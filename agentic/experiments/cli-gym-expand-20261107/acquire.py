"""One owned rolling acquisition controller, reusing the established production loop."""
import fcntl
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time

from append_rewrite.terminus.production import dump
from append_rewrite.terminus.lifecycle import retire_failed_workers


def read(path):
    return json.loads(path.read_text())


def partition_records(records, sources, prior_units):
    groups = {'cli-gym': [], 'swe-gym': []}
    for record in records:
        name = Path(record['unit']).name
        kind = 'cli-gym' if record['unit'] in prior_units else sources[name]
        groups[kind].append(record)
    return groups


def selected_model_arguments(root, arguments):
    """An old canary receipt must not override explicitly selected live routes."""
    selection = root / 'active_runtime_selection.json'
    selected = read(selection) if selection.exists() else {}
    result = list(arguments)
    for field, option in [('teacher_route_config', '--teacher-config'),
                          ('student_route_config', '--fleet-config')]:
        if selected.get(field):
            path = Path(selected[field])
            if not path.is_file():
                raise ValueError('Selected model config is absent; no fallback')
            result[result.index(option) + 1] = str(path)
    return result


class ObservedProcess:
    """Observe an original owner; never signal or relaunch it."""
    def __init__(self, receipt, completion):
        self.receipt, self.completion, self.returncode = receipt, completion, None

    def poll(self):
        p = Path('/proc') / str(self.receipt['pid']) / 'stat'
        fields = p.read_text().split(') ')[1].split() if p.exists() else None
        if fields and fields[19] == str(self.receipt['start_ticks']) and fields[0] != 'Z':
            return None
        self.returncode = 0 if self.completion.exists() else 1
        return self.returncode


