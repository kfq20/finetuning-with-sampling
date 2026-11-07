"""Official SWE-Gym train source -> existing paired native production protocol.

No solver requests. Keep all published required tests, private patches, pinned
images and initial0/gold1 controls. Malformed or unavailable cases stay held.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import shlex
import shutil
import tarfile
import time
from types import SimpleNamespace

from append_rewrite.terminus.cli_contract import resolve_selectors, test_roots, bound_pytest_resources
from append_rewrite.terminus.docker_world import DockerWorld, checked
from append_rewrite.terminus.production import controls, tree, dump
from append_rewrite.terminus.protocol import digest


def row_sha(row):
    return hashlib.sha256(json.dumps(row, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def prepare(row, revision, output, assets, *, episode_timeout_sec=3000, repair_pytest_snail=False):
    if type(episode_timeout_sec) is not int or episode_timeout_sec <= 0:
        raise ValueError("Positive prospective episode timeout required")
    name = row['instance_id']
    unit = output / name
    unit.mkdir()
    dump(unit / 'source-row.json', row)
    required = list(dict.fromkeys(row['FAIL_TO_PASS'] + row['PASS_TO_PASS']))
    if not required or not row['FAIL_TO_PASS'] or any('::' not in n for n in required):
        raise ValueError('No supported exact pytest requirements')
    image = 'xingyaoww/sweb.eval.x86_64.' + name.replace('__', '_s_').lower()
    (unit / 'pull.log').write_bytes(checked('pull', image, timeout=900))
    info = json.loads(checked('image', 'inspect', image))[0]
    task = unit / 'task'
    tests = task / 'tests'
    tests.mkdir(parents=True)
    solution = task / 'solution'
    solution.mkdir()
    (task / 'instruction.md').write_text(
        'The repository is at /testbed. Resolve the following issue and preserve unrelated behavior.\n\n'
        + row['problem_statement'] + '\n')
    script = 'set -euo pipefail\ncd /testbed\nprintf %s ' + shlex.quote(row['patch']) + ' > /tmp/owned-gold.patch\ngit apply /tmp/owned-gold.patch\n'
    (solution / 'solve.sh').write_text(script)
    gold = DockerWorld(info['Id'], 'swegym-manufacture-gold')
    try:
        snail = None
        if repair_pytest_snail:
            from append_rewrite.terminus.pytest_snail_compat import discover_and_apply
            snail = discover_and_apply(gold)
        from append_rewrite.terminus.source_patch import initialize_repo
        initial = gold.run('git status --porcelain', cwd='/testbed')
        baseline = initialize_repo(gold, {'source_base_commit': row['base_commit']})
        dump(unit / 'initial-state.json', {'original_base_commit': row['base_commit'],
             'initial_tracked_and_untracked_status': initial.stdout, 'frozen_baseline_commit': baseline})
        gold.write('/tmp/owned-gold.patch', row['patch'])
        gold.write('/tmp/owned-test.patch', row['test_patch'])
        q = gold.run('git apply /tmp/owned-gold.patch && git apply /tmp/owned-test.patch', cwd='/testbed')
        if q.exit_code:
            raise ValueError('Published source/test patch did not apply')
        collector = ('import json,sys,os\nfrom pathlib import Path\nsys.path.insert(0,os.getcwd())\nimport pytest\n'
                     'class Capture:\n def pytest_collection_finish(self,session):\n'
                     '  Path("/tmp/owned-collected.json").write_text(json.dumps([i.nodeid for i in session.items]))\n'
                     'raise SystemExit(pytest.main(sys.argv[1:],plugins=[Capture()]))\n')
        gold.write('/tmp/owned-collect.py', collector)
        parents = sorted({n.split('::')[0] for n in required})
        q = gold.run(shlex.join(['/usr/bin/env', 'PYTEST_XDIST_AUTO_NUM_WORKERS=1',
                    'OPENBLAS_NUM_THREADS=1', '/opt/miniconda3/envs/testbed/bin/python',
                    '/tmp/owned-collect.py', '--collect-only', '-q', *parents]), cwd='/testbed', timeout=600)
        (unit / 'collection.log').write_text(q.stdout + q.stderr)
        if q.exit_code:
            raise ValueError('Gold selected tests could not be collected')
        collected = json.loads(gold.read('/tmp/owned-collected.json'))
        ids = resolve_selectors(required, collected)
        f2p = resolve_selectors(row['FAIL_TO_PASS'], collected)
        paths = test_roots(ids)
        archive = checked('exec', gold.sandbox_id, 'tar', 'czf', '-', '-C', '/testbed', *paths)
        # Validate archive membership before it becomes a frozen grading asset.
        with tarfile.open(fileobj=io.BytesIO(archive)) as t:
            for m in t.getmembers():
                p = Path(m.name)
                if p.is_absolute() or '..' in p.parts or m.issym() or m.islnk():
                    raise ValueError('Unsupported private test archive entry')
        (tests / 'original-tests.tgz').write_bytes(archive)
    finally:
        gold.kill()
    argv = bound_pytest_resources(['/opt/miniconda3/envs/testbed/bin/python', '-m', 'pytest',
             '--disable-warnings', '--color=no', '--tb=no', '--verbose', *ids])
    dump(tests / 'contract.json', {'test_ids': ids, 'frozen_test_paths': paths,
         'explicit_pytest_argv': argv, 'timeout_sec': 3000,
         'original_required_tests': required, 'resolved_fail_to_pass': f2p})
    (tests / 'run-original.sh').write_text('# Private exact-node evaluator; see contract.json\n')
    state = unit / 'state'
    state.mkdir()
    spec = {'unit_id': 'swegym-' + name, 'environment_backend': 'docker',
            'template_id': info['Id'], 'gold_template_id': info['Id'],
            'source_registry_image': info['RepoDigests'][0], 'capture_format': 'git-patch',
            'source_base_commit': row['base_commit'], 'source_baseline_commit': baseline,
            'task_path': str(task), 'instruction_path': str(task / 'instruction.md'),
            'task_manifest': tree(task), 'state_path': str(state), 'state_manifest': {},
            'cwd': '/testbed', 'artifacts': ['/testbed/'], 'restore_reset_paths': ['/app/'],
            'solver_network': 'none', 'healthcheck': 'test -d /testbed/.git',
            'legal_control_script': str(solution / 'solve.sh'), 'episode_timeout_sec': episode_timeout_sec,
            'source': {'kind': 'swe-gym', 'split': 'train', 'dataset_revision': revision,
                       'task_id': name, 'row_sha256': row_sha(row)}}
    if snail:
        spec['pytest_snail_compat'] = snail
    spec['identity'] = digest(spec)
    dump(unit / 'spec.json', spec)
    controls(spec, SimpleNamespace(runtime_assets=assets), unit / 'controls')
    receipt = json.loads((unit / 'controls/receipt.json').read_text())
    if not receipt['passed'] or not any(receipt['initial']['details']['statuses'].get(n) == 'FAILED' for n in f2p):
        raise ValueError('Original bug is not a demonstrated failing requirement')
    return {'unit_id': spec['unit_id'], 'lane': 'shared', 'spec_path': str(unit / 'spec.json')}


def main(a):
    from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
    workers = getattr(a, 'workers', 1)
    horizon = getattr(a, 'episode_timeout_sec', 3000)
    if type(workers) is not int or workers < 1 or type(horizon) is not int or horizon < 1:
        raise ValueError('Positive preparation capacity and episode horizon required')
    rows = json.loads(a.rows.read_text())
    scope = json.loads(a.scope.read_text())
    allowed = scope['tasks']
    rows = [r for r in rows if r['instance_id'] in allowed]
    repos = ['pydantic/pydantic', 'bokeh/bokeh', 'facebookresearch/hydra',
             'python/mypy', 'conan-io/conan', 'dask/dask', 'getmoto/moto',
             'iterative/dvc', 'pandas-dev/pandas', 'modin-project/modin', 'Project-MONAI/MONAI']
    rows.sort(key=lambda r: (repos.index(r['repo']) if r['repo'] in repos else len(repos), r['repo'],
                            len(r['FAIL_TO_PASS']) + len(r['PASS_TO_PASS']), r['instance_id']))
    a.output.mkdir(exist_ok=True)
    plan = json.loads((a.output / 'plan.json').read_text())['units'] if (a.output / 'plan.json').exists() else []
    held = json.loads((a.output / 'progress.json').read_text()).get('held', []) if (a.output / 'progress.json').exists() else []
    seen = {r['task_id'] for r in held}
    pending, cursor = {}, 0

    def manufacture(row):
        if row_sha(row) != allowed[row['instance_id']]:
            raise ValueError('Source row drift')
        return prepare(row, scope['revision'], a.output, a.assets, episode_timeout_sec=horizon,
                       repair_pytest_snail=getattr(a, 'repair_pytest_snail', False))

    def progress(phase):
        dump(a.output / 'progress.json', {'phase': phase, 'ready': len(plan), 'held': held,
             'preparation_workers': workers, 'active_tasks': sorted(pending.values())})

    with ThreadPoolExecutor(workers) as pool:
        while True:
            live = json.loads((a.root / 'acquisition-progress.json').read_text())
            reached = live.get('valid_by_source', {}).get('swe-gym', 0) >= live.get('targets_by_source', {}).get('swe-gym', 1000)
            queued = sum(not (a.root / 'production/units' / item['unit_id']).exists() for item in plan)
            free = shutil.disk_usage(a.root).free
            already = {z['unit_id'] for z in json.loads((a.root / 'acquisition-plan.json').read_text())['units']}
            while (not reached and cursor < len(rows) and len(pending) < workers
                   and queued + len(pending) < 16 and free >= 40 * 1024**3):
                row = rows[cursor]
                cursor += 1
                name = row['instance_id']
                uid = 'swegym-' + name
                if (name in seen or (a.output / name).exists() or uid in already
                        or (a.root / 'production/units' / uid).exists()):
                    continue
                seen.add(name)
                pending[pool.submit(manufacture, row)] = name
            if not pending:
                if reached or cursor == len(rows):
                    dump(a.output / 'complete.json', {'target_reached': reached, 'ready': len(plan), 'held': held})
                    return
                progress('storage_hold' if free < 40 * 1024**3 else 'queue_full')
                time.sleep(10)
                continue
            progress('manufacturing')
            done, _ = wait(pending, timeout=2, return_when=FIRST_COMPLETED)
            for future in done:
                name = pending.pop(future)
                try:
                    plan.append(future.result())
                except Exception as error:
                    held.append({'task_id': name, 'type': type(error).__name__, 'message': str(error)[:300]})
                dump(a.output / 'plan.json', {'units': plan})
            progress('manufacturing')


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    for key in ['root', 'rows', 'scope', 'output', 'assets']:
        p.add_argument('--' + key, type=Path, required=True)
    p.add_argument('--episode-timeout-sec', type=int, default=3000)
    p.add_argument('--workers', type=int, default=1)
    p.add_argument('--repair-pytest-snail', action='store_true')
    main(p.parse_args())
