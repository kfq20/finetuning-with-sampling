"""One explicit three-task canary; old results immutable, no automatic retries."""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import time

TASKS = ('regex-log', 'password-recovery', 'polyglot-rust-c')
OLD = Path('/mnt/ecs-tb4/evaluations/qwen38-http-base-timeout2x-20261105-a1')
PYTHON = '/mnt/ecs-tb4/cli-gym-scale-20261104/support/sdk/bin/python'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def prepare(root):
    os.umask(0o077)
    assert not (root / 'binding.json').exists(), 'Already prepared; never replace a run'
    source = root / 'runtime/source/agentic/src'
    for relative, expected in json.loads((root / 'runtime/files.json').read_text()).items():
        assert sha(root / 'runtime' / relative) == expected, relative
    # Credential copied only on ECS, never sent to the operator or committed.
    prior = Path('/mnt/ecs-tb4/cli-gym-scale-20261104/native-endpoint-recovery-20261104/qwen-direct-private.json')
    private = json.loads(prior.read_text())
    origin = private['base_url'].removesuffix('/v1')
    config = {'base_url': origin, 'native_endpoint': origin + '/generate',
              'api_key': private['api_key'], 'model_id': 'Qwen/Qwen3.8-27B',
              'context_limit': 262144, 'user_authorized_direct_origin': origin,
              'scoped_abort': False}
    dump(root / 'private.json', config)
    (root / 'private.json').chmod(0o600)
    cfg = json.loads((OLD / 'full-config.json').read_text())
    cfg.update(job_name='three-timeout-controls', jobs_dir=str(root / 'jobs'),
               n_concurrent_trials=3, n_attempts=1, retry={'max_retries': 0})
    selected = [t for t in cfg['tasks'] if Path(t['path']).name in TASKS]
    assert len(selected) == len(TASKS)
    cfg['tasks'] = selected
    cfg['agents'][0]['kwargs'].update(native_config=str(root / 'private.json'),
        inference_profile='cancellable-thinking', interleaved_thinking=True,
        temperature=1.0)
    baseline = []
    task_hashes = {}
    for task in TASKS:
        result = list(OLD.glob('jobs/*/' + task + '__*/result.json'))
        assert len(result) == 1
        row = json.loads(result[0].read_text())
        assert row['exception_info']['exception_type'] == 'AgentTimeoutError'
        baseline.append({'task': task, 'result_path': str(result[0]),
                         'result_sha256': sha(result[0])})
        for path in (OLD / 'tasks' / task).rglob('*'):
            if path.is_file():
                task_hashes[str(path)] = sha(path)
    dump(root / 'task-files.json', task_hashes)
    dump(root / 'config.json', cfg)
    dump(root / 'binding.json', {
        'at': time.time(), 'source_commit': (root / 'runtime/commit.txt').read_text().strip(),
        'baseline_root': str(OLD), 'baseline_results': baseline,
        'task_files_sha256': sha(root / 'task-files.json'), 'config_sha256': sha(root / 'config.json'),
        'runtime_manifest_sha256': sha(root / 'runtime/files.json'),
        'thinking': True, 'preserve_thinking': True, 'reasoning_effort': 'xhigh',
        'sampling': {'temperature': 1, 'top_p': .95, 'top_k': 20, 'min_p': 0,
                     'presence_penalty': 0, 'repetition_penalty': 1},
        'max_new_tokens': 128000, 'context_limit': 262144,
        'agent_time_budget': 'Same per-task 2x budgets as previous HTTP cohort',
        'official_full_tb21_protocol_reproduced': False,
        'official_reference': 'https://huggingface.co/Qwen/Qwen3.8-27B',
        'scope': 'User-authorized three previously timed-out tasks, once each',
        'direct_http_no_bridge': True, 'inference_threads': False,
        'provider_scoped_abort_capability': '404; socket close only, engine abort unconfirmed',
        'automatic_paid_retry': False, 'comparison': 'Historical control; multiple protocol changes, not a single-factor ablation',
    })
    print(json.dumps({'prepared': str(root), 'tasks': list(TASKS)}))


def collect(root):
    rows = []
    for path in sorted((root / 'jobs').glob('*/*/result.json')):
        value = json.loads(path.read_text())
        gen = path.parent / 'native-generation'
        if not gen.exists():
            gen = path.parent / 'agent/native-generation'
        decisions = [json.loads(p.read_text()) for p in sorted(gen.glob('turn-*/decision.json'))]
        cleanup = [json.loads(p.read_text()) for p in gen.glob('turn-*/cleanup.json')]
        usage = [d['usage'] for d in decisions]
        err = value.get('exception_info') or {}
        reward = (value.get('verifier_result') or {}).get('rewards', {}).get('reward')
        valid = bool(value.get('finished_at') and not err and isinstance(reward, (int, float)) and math.isfinite(reward))
        rows.append({'task': path.parent.name, 'result_sha256': sha(path),
                     'exception_type': err.get('exception_type'), 'valid_completed': valid,
                     'reward': reward, 'binary_success': int(reward == 1) if valid else None,
                     'turns': len(decisions), 'context_peak': max([u.get('prompt_tokens', 0) for u in usage] or [0]),
                     'input_tokens': sum(u.get('prompt_tokens', 0) for u in usage),
                     'output_tokens': sum(u.get('completion_tokens', 0) for u in usage),
                     'generation_sec': sum(d['elapsed_sec'] for d in decisions),
                     'cleanup': cleanup, 'started_at': value.get('started_at'),
                     'finished_at': value.get('finished_at')})
    dump(root / 'progress.json', {'checked_at': time.time(), 'planned': 3, 'ended': len(rows), 'rows': rows})
    return rows


def run(root):
    import fcntl
    lock = (root / 'controller.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert not (root / 'claim.json').exists(), 'No repeated dispatch'
    binding = json.loads((root / 'binding.json').read_text())
    assert sha(root / 'config.json') == binding['config_sha256']
    for name, expected in json.loads((root / 'task-files.json').read_text()).items():
        assert sha(Path(name)) == expected
    for relative, expected in json.loads((root / 'runtime/files.json').read_text()).items():
        assert sha(root / 'runtime' / relative) == expected
    dump(root / 'claim.json', {'at': time.time(), 'attempts_per_task': 1})
    env = {**os.environ, 'PYTHONPATH': str(root / 'runtime/source/agentic/src')}
    launcher = '/mnt/ecs-tb4/evaluations/qwen38-tb21-base-20261104/oracle-launcher-v2.py'
    with (root / 'harbor.log').open('a') as log:
        child = subprocess.Popen([PYTHON, launcher, str(root / 'config.json')],
                                 env=env, stdout=log, stderr=log)
        dump(root / 'harbor-launch.json', {'pid': child.pid, 'start_ticks':
             Path(f'/proc/{child.pid}/stat').read_text().split()[21], 'at': time.time()})
        while child.poll() is None:
            collect(root)
            time.sleep(20)
        rows = collect(root)
    for item in binding['baseline_results']:
        assert sha(Path(item['result_path'])) == item['result_sha256']
    dump(root / 'finished.json', {'exit_code': child.returncode, 'at': time.time(),
                                 'ended': len(rows), 'old_results_unchanged': True})


if __name__ == '__main__':
    mode, folder = sys.argv[1:]
    {'prepare': prepare, 'run': run, 'collect': collect}[mode](Path(folder))
