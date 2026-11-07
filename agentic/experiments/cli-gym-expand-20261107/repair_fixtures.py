"""Preserve declared task data while restoring immutable verifier assets."""
import argparse
import copy
import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import shlex
import shutil
import tarfile
from types import SimpleNamespace

from append_rewrite.terminus.docker_world import DockerWorld, checked
from append_rewrite.terminus.production import controls, dump, tree
from append_rewrite.terminus.protocol import digest
from repair_controls import unpaid_proof


def read(path):
    return json.loads(path.read_text())


def entries(raw):
    result = {}
    with tarfile.open(fileobj=io.BytesIO(raw), mode='r:gz') as source:
        for item in source.getmembers():
            name = str(PurePosixPath(item.name))
            parts = PurePosixPath(name).parts
            if not parts or parts[0] != 'tests' or '..' in parts or item.issym() or item.islnk():
                raise ValueError('Unsupported test archive path or link')
            if '__pycache__' in parts or '.pytest_cache' in parts or name.endswith('.pyc'):
                continue
            if not (item.isfile() or item.isdir()):
                raise ValueError('Unsupported test archive entry')
            result[name] = (copy.copy(item), source.extractfile(item).read() if item.isfile() else None)
    return result


def frozen_partition(names, mutable):
    """Coalesce immutable subtrees without deleting editable task fixtures."""
    result = []
    def visit(path):
        if path in mutable:
            return
        if not any(x.startswith(path + '/') for x in mutable):
            result.append(path)
            return
        children = sorted({path + '/' + x[len(path) + 1:].split('/')[0]
                           for x in names if x.startswith(path + '/')})
        for child in children:
            visit(child)
    visit('tests')
    assert all(not (m == p or m.startswith(p + '/')) for m in mutable for p in result)
    return result


