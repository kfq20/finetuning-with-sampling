"""Finite 6-task SWE-bench Lite dev pilot, three frozen Qwen Fleet arms."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import fcntl
import hashlib
import importlib.util
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

PYTHON = '/mnt/ecs-tb4/cli-gym-scale-20261104/support/sdk/bin/python'
PRIOR = Path('/mnt/ecs-tb4/evaluations/qwen38-paired531-sft-20261105-a1')
LAUNCHER = '/mnt/ecs-tb4/evaluations/qwen38-tb21-base-20261104/oracle-launcher-v2.py'
REPOS = ('marshmallow-code/marshmallow', 'pydicom/pydicom', 'pylint-dev/astroid')
ARMS = ('base', 'method', 'expert')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    pending = path.with_suffix(path.suffix + '.tmp')
    pending.write_text(json.dumps(value, indent=2) + '\n')
    pending.replace(path)


def selected(rows):
    return [row for repo in REPOS for row in sorted(
        (r for r in rows if r['repo'] == repo), key=lambda x: x['instance_id'])[:2]]


def prepare(root):
    import toml
    assert not (root / 'plan.json').exists(), 'Do not mutate frozen plan'
    rows = json.loads((root / 'source/dev.json').read_text())
    tasks = selected(rows)
    assert len(rows) == 23 and len(tasks) == 6
    parser = (root / 'source/python.py').read_text()
    assert parser.count('from swebench.harness.constants import TestStatus') == 1
    # Official parser function bodies stay byte-identical; only standalone imports
    # replace package-only type hints and the four-value status enum.
    parser = 'from __future__ import annotations\n' + parser.replace(
        'from swebench.harness.constants import TestStatus',
        'from enum import Enum\nclass TestStatus(Enum):\n'
        '    PASSED = "PASSED"\n    FAILED = "FAILED"\n'
        '    SKIPPED = "SKIPPED"\n    ERROR = "ERROR"').replace(
        'from swebench.types import TestSpec', '')
    exp = Path(__file__).parent
    for row in tasks:
        p = root / 'dataset/tasks' / row['instance_id']
        for name in ('environment', 'tests', 'solution'):
            (p / name).mkdir(parents=True)
        (p / 'instruction.md').write_text(
            'The repository is available at /testbed. Resolve the following issue. '
            'Preserve unrelated behavior and leave the repaired source in the repository.\n\n'
            + row['problem_statement'] + '\n')
        (p / 'environment/Dockerfile').write_text('FROM ' + row['image'] + '\nWORKDIR /testbed\n')
        config = {'schema_version': '1.1', 'metadata': {
            'category': 'software-engineering', 'dataset': 'SWE-bench_Lite/dev',
            'instance_id': row['instance_id']},
            'agent': {'timeout_sec': 1800}, 'verifier': {'timeout_sec': 600},
            'environment': {'docker_image': row['image'], 'build_timeout_sec': 1800,
                            'cpus': 2, 'memory_mb': 4096, 'storage_mb': 10240,
                            'allow_internet': False,
                            'env': {'PATH': '/opt/miniconda3/envs/testbed/bin:/opt/miniconda3/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin'}}}
        (p / 'task.toml').write_text(toml.dumps(config))
        (p / 'tests/eval.sh').write_text(row['eval_script'])
        (p / 'tests/official_parsers.py').write_text(parser)
        shutil.copyfile(exp / 'grade.py', p / 'tests/grade.py')
        dump(p / 'tests/grading.json', {k: row[k] for k in
             ('instance_id', 'log_parser', 'FAIL_TO_PASS', 'PASS_TO_PASS')})
        (p / 'tests/test.sh').write_text('#!/bin/bash\nset -euo pipefail\n'
            'export PYTHONPATH=/tests\npython3 /tests/grade.py /tests /logs/verifier\n')
        (p / 'tests/test.sh').chmod(0o755)
        (p / 'solution/gold.patch').write_text(row['patch'])
        (p / 'solution/solve.sh').write_text('#!/bin/bash\nset -euo pipefail\n'
            'cd /testbed\ngit apply /solution/gold.patch\n')
        (p / 'solution/solve.sh').chmod(0o755)
    dump(root / 'plan.json', {'at': time.time(), 'dataset_revision':
        json.loads((root / 'source/dataset-info.json').read_text())['sha'],
        'parser_commit': json.loads((root / 'source/swebench-head.json').read_text())['sha'],
        'source_sha256': sha(root / 'source/dev.json'),
        'task_ids': [r['instance_id'] for r in tasks], 'arms': list(ARMS),
        'selection': 'First two sorted instance IDs per predefined lightweight project',
        'agent_timeout_sec': 1800, 'concurrency_per_arm': 1,
        'generation': {'temperature': .6, 'thinking': False},
        'checkpoint_selection': 'Frozen epoch1 step34; epoch2 not deployed',
        'automatic_paid_retry': False, 'official_test_score': False})


def config(root, agent, tasks, job):
    cfg = json.loads((PRIOR / 'base/full-config.json').read_text())
    cfg.update(job_name=job, jobs_dir=str(root / 'controls'),
               tasks=[{'path': str(p)} for p in tasks], n_attempts=1,
               n_concurrent_trials=2, retry={'max_retries': 0})
    cfg['agents'] = [{'name': agent}]
    return cfg


def invoke(root, cfg, name):
    path = root / (name + '.json')
    assert not path.exists(), 'No repeated evaluation job'
    dump(path, cfg)
    with (root / (name + '.log')).open('x') as f:
        return subprocess.run([PYTHON, LAUNCHER, str(path)], stdout=f, stderr=f).returncode


def trial_rows(path):
    return [(p, json.loads(p.read_text())) for p in path.glob('*/result.json')]


def valid(row):
    reward = (row.get('verifier_result') or {}).get('rewards', {}).get('reward')
    return bool(row.get('finished_at') and not row.get('exception_info')
                and isinstance(reward, (float, int)) and math.isfinite(reward))


def admission(root):
    tasks = sorted((root / 'prepared-tasks').iterdir())
    expected = json.loads((root / 'plan.json').read_text())['task_ids']
    assert len(tasks) == len(expected) == 6
    # NOP/oracle uses the actual Harbor/Ali environment and official grader.
    for agent in ('nop', 'oracle'):
        name = 'control-' + agent
        code = invoke(root, config(root, agent, tasks, name), name)
        dump(root / (name + '-exit.json'), {'exit_code': code, 'at': time.time()})
    verify_controls(root)


def verify_controls(root):
    tasks = sorted((root / 'prepared-tasks').iterdir())
    assert len(tasks) == 6
    receipts = {}
    for task in tasks:
        evidence = {}
        for agent, score in [('nop', 0), ('oracle', 1)]:
            matches = [(p, r) for p, r in trial_rows(root / 'controls' / ('control-' + agent))
                       if r['task_name'] == task.name]
            assert len(matches) == 1 and valid(matches[0][1]), ('Invalid control', task.name, agent)
            p, row = matches[0]
            assert row['verifier_result']['rewards']['reward'] == score, (task.name, agent)
            evidence[agent] = {'result_path': str(p), 'result_sha256': sha(p), 'reward': score}
        evidence['files'] = {str(p.relative_to(task)): sha(p) for p in task.rglob('*') if p.is_file()}
        receipts[task.name] = evidence
    dump(root / 'admission.json', {'at': time.time(), 'passed': True, 'tasks': receipts})


def prepare_models(root):
    import asyncio
    import httpx
    from append_rewrite.terminus.native_stream import NativeStreamClient
    # Read-only deployment identity check: no extra inference probe.
    records = {}
    for arm in ARMS:
        dest = root / arm
        dest.mkdir()
        old = PRIOR / arm
        cfg = json.loads((old / 'full-config.json').read_text())
        source = Path(cfg['agents'][0]['kwargs']['native_config'])
        shutil.copyfile(source, dest / 'private.json')
        (dest / 'private.json').chmod(0o600)
        client = NativeStreamClient(dest / 'private.json')
        c = client.config
        async def check():
            async with httpx.AsyncClient(timeout=30, trust_env=False) as http:
                r = await http.get(c['base_url'].rstrip('/') + '/api/fleet/v1/deployments/' + c['task_id'],
                                   headers={'x-api-key': c['api_key']})
                r.raise_for_status()
                return r.json()
        status = asyncio.run(check())
        binding = json.loads((old / 'binding.json').read_text())
        checkpoint = binding.get('checkpoint')
        assert status['state'] in ('serving', 'succeeded')
        assert status['model_id'] == c['task_id'] and status['base_model'] == 'Qwen/Qwen3.8-27B'
        assert status['source'] == ('lora' if checkpoint else 'base')
        assert not checkpoint or status.get('checkpoint') == checkpoint
        tasks = [root / 'prepared-tasks' / name for name in json.loads((root / 'plan.json').read_text())['task_ids']]
        cfg.update(job_name='swe-lite-dev6', jobs_dir=str(dest / 'jobs'),
                   tasks=[{'path': str(p)} for p in tasks], n_attempts=1,
                   n_concurrent_trials=1, retry={'max_retries': 0})
        cfg['agents'][0]['kwargs'].update(native_config=str(dest / 'private.json'),
                                        inference_profile='cancellable-legacy')
        dump(dest / 'config.json', cfg)
        records[arm] = {'model_id': status['model_id'], 'source': status['source'],
                        'checkpoint': checkpoint, 'cluster_id': status['cluster_id'],
                        'config_sha256': sha(dest / 'config.json')}
    dump(root / 'models.json', records)


def collect(root):
    summary = {'at': time.time(), 'arms': {}}
    for arm in ARMS:
        rows = trial_rows(root / arm / 'jobs/swe-lite-dev6')
        summary['arms'][arm] = {'planned': 6, 'ended': len(rows),
            'valid': sum(valid(r) for _, r in rows),
            'resolved': sum(valid(r) and r['verifier_result']['rewards']['reward'] == 1 for _, r in rows),
            'unknown': sum(not valid(r) for _, r in rows)}
    dump(root / 'progress.json', summary)
    return summary


def models(root):
    assert json.loads((root / 'admission.json').read_text())['passed']
    assert not (root / 'dispatch-claim.json').exists(), 'No automatic paid replay'
    for task, evidence in json.loads((root / 'admission.json').read_text())['tasks'].items():
        for relative, expected in evidence['files'].items():
            assert sha(root / 'prepared-tasks' / task / relative) == expected
    prepare_models(root)
    dump(root / 'dispatch-claim.json', {'at': time.time(), 'planned': 18,
         'models_sha256': sha(root / 'models.json'), 'admission_sha256': sha(root / 'admission.json')})
    logs, children = [], {}
    try:
        for arm in ARMS:
            log = (root / arm / 'harbor.log').open('x'); logs.append(log)
            child = subprocess.Popen([PYTHON, LAUNCHER, str(root / arm / 'config.json')],
                                     stdout=log, stderr=log)
            children[arm] = child
            dump(root / arm / 'launch.json', {'pid': child.pid,
                'start_ticks': Path(f'/proc/{child.pid}/stat').read_text().split()[21], 'at': time.time()})
        while any(p.poll() is None for p in children.values()):
            collect(root)
            time.sleep(20)
        dump(root / 'finished.json', {'at': time.time(), 'results': collect(root),
                                     'exit_codes': {k: p.returncode for k, p in children.items()}})
    finally:
        for f in logs:
            f.close()


def continue_after_controls(root):
    # Only an unpaid admission bookkeeping repair; reuse all actual controls.
    lock = (root / 'controller.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert not (root / 'dispatch-claim.json').exists()
    assert (root / 'hold.json').exists(), 'Wait for the original finite preparer to exit'
    verify_controls(root)
    dump(root / 'admission-repair.json', {'at': time.time(),
        'original_hold_sha256': sha(root / 'hold.json'),
        'reason': 'Canonical task_name matching, not truncated Harbor trial directory',
        'replayed_controls': 0, 'replayed_models': 0})
    models(root)


def pipeline(root):
    os.umask(0o077)
    lock = (root / 'controller.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        prepare(root)
        source = root / 'runtime/source'
        helper = source / 'agentic/experiments/tb21-qwen-base-20261104/prepare_images.py'
        spec = importlib.util.spec_from_file_location('pinned_image_copy', helper)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        code = mod.prepare(root, Path('/mnt/ecs-tb4/relayforge_scenario_deepseek_aliyun_20261028_v1/bin/crane'),
            Path('/mnt/ecs-tb4/cli-gym-scale-20261104/support/private/sandbox.env'), 2)
        assert code == 0, 'Image preparation failed; no model requests allowed'
        admission(root)
        models(root)
    except BaseException as e:
        # Raw HTTP/model credentials are never logged in this top-level receipt.
        dump(root / 'hold.json', {'at': time.time(), 'type': type(e).__name__,
                                 'message': str(e)[:400] if isinstance(e, AssertionError) else '',
                                 'model_dispatch_claimed': (root / 'dispatch-claim.json').exists()})
        raise


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mode', choices=['pipeline', 'collect', 'continue'])
    parser.add_argument('root', type=Path)
    args = parser.parse_args()
    {'pipeline': pipeline, 'collect': collect, 'continue': continue_after_controls}[args.mode](args.root)
