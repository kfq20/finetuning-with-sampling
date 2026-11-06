"""Freeze one selected SWE-Lite split; never change existing experiment packages."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from dotenv import dotenv_values


def main(root, split):
    os.umask(0o077)
    assert split in ('test', 'dev')
    assert not (root / 'plan.json').exists()
    experiment = root / 'runtime/source/agentic/experiments'
    spec = importlib.util.spec_from_file_location('pilot_materialize', experiment / 'swe-lite-dev-20261106/run.py')
    pilot = importlib.util.module_from_spec(spec); spec.loader.exec_module(pilot)
    parent = Path('/mnt/ecs-tb4/evaluations/qwen38-swe-lite-dev6-20261106-a2')
    rows = json.loads((root / 'source/rows.json').read_text())
    assert len(rows) == (300 if split == 'test' else 23)
    assert len({r['instance_id'] for r in rows}) == len(rows)
    prior_ids = {json.loads(p.read_text())['task_name'] for p in (parent / 'base/jobs').glob('*/*/result.json')}
    if split == 'test':
        assert not prior_ids.intersection(r['instance_id'] for r in rows)
    else:
        # Explicit import receipts, no paid retry of already completed dev tasks.
        reuse = {}
        for arm in ('base', 'method', 'expert'):
            reuse[arm] = [{'path': str(p), 'sha256': pilot.sha(p)} for p in
                          (parent / arm / 'jobs').glob('*/*/result.json')]
        pilot.dump(root / 'reused-dev-results.json', reuse)
        rows = [r for r in rows if r['instance_id'] not in prior_ids]
        pilot.dump(root / 'source/rows.json', rows)
    pilot.materialize(root, rows, dataset='SWE-bench_Lite/' + split)
    archive = parent / 'offline-runtime.tar.gz'
    assert pilot.sha(archive) == json.loads((parent / 'plan.json').read_text())['offline_runtime_sha256']
    os.link(archive, root / 'offline-runtime.tar.gz')
    (root / 'private').mkdir()
    (root / 'reference').mkdir()
    shutil.copyfile('/mnt/ecs-tb4/evaluations/qwen38-tb21-base-20261104/oracle-launcher-v2.py', root / 'reference/launcher.py')
    bindings = json.loads((parent / 'models.json').read_text())
    for arm in ('base', 'method', 'expert'):
        target = root / 'private' / (arm + '.json')
        shutil.copyfile(parent / arm / 'private.json', target); target.chmod(0o600)
        bindings[arm]['private_config_sha256'] = pilot.sha(target)
        assert pilot.sha(parent / arm / 'config.json') == bindings[arm]['config_sha256']
        shutil.copyfile(parent / arm / 'config.json', root / 'reference' / (arm + '-config.json'))
    pilot.dump(root / 'models.json', bindings)
    registry = root / 'private/registry-auth'; registry.mkdir()
    values = dotenv_values('/mnt/ecs-tb4/cli-gym-scale-20261104/support/private/sandbox.env', interpolate=False)
    env = {**os.environ, 'DOCKER_CONFIG': str(registry)}
    crane = '/mnt/ecs-tb4/relayforge_scenario_deepseek_aliyun_20261028_v1/bin/crane'
    p = subprocess.run([crane, 'auth', 'login', 'acr-rf-sg-registry.ap-southeast-8.cr.aliyuncs.com',
        '-u', values['REGISTRY_USERNAME'], '--password-stdin'], input=values['REGISTRY_PASSWORD'],
        env=env, capture_output=True, text=True, timeout=60)
    assert p.returncode == 0, 'Registry authentication failed'
    pilot.dump(root / 'plan.json', {'at': time.time(), 'split': split,
        'dataset': 'SWE-bench/SWE-bench_Lite', 'cohort': len(rows),
        'dataset_revision': json.loads((root / 'source/dataset-info.json').read_text())['sha'],
        'task_ids': [r['instance_id'] for r in rows], 'pass_at': 1,
        'arms': ['base', 'method', 'expert'], 'max_new_model_attempts': 3 * len(rows),
        'concurrency_per_arm': 4, 'gate_concurrency': 4, 'rolling_admission': True,
        'model_checkpoint': 'epoch1 step34 / base; unchanged from five-task pilot',
        'agent_timeout_sec': 1800, 'verifier_timeout_sec': 1800,
        'generation': {'temperature': .6, 'thinking': False, 'context_limit': 262144,
                       'max_output_tokens': 128000, 'max_turns': None},
        'automatic_paid_retry': False, 'original_pilot_root': str(parent),
        'claim_convention': 'Runtime/control/provider failures are unknown, not valid model0'})
    files = {str(p.relative_to(root)): pilot.sha(p) for folder in ('runtime', 'source', 'reference')
             for p in (root / folder).rglob('*') if p.is_file() and '__pycache__' not in p.parts}
    files['models.json'] = pilot.sha(root / 'models.json')
    files['plan.json'] = pilot.sha(root / 'plan.json')
    pilot.dump(root / 'source-files.json', files)
    print(json.dumps({'prepared': str(root), 'split': split, 'tasks': len(rows), 'max_new_model_attempts': 3 * len(rows)}))


if __name__ == '__main__':
    main(Path(sys.argv[1]), sys.argv[2])