def repair(root, spec_path, output, assets):
    old = read(spec_path)
    index = old['source']['row_index']
    proof = unpaid_proof(root, index)
    assert index not in {x['row_index'] for x in read(root / 'split-v1/selection.json')['holdout']}
    old_archive = Path(old['task_path']) / 'tests/original-tests.tgz'
    before = entries(old_archive.read_bytes())
    healthy = DockerWorld(old['gold_template_id'], 'fixture-reference-audit')
    try:
        gold_raw = checked('exec', healthy.sandbox_id, 'tar', 'czf', '-', '-C', '/testbed', 'tests')
    finally:
        healthy.kill()
    gold = entries(gold_raw)
    changed = {x for x in set(before) | set(gold) if before.get(x, (None, None))[1] != gold.get(x, (None, None))[1]}
    if not changed:
        raise ValueError('No damaged task fixture found in verifier snapshot')
    rows = {x['row_idx']: x['row'] for p in Path('/mnt/ecs-tb4/cli-gym-scale-20261104/catalog').glob('rows-*.json')
            for x in read(p)['rows']}
    recipe = rows[index]['dockerfile']
    allowed = {'.dbc', '.kcd', '.arxml', '.xml', '.csv', '.json', '.yaml', '.yml', '.txt', '.npy'}
    for name in changed:
        if PurePosixPath(name).suffix not in allowed or '/testbed/' + name not in recipe:
            raise ValueError('Difference is not an explicitly declared operational data fixture: ' + name)
    output.mkdir(parents=True, exist_ok=False)
    task = output / 'task'
    shutil.copytree(old['task_path'], task)
    archive = task / 'tests/original-tests.tgz'
    with tarfile.open(archive, 'w:gz') as target:
        for name, (item, raw) in gold.items():
            if name not in changed:
                target.addfile(item, io.BytesIO(raw) if raw is not None else None)
    contract = read(task / 'tests/contract.json')
    argv = contract.get('explicit_pytest_argv') or [
        '/opt/miniconda3/envs/testbed/bin/python', '-m', 'pytest', '--disable-warnings',
        '--color=no', '--tb=no', '--verbose', *contract['test_ids']]
    source_script = task / 'tests/run-original.sh'
    shutil.copy2(source_script, task / 'tests/source-run-original.sh')
    script = ['#!/bin/bash', 'set -euo pipefail', 'cd /testbed',
              'stash=$(mktemp -d /tmp/cligym-graded-data.XXXXXX)', 'trap \'rm -rf -- "$stash"\' EXIT']
    for name in sorted(changed):
        q = shlex.quote(name)
        script += [f'test ! -L {q}', f'if [ -e {q} ]; then test -f {q}; mkdir -p "$stash"/{shlex.quote(str(PurePosixPath(name).parent))}; cp -p -- {q} "$stash"/{q}; fi']
    script += ['rm -rf -- /testbed/tests', 'tar xzf /tests/original-tests.tgz -C /testbed']
    for name in sorted(changed):
        q = shlex.quote(name)
        script += [f'if [ -f "$stash"/{q} ]; then mkdir -p {shlex.quote(str(PurePosixPath(name).parent))}; cp -p -- "$stash"/{q} {q}; fi']
    script.append(shlex.join(argv))
    source_script.write_text('\n'.join(script) + '\n')
    original_ids = list(contract['test_ids'])
    contract.update(frozen_test_paths=frozen_partition(set(gold), changed),
                    explicit_pytest_argv=['/bin/bash', '/tests/run-original.sh'],
                    mutable_task_data=sorted(changed))
    assert contract['test_ids'] == original_ids
    dump(task / 'tests/contract.json', contract)
    spec = {**old, 'unit_id': f'cligym-row-{index:04d}-fixtures-v1', 'task_path': str(task),
            'instruction_path': str(task / 'instruction.md'), 'task_manifest': tree(task)}
    spec.pop('identity', None); spec.pop('preflight_certificate', None)
    spec['identity'] = digest(spec)
    dump(output / 'spec.json', spec)
    dump(output / 'repair-proof.json', {'source_spec': str(spec_path), 'unpaid_originals': proof,
         'source_spec_sha256': hashlib.sha256(spec_path.read_bytes()).hexdigest(),
         'mutable_task_data': sorted(changed), 'all_other_noncache_test_asset_bytes_unchanged': True,
         'required_test_ids_unchanged': True, 'new_model_requests': 0})
    controls(spec, SimpleNamespace(runtime_assets=assets), output / 'controls')
    cr = read(output / 'controls/receipt.json')
    assert cr['passed'] and cr['initial']['reward'] == 0 and cr['legal']['reward'] == 1
    mutations = {}
    for name in ['missing_task_data', 'test_code_bypass']:
        sb = DockerWorld(old['gold_template_id'] if name == 'missing_task_data' else old['template_id'], name)
        try:
            if name == 'missing_task_data':
                change = sb.run('rm -f -- ' + shlex.quote('/testbed/' + sorted(changed)[0]))
            else:
                change = sb.run('find /testbed/tests -name "test_*.py" -exec sh -c \'echo "def test_fake(): assert True" > "$1"\' _ {} \\;')
            assert change.exit_code == 0, 'Mutation was not applied'
            mutations[name] = sb.grade(task)
            assert mutations[name]['reward'] == 0 and mutations[name]['details']['canary_expected_failure'], name
        finally:
            sb.kill()
    dump(output / 'mutation-controls.json', mutations)
    unpaid_proof(root, index)
    pp = output / 'repair-proof.json'
    return {'unit_id': spec['unit_id'], 'lane': 'shared', 'spec_path': str(output / 'spec.json'),
            'unpaid_repair_proof': str(pp), 'unpaid_repair_proof_sha256': hashlib.sha256(pp.read_bytes()).hexdigest()}


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--root', type=Path, required=True); p.add_argument('--specs', type=Path, nargs='+', required=True)
    p.add_argument('--output', type=Path, required=True); p.add_argument('--runtime-assets', type=Path, required=True)
    a = p.parse_args(); a.output.mkdir(parents=True, exist_ok=False)
    ready, held = [], []
    for sp in a.specs:
        try:
            ready.append(repair(a.root, sp, a.output / sp.stem, a.runtime_assets))
        except Exception as exc:
            held.append({'source_spec': str(sp), 'error_type': type(exc).__name__, 'message': str(exc)[:400]})
        dump(a.output / 'plan.json', {'units': ready})
        dump(a.output / 'progress.json', {'ready': len(ready), 'held': held, 'new_model_requests': 0})
    dump(a.output / 'complete.json', {'ready': len(ready), 'held': held, 'new_model_requests': 0})