def main(root):
    lock = (root / 'acquisition.lock').open('a+')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    source = Path(__file__).resolve().parents[3]
    prior = Path('/mnt/ecs-tb4/cli-gym-scale-20261104')
    goal = read(root / 'goal.json')
    selected = read(root / 'split-v1/selection.json')
    holdout = {x['row_index'] for x in selected['holdout']}
    eligible = {x['row_index'] for x in selected['acquisition_candidates']}
    canary_spec = root / 'repair-canary-v1/row-1517/spec.json'
    run = root / 'production'
    canary = run / 'units/cligym-row-1517'
    plan = root / 'acquisition-plan.json'
    complete = root / 'acquisition-complete.json'
    assert not complete.exists()
    handoff = {}
    if plan.exists():
        pointer = root / 'producer-handoff-selection.json'
        ref = read(pointer) if pointer.exists() else {'path': str(root / 'unpaid-build-handoff.json')}
        receipt = Path(ref['path'])
        if 'sha256' in ref:
            assert hashlib.sha256(receipt.read_bytes()).hexdigest() == ref['sha256']
        handoff = read(receipt)
        assert handoff.get('old_producer_exited') or handoff.get('old_producer_and_preparer_exited')
    baseline = read(prior / 'campaign-sft/manifest.json')
    prior_units = {x['unit'] for x in baseline['records']}
    targets = goal.get('targets_by_source', {'cli-gym': goal['target_total_valid_pairs']})
    assert set(targets) <= {'cli-gym', 'swe-gym'} and all(v > 0 for v in targets.values())
    original = (prior / 'campaign-sft/train.jsonl').read_bytes()
    assert hashlib.sha256(original).hexdigest() == baseline['train_sha256']
    assert len(baseline['records']) == goal['prior_valid_pairs'] == 531
    publish = runpy.run_path(str(source / 'agentic/experiments/cli-gym-scale-20261104/collect.py'))['publish']
    env = {**os.environ, 'PYTHONPATH': str(source / 'agentic/src'),
           'PYTHONDONTWRITEBYTECODE': '1',
           'DOCKER_HOST': 'unix:///mnt/ecs-tb4/cli-gym-pilot-20261104/runtime/docker.sock',
           'DOCKER_API_VERSION': '1.44', 'DOCKER_CONFIG': str(prior / 'docker-config'),
           'APPEND_REWRITE_STUDENT_POOL': str(root / 'student-pool'),
           'APPEND_REWRITE_SCORE_POOL': str(root / 'score-pool'),
           'APPEND_REWRITE_STUDENT_CAPACITY': '16', 'APPEND_REWRITE_SCORE_CAPACITY': '4',
           'APPEND_REWRITE_MIN_FREE_GIB': '40'}

    def launch(name, argv):
        with (root / (name + '.log')).open('xb') as log:
            child = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=subprocess.STDOUT)
        fields = (Path('/proc') / str(child.pid) / 'stat').read_text().split(') ')[1].split()
        dump(root / (name + '-launch.json'), {'pid': child.pid, 'start_ticks': fields[19],
             'argv': argv, 'source_root': str(source), 'started_at': time.time()})
        return child

    # Preparation is unpaid. The canary source row is never rebuilt/replayed.
    seed = read(plan)['units'] if plan.exists() else []
    prepared_ids = {read(Path(x['spec_path']))['source']['row_index'] for x in seed
                    if read(Path(x['spec_path']))['source']['kind'] == 'cli-gym'}
    indices = sorted(eligible - {1517} - prepared_ids)
    prep_root = root / 'repaired-acquisition-mirror'
    if handoff.get('retained_preparation_launch'):
        prep = ObservedProcess(read(Path(handoff['retained_preparation_launch'])), prep_root / 'complete.json')
    else:
        prep = launch('pool-mirror-preparation', [sys.executable,
        str(source / 'agentic/experiments/cli-gym-pilot-20261104/prepare.py'),
        '--rows', str(root / 'split-v1/acquisition-rows.json'), '--indices', *map(str, indices),
        '--output', str(prep_root), '--build-network', 'host', '--repair-contract',
        '--storage-root', str(root), '--min-free-gib', '40', '--apt-mirror'])
    dump(plan, {'units': seed})
    coordinator = (ObservedProcess(read(root / 'coordinator-launch.json'), run / 'coordinator-finished.json')
                   if (root / 'coordinator-launch.json').exists() else None)
    items = {x['unit_id']: x for x in seed}
    last_release = None
    exhausted_since = None
    while True:
        retire_failed_workers(run, [], root / 'failed-worker-retirements')
        status = read(canary / 'status.json')
        if coordinator is None:
            owner = read(root / 'model-canary-launch.json')
            proc = Path('/proc') / str(owner['pid']) / 'stat'
            fields = proc.read_text().split(') ')[1].split() if proc.exists() else None
            alive = fields and fields[19] == str(owner['start_ticks']) and fields[0] != 'Z'
            if not alive and status['phase'] not in ('hold', 'teacher_not_successful', 'completed'):
                dump(root / 'acquisition-hold.json', {'reason': 'canary_exited_without_closure', 'status': status})
                return
            if status['phase'] == 'hold':
                dump(root / 'acquisition-hold.json', {'reason': 'canary_execution_hold', 'status': status})
                return
            if status['phase'] == 'teacher_not_successful':
                dump(root / 'acquisition-hold.json', {'reason': 'canary_teacher_model_zero_not_retried'})
                return
            if status['phase'] == 'completed':
                receipt = read(canary / 'student/receipt.json')
                assert receipt['normal_completed']
                assert receipt['score']['reward'] in (0, 1) and receipt['fresh_score']['reward'] in (0, 1)
                args = read(root / 'model-canary-launch.json')['argv']
                tail = selected_model_arguments(root, args[args.index('--teacher-config'):])
                coordinator = launch('coordinator', [sys.executable, '-m',
                    'append_rewrite.terminus.production', 'batch', '--plan', str(plan),
                    '--discovery-summary', str(complete), '--output', str(run), '--workers', '16', *tail])
        candidates = [{'unit_id': 'cligym-row-1517', 'lane': 'shared', 'spec_path': str(canary_spec)}]
        if (prep_root / 'plan.json').exists():
            candidates += read(prep_root / 'plan.json')['units']
        registry_path = root / 'environment-repair-plans.json'
        registry = read(registry_path) if registry_path.exists() else {'open': False, 'plans': []}
        external = {}
        for extra in registry['plans']:
            path = Path(extra['plan'])
            assert path.resolve().is_relative_to(root.resolve())
            if path.exists():
                added = read(path)['units']
                if extra.get('source_manifest'):
                    manifest = Path(extra['source_manifest'])
                    assert manifest.resolve().is_relative_to(root.resolve())
                    assert hashlib.sha256(manifest.read_bytes()).hexdigest() == extra['source_manifest_sha256']
                    scope = read(manifest)
                    for item in added:
                        external[item['unit_id']] = scope
                candidates += added
        for item in candidates:
            if item['unit_id'] in items:
                assert items[item['unit_id']] == item
                continue
            spec = read(Path(item['spec_path']))
            if item['unit_id'] in external:
                scope = external[item['unit_id']]
                src = spec['source']
                assert src['kind'] == 'swe-gym' and src['split'] == 'train'
                assert src['dataset_revision'] == scope['revision']
                assert scope['tasks'][src['task_id']] == src['row_sha256']
                receipt = Path(item['spec_path']).parent / 'controls/receipt.json'
                controls = read(receipt)
                assert controls['passed'] and controls['initial']['reward'] == 0 and controls['legal']['reward'] == 1
                items[item['unit_id']] = item
                continue
            i = spec['source']['row_index']
            extra_scope = i in registry.get('extra_eligible_rows', [])
            assert (i in eligible or extra_scope) and i not in holdout and spec['solver_network'] == 'none'
            if extra_scope and i not in eligible:
                assert item.get('unpaid_repair_proof')
                assert spec['source']['kind'] == 'cli-gym' and spec['source']['dataset_revision'] == selected['revision']
            if item.get('unpaid_repair_proof'):
                proof_path = Path(item['unpaid_repair_proof'])
                assert hashlib.sha256(proof_path.read_bytes()).hexdigest() == item['unpaid_repair_proof_sha256']
                checker = runpy.run_path(str(source / 'agentic/experiments/cli-gym-expand-20261107/repair_controls.py'))['unpaid_proof']
                checker(root, i)
                grade = read(Path(item['spec_path']).parent / 'controls/receipt.json')
                assert grade['passed'] and grade['initial']['reward'] == 0 and grade['legal']['reward'] == 1
            items[item['unit_id']] = item
        dump(plan, {'units': list(items.values())})
        new = publish([run], root / 'new-sft')
        all_records = baseline['records'] + new['records']
        assert len({x['input_identity'] for x in all_records}) == len(all_records)
        groups = partition_records(all_records,
            {name: read(Path(item['spec_path']))['source']['kind'] for name, item in items.items()}, prior_units)
        counts = {kind: len(records) for kind, records in groups.items()}
        reached = all(counts[kind] >= target for kind, target in targets.items())
        dump(run / 'source-targets.json', {'targets': targets, 'counts': counts})
        if new['train_sha256'] != last_release:
            release = root / 'campaign-sft'
            release.mkdir(exist_ok=True)
            raw = original + (root / 'new-sft/train.jsonl').read_bytes()
            (release / 'train.jsonl.tmp').write_bytes(raw)
            (release / 'train.jsonl.tmp').replace(release / 'train.jsonl')
            dump(release / 'manifest.json', {**new, 'records': all_records,
                 'valid_trajectories': len(all_records), 'train_sha256': hashlib.sha256(raw).hexdigest(),
                 'supervised_tokens': sum(x['supervised_tokens'] for x in all_records),
                 'valid_by_source': counts, 'targets_by_source': targets})
            for kind, records in groups.items():
                dest = release / kind
                dest.mkdir(exist_ok=True)
                raw_group = b''.join((Path(x['unit']) / 'student/train.jsonl').read_bytes().rstrip() + b'\n' for x in records)
                (dest / 'train.jsonl.tmp').write_bytes(raw_group)
                (dest / 'train.jsonl.tmp').replace(dest / 'train.jsonl')
                dump(dest / 'manifest.json', {'source': kind, 'records': records,
                    'valid_trajectories': len(records), 'target': targets.get(kind),
                    'train_sha256': hashlib.sha256(raw_group).hexdigest()})
            last_release = new['train_sha256']
        phase = 'canary_running' if coordinator is None else 'rolling_acquisition'
        health_path = run / 'runtime-health.json'
        health = read(health_path) if health_path.exists() else {}
        if health.get('phase') in ('provider_hold', 'awaiting_supply'):
            phase = health['phase']
        if reached:
            dump(run / 'STOP_PROVIDER', {'reason': 'target_reached_drain', 'new_model_requests': 0})
            phase = 'target_reached_drain'
        elif shutil.disk_usage(root).free < 40 * 1024**3:
            phase = 'storage_hold'
        extras_done = all(Path(x['complete']).exists() for x in registry['plans'])
        no_dispatch = (health.get('active_workers') == 0 and health.get('queued') == 0
                       and phase not in ('storage_hold', 'provider_hold'))
        all_manufacturing_done = (prep_root / 'complete.json').exists() and extras_done
        if no_dispatch and all_manufacturing_done and not health.get('provider_holds'):
            exhausted_since = exhausted_since or time.time()
            phase = 'awaiting_supply'
            if time.time() - exhausted_since >= 300:
                phase = 'blocked_supply'
                dump(root / 'acquisition-hold.json', {'reason': 'supply_exhausted',
                     'valid_pairs': len(all_records), 'since': exhausted_since,
                     'benchmark_retry': False})
                dump(complete, {'plan_sha256': hashlib.sha256(plan.read_bytes()).hexdigest(),
                     'reason': 'supply_exhausted_not_target_complete'})
        else:
            exhausted_since = None
        if ((prep_root / 'complete.json').exists() and extras_done and not registry['open']) or (run / 'STOP_PROVIDER').exists():
            dump(complete, {'plan_sha256': hashlib.sha256(plan.read_bytes()).hexdigest()})
        if prep.poll() is not None and not (prep_root / 'complete.json').exists():
            dump(root / 'acquisition-hold.json', {'reason': 'preparation_exited_without_closure'})
            dump(run / 'STOP_PROVIDER', {'reason': 'preparation_exited_without_closure', 'new_model_requests': 0})
            dump(complete, {'plan_sha256': hashlib.sha256(plan.read_bytes()).hexdigest()})
        dump(root / 'acquisition-progress.json', {'checked_at': time.time(), 'phase': phase,
             'active_workers': health.get('active_workers'), 'queued_units': health.get('queued'),
             'provider_holds': health.get('provider_holds', []),
             'valid_pairs': len(all_records), 'valid_by_source': counts, 'targets_by_source': targets,
             'new_pairs': len(new['records']), 'target': sum(targets.values()),
             'published_tasks': len(items), 'worker_capacity': 16, 'score_capacity': 4,
             'heldout_tasks': 100, 'automatic_paid_retry': False})
        if coordinator is not None and coordinator.poll() is not None:
            dump(root / 'acquisition-finished.json', {'returncode': coordinator.returncode,
                 'valid_pairs': len(all_records), 'target_reached': reached})
            return
        time.sleep(15)


if __name__ == '__main__':
    main(Path(sys.argv[1]))
