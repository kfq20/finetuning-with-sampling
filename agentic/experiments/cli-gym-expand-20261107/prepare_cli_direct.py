"""CLI-only direct Docker supply. No gold/NOP/mutation calibration or paid retries."""
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import sys
import time

from append_rewrite.terminus.docker_world import checked, DockerWorld
from append_rewrite.terminus.production import dump
from append_rewrite.terminus.protocol import digest


def read(path):
    return json.loads(path.read_text())


def main(root, output):
    output.mkdir(parents=True, exist_ok=False)
    here = Path(__file__).parent
    census = runpy.run_path(str(here / 'census_cli_supply.py'))['census']
    census(root, output / 'census.json')
    candidates = read(output / 'census.json')['unpaid_rows']
    prior = Path('/mnt/ecs-tb4/cli-gym-scale-20261104')
    rows = {}
    for name, checksum in read(prior / 'catalog/manifest.json')['pages'].items():
        page = Path(name)
        assert hashlib.sha256(page.read_bytes()).hexdigest() == checksum
        rows.update({x['row_idx']: x['row'] for x in read(page)['rows']})
    prepare = runpy.run_path(str(here.parent / 'cli-gym-pilot-20261104/prepare.py'))['prepare']
    # Use already-built immutable packages first; no per-case repair work.
    existing = {}
    for base in [prior, root]:
        for path in base.rglob('spec.json'):
            if '/runtime/' in str(path) or '/support/' in str(path):
                continue
            try:
                spec = read(path)
                if spec.get('source', {}).get('kind') == 'cli-gym':
                    existing.setdefault(spec['source']['row_index'], path)
            except (OSError, ValueError, KeyError):
                continue
    candidates.sort(key=lambda x: x['row_index'] not in existing)
    plan, held = [], []
    dump(output / 'plan.json', {'units': []})
    for candidate in candidates:
        i = candidate['row_index']
        # Never launch again after any historical teacher/student attempt.
        if any((Path(p) / role).exists() for p in candidate['previous_units'] for role in ['teacher', 'student']):
            raise ValueError('Paid ownership changed after census')
        while True:
            pending = sum(not (root / 'production/units' / x['unit_id']).exists() for x in plan)
            if pending < 8 and shutil.disk_usage(root).free >= 40 * 1024**3:
                break
            dump(output / 'progress.json', {'published': len(plan), 'held': held,
                 'phase': 'queue_or_storage_wait', 'checked_at': time.time()})
            time.sleep(10)
        try:
            if i in existing:
                spec = read(existing[i])
                checked('image', 'inspect', spec['template_id'])
            else:
                built = prepare(rows[i], i, output, build_network='host')
                spec = read(Path(built['spec_path']))
            world = DockerWorld(spec['template_id'], 'cli-direct-start-smoke')
            try:
                result = world.run('true', timeout=30)
                if result.exit_code:
                    raise RuntimeError('Docker startup smoke failed')
            finally:
                world.kill()
            spec.update(unit_id=f'cligym-row-{i:04d}-buildonly-v1', preflight_mode='cli-build-only')
            spec.pop('control_certificate', None)
            spec['identity'] = digest({k: v for k, v in spec.items() if k != 'identity'})
            path = output / f'direct-{i:04d}.json'
            dump(path, spec)
            plan.append({'unit_id': spec['unit_id'], 'lane': 'shared', 'spec_path': str(path)})
            dump(output / 'plan.json', {'units': plan})
        except Exception as exc:
            held.append({'row_index': i, 'error_type': type(exc).__name__, 'message': str(exc)[:300]})
        dump(output / 'progress.json', {'published': len(plan), 'held': held,
             'phase': 'preparing', 'checked_at': time.time(), 'calibration_performed': False})
    dump(output / 'complete.json', {'published': len(plan), 'held': held, 'new_model_requests': 0})


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]))
