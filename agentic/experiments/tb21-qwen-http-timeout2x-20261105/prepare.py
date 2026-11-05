"""One new authorized HTTP-base cohort; double agent time only, no paid retries."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tomllib

import toml


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def doubled(config):
    value = json.loads(json.dumps(config))
    assert value['agent']['timeout_sec'] > 0
    value['agent']['timeout_sec'] *= 2
    return value


def main():
    os.umask(0o077)
    root = Path(sys.argv[1]).resolve()
    assert not (root / 'launch-intent.json').exists(), 'Already dispatched; inspect, do not replay'
    old = Path('/mnt/ecs-tb4/evaluations/qwen38-tb21-base-20261104')
    source = root / 'runtime/ecs_eval.py'
    manifest = json.loads((old / 'evaluation-runtime-manifest.json').read_text())
    for relative, expected in manifest.items():
        assert sha(old / relative) == expected, relative
    cfg = json.loads((old / 'full-config.json').read_text())
    private = json.loads(Path(cfg['agents'][0]['kwargs']['native_config']).read_text())
    # The existing direct HTTP bridge has its own credential; no SSH model tunnel.
    private.update(native_endpoint='http://127.0.0.1:18133/generate',
                   base_url='http://127.0.0.1:18133')
    write(root / 'native-private.json', private)
    (root / 'native-private.json').chmod(0o600)
    selected = []
    changes = []
    hashes = {}
    for task in sorted((old / 'evaluation-tasks').iterdir()):
        if not (task / 'task.toml').exists():
            continue
        target = root / 'tasks' / task.name
        shutil.copytree(task, target, copy_function=os.link)
        before = tomllib.loads((task / 'task.toml').read_text())
        after = doubled(before)
        # Atomic replace breaks the hardlink; never modify the original config.
        temporary = target / 'task.toml.new'
        temporary.write_text(toml.dumps(after))
        temporary.replace(target / 'task.toml')
        check = tomllib.loads((target / 'task.toml').read_text())
        assert check == after
        for f in task.rglob('*'):
            if f.is_file():
                relative = f.relative_to(task)
                if f.name != 'task.toml':
                    assert sha(f) == sha(target / relative)
                hashes[str((target / relative).relative_to(root))] = sha(target / relative)
        changes.append({'task': task.name, 'agent_timeout_before': before['agent']['timeout_sec'],
            'agent_timeout_after': after['agent']['timeout_sec'], 'verifier_timeout_unchanged': before['verifier']['timeout_sec']})
        selected.append({'path': str(target)})
    assert len(selected) == 89
    cfg.update(tasks=selected, jobs_dir=str(root / 'jobs'), n_attempts=1,
        n_concurrent_trials=4, retry={'max_retries': 0}, timeout_multiplier=1.0)
    cfg['agents'][0]['kwargs']['native_config'] = str(root / 'native-private.json')
    write(root / 'full-config.json', cfg)
    write(root / 'timeout-changes.json', changes)
    write(root / 'task-manifest.json', hashes)
    write(root / 'binding.json', {'original_root': str(old),
        'authorization': 'User requested new HTTP Qwen base TB2.1 evaluation with doubled task timeout',
        'source_commit': (root / 'runtime/commit.txt').read_text().strip(),
        'model': 'Qwen/Qwen3.8-27B', 'upstream': 'http://123.57.26.97:8000/v1',
        'ssh_model_tunnel': False, 'task_count': 89, 'concurrency': 4,
        'agent_timeout_factor': 2, 'other_timeouts_factor': 1,
        'controller_sha256': sha(source), 'config_sha256': sha(root / 'full-config.json'),
        'task_manifest_sha256': sha(root / 'task-manifest.json'), 'at': time.time(),
        'previous_results_preserved': True, 'automatic_paid_retry': False})
    with (root / 'launch-intent.json').open('x') as f:
        json.dump({'at': time.time(), 'controller_sha256': sha(source)}, f)
    with (root / 'controller.log').open('a') as log:
        child = subprocess.Popen([sys.executable, str(source), '--controller', str(root)],
            stdout=log, stderr=log, start_new_session=True)
    receipt = {'pid': child.pid, 'start_ticks': Path('/proc/' + str(child.pid) + '/stat').read_text().split()[21],
        'at': time.time(), 'root': str(root), 'entry': str(source), 'entry_sha256': sha(source)}
    write(root / 'launch.json', receipt)
    print(json.dumps(receipt))


if __name__ == '__main__':
    main()
