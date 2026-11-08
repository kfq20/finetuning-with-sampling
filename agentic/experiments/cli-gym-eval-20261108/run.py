"""Frozen CLI heldout evaluation: plain Terminus, one attempt, no training export."""
import argparse
import asyncio
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
from types import SimpleNamespace
import time

from append_rewrite.terminus.production import dump, episode
from append_rewrite.terminus.benchmark_llm import CancellableQwenLLM
from append_rewrite.terminus.tokenizer import PinnedTokenizer


def read(path):
    return json.loads(path.read_text())


def prepare(root):
    plan = read(root / 'plan.json')
    source = Path(plan['source_root'])
    selection = Path(plan['holdout_selection'])
    assert hashlib.sha256(selection.read_bytes()).hexdigest() == plan['holdout_selection_sha256']
    wanted = [x['row_index'] for x in read(selection)['holdout']]
    assert len(wanted) == len(set(wanted)) == 100
    previous = {read(Path(x['spec_path']))['source']['row_index']: x
                for x in read(source / 'prepared-holdout/plan.json')['units']}
    rows = {x['row_idx']: x['row'] for x in read(source / 'split-v1/holdout-rows.json')['rows']}
    factory = runpy.run_path(str(Path(__file__).parents[1] / 'cli-gym-pilot-20261104/prepare.py'))['prepare']
    output = root / 'prepared'
    output.mkdir(exist_ok=False)
    specs, held = [], []
    dump(root / 'tasks.json', {'units': []})
    for i in sorted(wanted, key=lambda i: i not in previous):
        while shutil.disk_usage(root).free < 40 * 1024**3:
            dump(root / 'preparation-progress.json', {'phase': 'storage_wait', 'row': i, 'at': time.time()})
            time.sleep(10)
        try:
            item = previous[i] if i in previous else factory(rows[i], i, output, build_network='host')
            raw = Path(item['spec_path']).read_bytes()
            spec = json.loads(raw)
            assert spec['source']['kind'] == 'cli-gym' and spec['source']['row_index'] == i
            # Owned immutable dispatch copy. Original assets and images stay unchanged.
            path = output / f'spec-{i:04d}.json'
            path.write_bytes(raw)
            specs.append({'row_index': i, 'spec_path': str(path),
                          'spec_sha256': hashlib.sha256(raw).hexdigest()})
            dump(root / 'tasks.json', {'units': specs})
        except Exception as exc:
            held.append({'row_index': i, 'error_type': type(exc).__name__, 'message': str(exc)[:400]})
        dump(root / 'preparation-progress.json', {'prepared': len(specs), 'held': held, 'at': time.time()})
    dump(root / 'preparation-complete.json', {'prepared': len(specs), 'held': held,
         'selected': 100, 'replacement_tasks': 0, 'new_model_requests': 0})


def summary(root):
    results = [read(p) for p in (root / 'trials').glob('*/result.json')]
    valid = [x for x in results if x['valid']]
    dump(root / 'summary.json', {'at': time.time(), 'selected_tasks': 100,
         'attempted': len(results), 'valid_completed': len(valid),
         'full_success': sum(x['binary_score'] == 1 for x in valid),
         'valid_zero': sum(x['binary_score'] == 0 for x in valid),
         'execution_or_scoring_errors': len(results) - len(valid),
         'automatic_paid_retry': False, 'training_export': False})


