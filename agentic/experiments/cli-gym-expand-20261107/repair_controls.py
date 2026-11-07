"""Repair resource-only pre-model control holds; never replay a model attempt."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
from types import SimpleNamespace

from append_rewrite.terminus.cli_contract import bound_pytest_resources, PYTEST_RESOURCES
from append_rewrite.terminus.docker_world import checked
from append_rewrite.terminus.production import controls, dump, tree
from append_rewrite.terminus.protocol import digest


def read(path):
    return json.loads(path.read_text())


def unpaid_proof(root, index):
    prior = Path('/mnt/ecs-tb4/cli-gym-scale-20261104')
    runs = [Path(x) for x in read(prior / 'campaign-progress.json')['runs']]
    runs.append(root / 'production')
    proof = []
    for run in runs:
        for unit in (run / 'units').glob(f'*row-{index:04d}*'):
            if (unit / 'teacher').exists() or (unit / 'student').exists():
                raise ValueError('Historical model attempt exists; repair cannot replay it')
            status = unit / 'status.json'
            if not status.exists() or read(status)['phase'] != 'hold':
                raise ValueError('Original unit is not a closed pre-model hold')
            proof.append({'unit': str(unit), 'status_sha256': hashlib.sha256(status.read_bytes()).hexdigest(),
                          'teacher_directory_absent': True, 'student_directory_absent': True})
    if not proof:
        raise ValueError('Expected an original pre-model hold')
    return proof


def resource_image(image, output):
    assert re.fullmatch(r'sha256:[0-9a-f]{64}', image)
    build = output / 'resource-image'
    build.mkdir()
    dockerfile = ('FROM ' + image + '\nENV '
                  + ' '.join(k + '=' + v for k, v in PYTEST_RESOURCES.items()) + '\n')
    (build / 'Dockerfile').write_text(dockerfile)
    tag = 'append-rewrite/cligym-resource:' + hashlib.sha256(dockerfile.encode()).hexdigest()[:16]
    (build / 'build.log').write_bytes(checked('build', '--network', 'none', '-t', tag, str(build)))
    before = json.loads(checked('image', 'inspect', image))[0]
    after = json.loads(checked('image', 'inspect', tag))[0]
    assert before['RootFS'] == after['RootFS'], 'Resource adapter must not alter task files'
    for key in ['Cmd', 'Entrypoint', 'User', 'WorkingDir']:
        assert before['Config'].get(key) == after['Config'].get(key)
    dump(build / 'binding.json', {'original_image': image, 'image': after['Id'],
         'rootfs_unchanged': True, 'environment_patch': PYTEST_RESOURCES,
         'new_model_requests': 0})
    return after['Id']


def repair(root, spec_path, output, assets):
    original = read(spec_path)
    index = original['source']['row_index']
    proof = unpaid_proof(root, index)
    assert index not in {x['row_index'] for x in read(root / 'split-v1/selection.json')['holdout']}
    output.mkdir(parents=True, exist_ok=False)
    task = output / 'task'
    shutil.copytree(original['task_path'], task)
    cp = task / 'tests/contract.json'
    before = read(cp)
    assert before.get('explicit_pytest_argv'), 'Explicit frozen test list required'
    after = dict(before)
    original_logs = [read(Path(x['unit']) / 'controls/receipt.json').get('legal', {}).get(
        'details', {}).get('test_log', '') for x in proof
        if (Path(x['unit']) / 'controls/receipt.json').exists()]
    xdist = any('xdist-' in log for log in original_logs)
    after['explicit_pytest_argv'] = bound_pytest_resources(before['explicit_pytest_argv'], serial_xdist=xdist)
    assert after['test_ids'] == before['test_ids']
    dump(cp, after)
    # Aside from the wrapper, preserve every public instruction/test byte.
    actual = tree(task)
    diff = {name for name in set(actual) | set(original['task_manifest'])
            if actual.get(name) != original['task_manifest'].get(name)}
    assert diff == {'tests/contract.json'}, diff
    spec = {**original, 'unit_id': f'cligym-row-{index:04d}-resources-v1',
            'task_path': str(task), 'instruction_path': str(task / 'instruction.md'),
            'task_manifest': tree(task)}
    spec['template_id'] = resource_image(original['template_id'], output)
    spec.pop('identity', None)
    spec.pop('preflight_certificate', None)
    spec['identity'] = digest(spec)
    dump(output / 'spec.json', spec)
    dump(output / 'repair-proof.json', {'source_spec': str(spec_path),
         'source_spec_sha256': hashlib.sha256(spec_path.read_bytes()).hexdigest(),
         'unpaid_originals': proof, 'changed_files': sorted(diff),
         'original_test_ids': before['test_ids'], 'repaired_test_ids': after['test_ids'],
         'new_model_requests': 0, 'instruction_unchanged': True, 'xdist_serialized': xdist})
    controls(spec, SimpleNamespace(runtime_assets=assets), output / 'controls')
    receipt = read(output / 'controls/receipt.json')
    assert receipt['passed'] and receipt['initial']['reward'] == 0 and receipt['legal']['reward'] == 1
    unpaid_proof(root, index)  # Recheck before publishing a first-model admission.
    proof_path = output / 'repair-proof.json'
    return {'unit_id': spec['unit_id'], 'lane': 'shared', 'spec_path': str(output / 'spec.json'),
            'unpaid_repair_proof': str(proof_path),
            'unpaid_repair_proof_sha256': hashlib.sha256(proof_path.read_bytes()).hexdigest()}


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--root', type=Path, required=True)
    p.add_argument('--specs', type=Path, nargs='+', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--runtime-assets', type=Path, required=True)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False)
    ready, held = [], []
    for spec_path in a.specs:
        try:
            ready.append(repair(a.root, spec_path, a.output / spec_path.stem, a.runtime_assets))
        except Exception as exc:
            held.append({'source_spec': str(spec_path), 'error_type': type(exc).__name__, 'message': str(exc)[:400]})
        dump(a.output / 'plan.json', {'units': ready})
        dump(a.output / 'progress.json', {'ready': len(ready), 'held': held, 'new_model_requests': 0})
    dump(a.output / 'complete.json', {'ready': len(ready), 'held': held, 'new_model_requests': 0})
