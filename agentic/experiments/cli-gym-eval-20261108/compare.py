"""Launch and report the matched three-arm Fleet CLI-Gym comparison on ECS."""
import argparse
import asyncio
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

from run import dump, effective_result, read

BASELINE = Path('/mnt/ecs-tb4/evaluations/qwen38-cli100-base-http-20261108-a1')
ROOT = Path('/mnt/ecs-tb4/evaluations/qwen38-cli100-epoch2-fleet-20261109')
ARMS = ('base', 'method', 'expert')
FLEET = 'https://mint-mol-fleet-prod-c4ebad.southeastasia.cloudapp.azure.com'
CLUSTER = 'h20-qwen38-tp4'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def launch_process(name, args):
    with (ROOT / f'{name}.log').open('xb') as log:
        child = subprocess.Popen([sys.executable, *map(str, args)], stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=log, start_new_session=True)
    fields = Path(f'/proc/{child.pid}/stat').read_text().split(') ', 1)[1].split()
    return {'pid': child.pid, 'start_ticks': fields[19], 'at': time.time()}


async def probe(arm, token_ids):
    from append_rewrite.terminus.native_stream import NativeStreamClient

    class PinnedProbe:
        def encode(self, text, add_special_tokens=False):
            return token_ids

    out = ROOT / 'probe' / arm
    client = NativeStreamClient(ROOT / arm / 'private.json')
    response = await asyncio.wait_for(client.generate_async(
        '', PinnedProbe(), journal=out, sampling_params={'temperature': 0.6},
        max_tokens=16), timeout=60)
    return {'normal_stop': response['meta_info']['finish_reason']['type'] == 'stop',
            'prompt_tokens': response['meta_info']['prompt_tokens'],
            'completion_tokens': response['meta_info']['completion_tokens']}


def launch():
    import httpx

    data = json.load(sys.stdin)
    key = data['key']
    bindings = data['deployments']
    assert set(bindings) == set(ARMS)
    expected = read(BASELINE.parent / 'qwen38-cli100-epoch2-20261108-a1/plan.json')
    plan = read(BASELINE / 'plan.json')
    assert plan['holdout_selection_sha256'] == expected['holdout_selection_sha256']
    selection = Path(plan['holdout_selection'])
    assert sha(selection) == plan['holdout_selection_sha256']
    wanted = {x['row_index'] for x in read(selection)['holdout']}
    admission = read(BASELINE / 'preparation-complete.json')
    prepared = read(BASELINE / 'tasks.json')['units']
    held = {x['row_index'] for x in admission['held']}
    ready = {x['row_index'] for x in prepared}
    assert len(wanted) == 100 and ready | held == wanted and not ready & held
    assert all(sha(Path(i['spec_path'])) == i['spec_sha256'] for i in prepared)
    with httpx.Client(base_url=FLEET, headers={'x-api-key': key}, timeout=20) as api:
        for arm in ARMS:
            task = bindings[arm]
            r = api.get('/api/fleet/v1/deployments/' + task)
            r.raise_for_status()
            d = r.json()
            assert d['task_id'] == d['model_id'] == task and d['cluster_id'] == CLUSTER
            assert d['state'] in ('serving', 'succeeded') and d.get('mounted_at')
            assert d['base_model'] == plan['model']
            if arm == 'base':
                assert d['source'] == 'base' and not d.get('checkpoint')
            else:
                assert d['source'] == 'lora' and d['checkpoint'] == expected['checkpoints'][arm]['state_path']
    os.umask(0o077)
    ROOT.mkdir(exist_ok=False)
    (ROOT / 'probe').mkdir()
    shutil.copyfile(selection, ROOT / 'holdout-selection.json')
    dump(ROOT / 'tasks.json', {'units': prepared})
    dump(ROOT / 'initial-preparation.json', admission)
    dump(ROOT / 'comparison-plan.json', {'planned_tasks': 100, 'planned_trials': 300,
        'holdout_sha256': sha(selection), 'initial_prepared': len(ready), 'initial_held': len(held),
        'deployments': bindings, 'checkpoint_step': 68, 'cluster_id': CLUSTER,
        'common_settings': {k: plan[k] for k in ('model', 'tokenizer', 'runtime_assets',
            'concurrency', 'temperature', 'thinking', 'context_limit', 'task_timeout')},
        'http_base_separate': str(BASELINE), 'entry_sha256': sha(Path(__file__)),
        'attempts_per_arm_task': 1, 'automatic_paid_retry': False})
    for arm, task in bindings.items():
        folder = ROOT / arm
        folder.mkdir()
        (folder / 'tasks.json').symlink_to('../tasks.json')
        (folder / 'preparation-complete.json').symlink_to('../preparation-complete.json')
        dump(folder / 'plan.json', {**plan, 'model_role': arm, 'fleet_deployment': task,
             'holdout_selection': str(ROOT / 'holdout-selection.json'),
             'endpoint': f'{FLEET}/d/{task}/generate'})
        dump(folder / 'private.json', {'base_url': FLEET, 'task_id': task, 'model_id': task,
             'api_key': key, 'context_limit': plan['context_limit'],
             'native_generation_stream': True, 'fleet_route_model': True})
        (folder / 'private.json').chmod(0o600)
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {arm: pool.submit(asyncio.run, probe(arm, data['probe_ids'])) for arm in ARMS}
        smoke = {arm: job.result() for arm, job in jobs.items()}
    assert all(v['normal_stop'] and v['completion_tokens'] > 0 for v in smoke.values())
    dump(ROOT / 'transport-probes.json', smoke)
    receipts = {arm: launch_process(arm, [Path(__file__).with_name('run.py'), 'run', ROOT / arm])
                for arm in ARMS}
    dump(ROOT / 'launch.json', receipts)
    print(json.dumps({'root': str(ROOT), 'probes': smoke, 'controllers': receipts}, indent=2))


def report():
    plan = read(ROOT / 'comparison-plan.json')
    wanted = sorted(x['row_index'] for x in read(ROOT / 'holdout-selection.json')['holdout'])
    results = {arm: {row: effective_result(ROOT / arm, row) for row in wanted} for arm in ARMS}
    valid = {arm: {row for row, v in results[arm].items() if v and v['valid']} for arm in ARMS}
    common = sorted(set.intersection(*valid.values()))
    stats = {}
    for arm in ARMS:
        seen = [v for v in results[arm].values() if v is not None]
        ok = [results[arm][row] for row in valid[arm]]
        common_wins = sum(results[arm][row]['binary_score'] for row in common)
        health = ROOT / arm / 'health.json'
        stats[arm] = {'valid': len(ok), 'full_success': sum(v['binary_score'] for v in ok),
            'errors': len(seen) - len(ok), 'common_full_success': common_wins,
            'common_pct': 100 * common_wins / len(common) if common else None,
            'median_elapsed_sec': median(v['elapsed_sec'] for v in ok),
            'health': read(health) if health.exists() else None}
    result = {'at': time.time(), 'planned_tasks': plan['planned_tasks'],
              'prepared': len(read(ROOT / 'tasks.json')['units']), 'three_way_valid': len(common),
              'common_rows': common, 'arms': stats}
    dump(ROOT / 'comparison-summary.json', result)
    print(json.dumps(result, indent=2))


def median(values):
    from statistics import median as calculate
    data = list(values)
    return calculate(data) if data else None


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('mode', choices=['launch', 'report'])
    args = p.parse_args()
    (launch if args.mode == 'launch' else report)()
