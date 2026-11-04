"""One canary + remaining88, evaluation-only; never retry paid trajectories."""
import argparse
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tomllib

import toml


def write(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2) + '\n')
    temporary.replace(path)


def results(job):
    return [(p, json.loads(p.read_text())) for p in job.glob('*/result.json')]


def valid_trial(value):
    reward = (value.get('verifier_result') or {}).get('rewards', {}).get('reward')
    return (value.get('finished_at') and not value.get('exception_info')
            and isinstance(reward, (int, float)) and math.isfinite(reward))


def main(root):
    os.umask(0o077)
    lock = (root / 'baseline-controller.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (root / 'full-launch.json').exists():
        raise RuntimeError('Already dispatched; inspect original results, do not replay')
    canary = root / 'model-jobs/tb21-qwen-fix-git-canary'
    while True:
        if (root / 'STOP.json').exists():
            return
        final = json.loads((canary / 'result.json').read_text()) if (canary / 'result.json').exists() else {}
        if final.get('finished_at'):
            break
        write(root / 'baseline-status.json', {'phase': 'waiting_canary', 'time': time.time()})
        time.sleep(15)
    rows = results(canary)
    if len(rows) != 1 or not valid_trial(rows[0][1]):
        write(root / 'baseline-hold.json', {'reason': 'Canary execution/score incomplete',
                                         'time': time.time(), 'automatic_retry': False})
        return
    native = rows[0][0].parent / 'agent/native-generation'
    decisions = list(native.glob('turn-*/decision.json'))
    if not decisions:
        raise RuntimeError('No completed model decisions captured')
    for decision in decisions:
        transport = json.loads((decision.parent / 'transport.json').read_text())
        assert transport['complete_stop'], 'Incomplete model stream'
    for agent, expected in [('oracle', 1), ('nop', 0)]:
        controls = results(root / ('controls/tb21-fix-git-' + agent + '-ali-v3'))
        assert len(controls) == 1 and valid_trial(controls[0][1])
        assert controls[0][1]['verifier_result']['rewards']['reward'] == expected
    while not (root / 'image-preparation.json').exists():
        if (root / 'STOP.json').exists():
            return
        write(root / 'baseline-status.json', {'phase': 'waiting_images', 'time': time.time()})
        time.sleep(15)
    preparation = json.loads((root / 'image-preparation.json').read_text())
    if preparation['prepared'] != 89 or preparation['failures']:
        write(root / 'baseline-hold.json', {'reason': 'Image preparation incomplete',
                                          'details': preparation, 'automatic_retry': False})
        return
    allocations = []
    selected = []
    for source in sorted((root / 'prepared-tasks').iterdir()):
        if not (source / 'task.toml').exists():
            continue
        original = root / 'dataset/tasks' / source.name
        original_config = tomllib.loads((original / 'task.toml').read_text())
        config = tomllib.loads((source / 'task.toml').read_text())
        expected = json.loads(json.dumps(original_config))
        expected['environment']['docker_image'] = config['environment']['docker_image']
        assert config == expected, 'Prepared contract changed'
        for original_file in original.rglob('*'):
            if original_file.is_file() and original_file.name != 'task.toml':
                assert original_file.read_bytes() == (source / original_file.relative_to(original)).read_bytes()
        target = root / 'evaluation-tasks' / source.name
        shutil.copytree(source, target, dirs_exist_ok=False)
        env = config['environment']
        cpu, memory = env['cpus'], env['memory_mb']
        # Alibaba permits1–4GiB perCPU; never allocate below official requests.
        env['cpus'] = max(cpu, math.ceil(memory / 4096))
        env['memory_mb'] = max(memory, env['cpus'] * 1024)
        allocations.append({'task': source.name, 'declared': {'cpus': cpu, 'memory_mb': memory},
                            'allocated': {'cpus': env['cpus'], 'memory_mb': env['memory_mb']}})
        (target / 'task.toml').write_text(toml.dumps(config))
        if source.name != 'fix-git':
            selected.append({'path': str(target)})
    assert len(selected) == 88
    write(root / 'resource-allocations.json', allocations)
    config = json.loads((root / 'canary-config.json').read_text())
    config.update(job_name='tb21-qwen-base-remaining88', tasks=selected, n_concurrent_trials=4)
    path = root / 'full-config.json'
    write(path, config)
    env = {**os.environ, 'PYTHONPATH': str(root / 'runtime-v2/source/agentic/src')}
    with (root / 'full.log').open('a') as output:
        worker = subprocess.Popen([sys.executable, str(root / 'oracle-launcher-v2.py'), str(path)],
                                  stdout=output, stderr=output, env=env)
        write(root / 'full-launch.json', {
            'pid': worker.pid, 'start_ticks': Path('/proc/' + str(worker.pid) + '/stat').read_text().split()[21],
            'config_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
            'started_at': time.time(), 'pass_at': 1, 'concurrency': 4, 'remaining_tasks': 88,
            'canary_reused': str(rows[0][0]), 'automatic_paid_retry': False,
            'evaluation_only': True})
        worker.wait()
    all_rows = rows + results(root / 'model-jobs/tb21-qwen-base-remaining88')
    valid = [value for _, value in all_rows if valid_trial(value)]
    write(root / 'baseline-summary.json', {
        'time': time.time(), 'total_tasks': 89, 'recorded_trials': len(all_rows),
        'valid_finished': len(valid), 'successes': sum(v['verifier_result']['rewards']['reward'] == 1 for v in valid),
        'execution_or_capture_errors': len(all_rows) - len(valid), 'job_exit_code': worker.returncode,
        'training_export': False, 'automatic_paid_retry': False})


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    main(parser.parse_args().root)