async def trial(root, item, plan):
    name = f"row-{item['row_index']:04d}"
    out = root / 'trials' / name
    if out.exists() or (root / 'generation' / name).exists():
        return  # Exclusive attempt; never replay an uncertain or failed request.
    path = Path(item['spec_path'])
    assert hashlib.sha256(path.read_bytes()).hexdigest() == item['spec_sha256']
    spec = read(path)
    start = time.time()
    try:
        backend = CancellableQwenLLM(root / 'private.json',
            PinnedTokenizer(plan['tokenizer'], enable_thinking=False),
            root / 'generation' / name, thinking=False)
        receipt = await episode(spec, SimpleNamespace(tokenizer=plan['tokenizer'],
                                runtime_assets=Path(plan['runtime_assets'])),
                                out, 'evaluation', backend=backend)
        a, b = receipt['score']['reward'], receipt['fresh_score']['reward']
        if a not in (0, 1) or b not in (0, 1) or a != b:
            raise ValueError('Invalid or inconsistent fresh verifier scores')
        result = {'valid': True, 'binary_score': int(a == 1),
                  'interactions': receipt['executed_interactions']}
    except Exception as exc:
        out.mkdir(exist_ok=True, parents=True)
        result = {'valid': False, 'binary_score': None,
                  'error_type': type(exc).__name__, 'message': str(exc)[:400]}
    dump(out / 'result.json', {**result, 'row_index': item['row_index'],
         'model_id': plan['model'], 'elapsed_sec': time.time() - start,
         'task_spec_sha256': item['spec_sha256'], 'expert_reference': False,
         'candidate_selection': False, 'automatic_paid_retry': False})
    summary(root)


async def run(root):
    import fcntl
    lock = (root / 'controller.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    plan = read(root / 'plan.json')
    (root / 'trials').mkdir(exist_ok=True)
    scheduled, active = set(), {}
    canary = None
    while True:
        for name, task in list(active.items()):
            if task.poll() is not None:
                if not (root / 'trials' / f'row-{name:04d}' / 'result.json').exists():
                    dump(root / 'HOLD.json', {'reason': 'Worker exited without result', 'row': name})
                    return
                del active[name]
        units = read(root / 'tasks.json')['units'] if (root / 'tasks.json').exists() else []
        if canary is None and units:
            canary = units[0]['row_index']
            dump(root / 'canary-selection.json', units[0])
        result = root / 'trials' / f'row-{canary:04d}' / 'result.json' if canary is not None else None
        canary_done = result is not None and result.exists()
        if canary_done and not read(result)['valid']:
            dump(root / 'HOLD.json', {'reason': 'First real trial did not close normally; no bulk dispatch',
                                    'result_path': str(result), 'automatic_paid_retry': False})
            return
        for item in units:
            i = item['row_index']
            if i in scheduled or (not canary_done and i != canary):
                continue
            if len(active) >= plan['concurrency']:
                break
            if (root / 'STOP').exists() or shutil.disk_usage(root).free < 40 * 1024**3:
                break
            scheduled.add(i)
            with (root / f'trial-{i:04d}.log').open('x') as log:
                active[i] = subprocess.Popen([sys.executable, __file__, 'trial', str(root),
                                             '--row', str(i)], stdout=log, stderr=log)
            dump(root / f'launch-{i:04d}.json', {'pid': active[i].pid, 'row': i,
                 'at': time.time(), 'automatic_paid_retry': False})
        dump(root / 'health.json', {'at': time.time(), 'active': len(active),
             'scheduled': len(scheduled), 'prepared': len(units), 'concurrency': plan['concurrency']})
        if not active and ((root / 'STOP').exists() or
                ((root / 'preparation-complete.json').exists() and len(scheduled) == len(units))):
            summary(root)
            dump(root / 'finished.json', {'at': time.time(), 'automatic_paid_retry': False})
            return
        await asyncio.sleep(3)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('mode', choices=['prepare', 'run', 'trial'])
    parser.add_argument('root', type=Path)
    parser.add_argument('--row', type=int)
    args = parser.parse_args()
    if args.mode == 'prepare':
        prepare(args.root)
    elif args.mode == 'trial':
        item = next(x for x in read(args.root / 'tasks.json')['units'] if x['row_index'] == args.row)
        asyncio.run(trial(args.root, item, read(args.root / 'plan.json')))
    else:
        asyncio.run(run(args.root))
