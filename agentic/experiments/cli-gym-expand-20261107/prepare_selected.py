"""Finite, inference-free preparation of the frozen holdout and fresh training rows."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time


def main(root):
    prior = Path('/mnt/ecs-tb4/cli-gym-scale-20261104')
    source = Path(json.loads((prior / 'campaign-selection.json').read_text())['source_root'])
    selection = root / 'split-v1/selection.json'
    selected = json.loads(selection.read_text())
    assert hashlib.sha256(selection.read_bytes()).hexdigest() == '642cc9d8aa19b227e512e290cab73c314c242d67959eda0feefd59ebe216c002'
    support = root / 'support/preparation-source'
    support.mkdir()
    old = source / 'agentic/experiments/cli-gym-pilot-20261104'
    raw = (old / 'prepare.py').read_bytes()
    assert hashlib.sha256(raw).hexdigest() == 'cfde5b34a586d272243cebe920858556bb4546f0eef1313e8ccde959ac3650eb'
    # Own copy only: leave more space for unrelated active SWE evaluation.
    text = raw.decode()
    assert text.count('< 20 * 1024**3') == 1
    text = text.replace('< 20 * 1024**3', '< 40 * 1024**3').replace('fewer than20GiB', 'fewer than40GiB')
    (support / 'prepare.py').write_text(text)
    shutil.copyfile(old / 'repair_test_ids.py', support / 'repair_test_ids.py')
    env = {**os.environ, 'PYTHONPATH': str(source / 'agentic/src'),
           'PYTHONDONTWRITEBYTECODE': '1',
           'DOCKER_HOST': 'unix:///mnt/ecs-tb4/cli-gym-pilot-20261104/runtime/docker.sock',
           'DOCKER_API_VERSION': '1.44', 'DOCKER_CONFIG': str(prior / 'docker-config')}
    groups = [('holdout', [x['row_index'] for x in selected['holdout']], 'holdout-rows.json'),
              ('fresh-acquisition', [x['row_index'] for x in selected['acquisition_candidates']
                                     if not x['previously_preparation_scanned']], 'fresh-acquisition-rows.json')]
    result = {}
    for name, indices, rows in groups:
        output = root / f'prepared-{name}'
        assert not output.exists()
        if shutil.disk_usage(root).free < 40 * 1024**3:
            result[name] = {'stage': 'storage_hold', 'new_model_requests': 0}
            break
        command = [sys.executable, str(support / 'prepare.py'), '--rows',
                   str(root / 'split-v1' / rows), '--output', str(output),
                   '--indices', *map(str, indices), '--canonicalize-selectors', '--storage-root', str(root)]
        with (root / f'{name}-preparation.log').open('xb') as log:
            child = subprocess.Popen(command, env=env, stdout=log, stderr=subprocess.STDOUT)
            (root / 'preparation-progress.json').write_text(json.dumps({
                'stage': name, 'child_pid': child.pid, 'started_at': time.time(),
                'output': str(output), 'new_model_requests': 0}, indent=2))
            rc = child.wait()
        result[name] = {'returncode': rc, 'output': str(output), 'new_model_requests': 0}
        if rc:
            break
    (root / 'preparation-finished.json').write_text(json.dumps(result, indent=2))


if __name__ == '__main__':
    main(Path(sys.argv[1]))
