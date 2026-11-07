"""Read-only CLI source census. Presence of a teacher conservatively claims a row."""
import hashlib
import json
from pathlib import Path
import re
import runpy
import sys
import time


def read(p):
    return json.loads(p.read_text())


def census(root, output):
    prior = Path('/mnt/ecs-tb4/cli-gym-scale-20261104')
    rows = {}
    for name, expected in read(prior / 'catalog/manifest.json')['pages'].items():
        p = Path(name)
        assert hashlib.sha256(p.read_bytes()).hexdigest() == expected
        rows.update({x['row_idx']: x['row'] for x in read(p)['rows']})
    fingerprint = runpy.run_path(str(Path(__file__).with_name('freeze.py')))['fingerprint']
    reserved = {x['row_index'] for x in read(root / 'split-v1/selection.json')['holdout']}
    manifest = read(root / 'campaign-sft/cli-gym/manifest.json')
    admitted = {int(re.search(r'row-(\d+)', Path(x['unit']).name)[1]) for x in manifest['records']}
    runs = [Path(x) for x in read(prior / 'campaign-progress.json')['runs']] + [root / 'production']
    paid_or_uncertain, attempted = set(), {}
    teacher_only = []
    for run in runs:
        for unit in (run / 'units').glob('cligym-row-*'):
            match = re.search(r'row-(\d+)', unit.name)
            if not match:
                continue
            i = int(match[1])
            attempted.setdefault(i, []).append(str(unit))
            if (unit / 'teacher').exists() or (unit / 'student').exists():
                paid_or_uncertain.add(i)
            receipt = unit / 'teacher/receipt.json'
            status = unit / 'status.json'
            if not receipt.exists() or (unit / 'student').exists() or not status.exists():
                continue
            teacher = read(receipt)
            if (read(status).get('phase') in ('hold', 'teacher_not_successful', 'completed')
                and teacher.get('normal_completed') and teacher.get('expert_admitted')
                and teacher.get('score', {}).get('reward') == teacher.get('fresh_score', {}).get('reward') == 1):
                teacher_only.append({'row_index': i, 'teacher': str(receipt),
                    'receipt_sha256': hashlib.sha256(receipt.read_bytes()).hexdigest()})
    excluded = {fingerprint(rows[i]) for i in paid_or_uncertain | reserved}
    unused = {}
    for i, row in sorted(rows.items()):
        key = fingerprint(row)
        if i not in reserved | paid_or_uncertain and key not in excluded:
            unused.setdefault(key, i)
    result = {'checked_at': time.time(), 'official_rows': len(rows), 'reserved_rows': len(reserved),
        'admitted_trajectories': len(manifest['records']), 'admitted_distinct_rows': len(admitted),
        'paid_or_uncertain_rows': len(paid_or_uncertain),
        'remaining_distinct_unpaid_contracts': len(unused),
        'unpaid_rows': [{'row_index': i, 'contract_sha256': key, 'previous_units': attempted.get(i, [])}
                        for key, i in unused.items()],
        'teacher_only_candidates_requiring_identity_and_runtime_admission': teacher_only,
        'new_model_requests': 0, 'automatic_paid_retries': 0,
        'interpretation': 'Unpaid candidates include broken or already-passing environments; not promised SFT yield.'}
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('unpaid_rows', 'teacher_only_candidates_requiring_identity_and_runtime_admission')}))


if __name__ == '__main__':
    census(Path(sys.argv[1]), Path(sys.argv[2]))
