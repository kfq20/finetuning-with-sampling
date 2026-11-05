"""One user-authorized recovery of original57 errors; retain32 normal attempts."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time


def main(root):
    run = root / 'retry57-20261105'
    run.mkdir(exist_ok=True)
    lock = (run / 'dispatch.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    if (run / 'launch.json').exists():
        raise RuntimeError('Recovery already launched; no automatic second replay')
    rows = []
    for job in ['tb21-qwen-fix-git-canary', 'tb21-qwen-base-remaining88']:
        for path in (root / 'model-jobs' / job).glob('*/result.json'):
            value = json.loads(path.read_text())
            assert value['finished_at']
            rows.append((path, value))
    assert len(rows) == 89
    failed = [(path, value) for path, value in rows if value.get('exception_info')]
    assert len(failed) == 57
    manifest = json.loads((root / 'evaluation-runtime-manifest.json').read_text())
    for relative, expected in manifest.items():
        assert hashlib.sha256((root / relative).read_bytes()).hexdigest() == expected
    selection = {'authorized_scope': 'Retry original51timeouts and6execution errors once',
                 'original_results': [], 'normal32_retained': [], 'automatic_paid_retry': False,
                 'merge_rule': 'Use new recovery outcome for selected57, never select best score',
                 'evaluation_only': True}
    for path, value in rows:
        record = {'task': value['task_name'], 'original_result': str(path),
                  'original_result_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                  'task_path': value['config']['task']['path']}
        key = 'original_results' if value.get('exception_info') else 'normal32_retained'
        selection[key].append(record)
    (run / 'selection.json').write_text(json.dumps(selection, indent=2) + '\n')
    config = json.loads((root / 'full-config.json').read_text())
    config.update(job_name='tb21-qwen-retry57-20261105', jobs_dir=str(run / 'jobs'),
                  tasks=[{'path': value['config']['task']['path']} for _, value in failed],
                  n_attempts=1, n_concurrent_trials=4, retry={'max_retries': 0})
    path = run / 'config.json'
    path.write_text(json.dumps(config, indent=2) + '\n')
    env = {**os.environ, 'PYTHONPATH': str(root / 'runtime-v2/source/agentic/src')}
    with (run / 'harbor.log').open('a') as log:
        worker = subprocess.Popen([sys.executable, str(root / 'oracle-launcher-v2.py'), str(path)],
                                  stdout=log, stderr=log, env=env)
        receipt = {'pid': worker.pid,
                   'start_ticks': Path('/proc/' + str(worker.pid) + '/stat').read_text().split()[21],
                   'started_at': time.time(), 'tasks': 57, 'concurrency': 4,
                   'config_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
                   'selection_sha256': hashlib.sha256((run / 'selection.json').read_bytes()).hexdigest(),
                   'automatic_paid_retry': False}
        (run / 'launch.json').write_text(json.dumps(receipt, indent=2) + '\n')
        (root / 'retry57-selection.json').write_text(json.dumps({'root': str(run), **receipt}, indent=2) + '\n')
        worker.wait()
        (run / 'worker-exit.json').write_text(json.dumps({'time': time.time(), 'exit_code': worker.returncode}) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', required=True, type=Path)
    main(parser.parse_args().root)
