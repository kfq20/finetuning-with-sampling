"""Repair preparation-only holds for the same frozen CLI-Gym task roster."""
import json
from pathlib import Path
import runpy
import shutil
import time

from compare import BASELINE, ROOT, sha
from run import dump, read

APT_FAILURES = {1531, 1549, 1554, 1561, 1566, 1567, 1576, 1606, 1618, 1627}
ORIGINAL_RECIPE_HOLDS = {1537, 1556, 1559, 1572, 1624}
PREPARE_MIN_FREE = 55 * 2**30


def main():
    out = ROOT / 'prepared-repairs'
    out.mkdir(exist_ok=False)
    factory = runpy.run_path(str(Path(__file__).parents[1] / 'cli-gym-pilot-20261104/prepare.py'))['prepare']
    tasks = read(ROOT / 'tasks.json')['units']
    original = read(ROOT / 'initial-preparation.json')
    repaired, held = [], []
    progress = ROOT / 'repair-progress.json'
    for failure in original['held']:
        row = failure['row_index']
        if row in ORIGINAL_RECIPE_HOLDS:
            held.append(failure)
            continue
        while shutil.disk_usage(ROOT).free < PREPARE_MIN_FREE:
            if (ROOT / 'STOP_PREPARATION').exists():
                return
            dump(progress, {'phase': 'storage_wait', 'row': row, 'repaired': repaired, 'held': held})
            time.sleep(15)
        if (ROOT / 'STOP_PREPARATION').exists():
            return
        dump(progress, {'phase': 'preparing', 'row': row, 'repaired': repaired, 'held': held})
        src = BASELINE / 'prepared' / f'row-{row:04d}' / 'original-row.json'
        try:
            built = factory(read(src), row, out, build_network='host',
                            repair_contract=True, apt_mirror=row in APT_FAILURES,
                            bash_build=row == 1577)
            spec_path = Path(built['spec_path'])
            assert read(spec_path)['source']['row_index'] == row
            item = {'row_index': row, 'spec_path': str(spec_path), 'spec_sha256': sha(spec_path)}
        except Exception as e:
            held.append({'row_index': row, 'error_type': type(e).__name__, 'message': str(e)[:350]})
            continue
        tasks.append(item)
        repaired.append(row)
        dump(ROOT / 'tasks.json', {'units': tasks})
    receipt = {'phase': 'completed', 'selected': 100, 'prepared': len(tasks), 'repaired': repaired,
               'held': held, 'replacement_tasks': 0, 'new_model_requests': 0}
    dump(progress, receipt)
    dump(ROOT / 'preparation-complete.json', receipt)
    print(json.dumps({'prepared': len(tasks), 'held': len(held), 'repaired': len(repaired)}))


if __name__ == '__main__':
    main()
