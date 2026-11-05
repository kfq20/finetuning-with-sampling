"""Stdin-only secret ingress; unique frozen evaluation per arm, no replays."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def valid(row):
    import math
    reward = (row.get('verifier_result') or {}).get('rewards', {}).get('reward')
    return bool(row.get('finished_at') and not row.get('exception_info')
        and isinstance(reward, (float, int)) and math.isfinite(reward))


def collect(root):
    return [json.loads(p.read_text()) for p in root.glob('*/result.json')]


def controller(root):
    import fcntl
    lock = (root / 'controller.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    binding = json.loads((root / 'binding.json').read_text())
    source = Path(binding['original_root'])
    env = {**os.environ, 'PYTHONPATH': str(source / 'runtime-v2/source/agentic/src')}
    launcher = source / 'oracle-launcher-v2.py'
    config = json.loads((root / 'full-config.json').read_text())
    canary = dict(config, job_name='canary-fix-git', tasks=[t for t in config['tasks'] if Path(t['path']).name == 'fix-git'], n_concurrent_trials=1)
    assert len(canary['tasks']) == 1
    for phase, cfg in [('canary', canary), ('remaining88', dict(config,
            job_name='remaining88', tasks=[t for t in config['tasks'] if Path(t['path']).name != 'fix-git']))]:
        if (root / 'STOP').exists():
            return
        path = root / (phase + '-config.json')
        write(path, cfg)
        with (root / (phase + '-claim.json')).open('x') as f:
            json.dump({'at': time.time(), 'config_sha256': hashlib.sha256(path.read_bytes()).hexdigest()}, f)
        with (root / (phase + '.log')).open('a') as log:
            child = subprocess.Popen([sys.executable, str(launcher), str(path)], env=env, stdout=log, stderr=log)
            write(root / (phase + '-launch.json'), {'pid': child.pid,
                'start_ticks': Path('/proc/' + str(child.pid) + '/stat').read_text().split()[21], 'at': time.time()})
            code = child.wait()
        rows = collect(root / 'jobs' / cfg['job_name'])
        write(root / (phase + '-summary.json'), {'exit_code': code, 'recorded': len(rows),
            'valid': sum(valid(r) for r in rows), 'full_success': sum(valid(r) and r['verifier_result']['rewards']['reward'] == 1 for r in rows),
            'errors_or_unknown': sum(not valid(r) for r in rows), 'at': time.time()})
        if phase == 'canary':
            if len(rows) != 1 or not valid(rows[0]):
                write(root / 'HOLD.json', {'reason': 'Canary failed execution/scoring; no automatic replay', 'at': time.time()})
                return
            decisions = list((root / 'jobs' / cfg['job_name']).glob('*/agent/native-generation/turn-*/decision.json'))
            assert decisions, 'Missing native canary capture'
            for p in decisions:
                assert json.loads((p.parent / 'transport.json').read_text())['complete_stop']
    rows = collect(root / 'jobs/canary-fix-git') + collect(root / 'jobs/remaining88')
    complete = [r for r in rows if valid(r)]
    write(root / 'summary.json', {'planned_tasks': 89, 'recorded_trials': len(rows),
        'valid_completed': len(complete), 'binary_successes': sum(r['verifier_result']['rewards']['reward'] == 1 for r in complete),
        'errors_or_unknown': len(rows)-len(complete), 'automatic_paid_retry': False, 'at': time.time()})


def ingress():
    os.umask(0o077)
    data = json.loads(sys.stdin.read())
    original = Path('/mnt/ecs-tb4/evaluations/qwen38-tb21-base-20261104')
    root = Path(data['plan']['evaluation']['ecs_root']) / data['arm']
    root.mkdir(parents=True, exist_ok=False)
    manifest = json.loads((original / 'evaluation-runtime-manifest.json').read_text())
    for name, expected in manifest.items():
        assert hashlib.sha256((original / name).read_bytes()).hexdigest() == expected, name
    private = root / 'fleet-private.json'
    write(private, {'base_url': data['plan']['fleet']['base_url'], 'task_id': data['task_id'],
        'model_id': data['task_id'], 'api_key': data['fleet_key'], 'context_limit': 262144})
    private.chmod(0o600)
    cfg = json.loads((original / 'full-config.json').read_text())
    cfg.update(jobs_dir=str(root / 'jobs'), n_attempts=1, n_concurrent_trials=4, retry={'max_retries': 0})
    cfg['tasks'] = [{'path': str(p)} for p in sorted((original / 'evaluation-tasks').iterdir()) if (p / 'task.toml').exists()]
    assert len(cfg['tasks']) == 89
    agent = cfg['agents'][0]
    agent['model_name'] = 'openai/' + data['task_id']
    agent['kwargs']['native_config'] = str(private)
    # Keep all other agent settings, task paths, resources and deadlines unchanged.
    write(root / 'full-config.json', cfg)
    write(root / 'binding.json', {'original_root': str(original), 'checkpoint': data['checkpoint'],
        'task_id': data['task_id'], 'arm': data['arm'], 'source_manifest_sha256': hashlib.sha256((original / 'evaluation-runtime-manifest.json').read_bytes()).hexdigest(),
        'ingress_sha256': data['ingress_sha256'], 'plan': data['plan'], 'at': time.time()})
    # This exact ingress source is frozen to a standalone controller before launch.
    entry = root / 'controller.py'
    entry.write_text(SOURCE)
    # Use the same installed Harbor Python from the original controller's venv.
    python = Path('/mnt/ecs-tb4/cli-gym-scale-20261104/support/sdk/bin/python')
    if not python.exists():
        raise RuntimeError('Expected Harbor interpreter absent; inspect original launch before dispatch')
    with (root / 'controller.log').open('a') as log:
        child = subprocess.Popen([str(python), str(entry), '--controller', str(root)], stdout=log, stderr=log, start_new_session=True)
    receipt = {'root': str(root), 'pid': child.pid, 'start_ticks': Path('/proc/' + str(child.pid) + '/stat').read_text().split()[21],
        'entry_sha256': hashlib.sha256(entry.read_bytes()).hexdigest(), 'at': time.time(), 'automatic_paid_retry': False}
    write(root / 'launch.json', receipt)
    print(json.dumps(receipt))


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--controller':
        controller(Path(sys.argv[2]))
    else:
        ingress()
