"""Select first-model-eligible control holds, excluding paid semantic duplicates."""
import json
from pathlib import Path
import re
import runpy
import sys
from collections import defaultdict


def read(p):
    return json.loads(p.read_text())


def main(root):
    old = Path('/mnt/ecs-tb4/cli-gym-scale-20261104')
    fingerprint = runpy.run_path(str(Path(__file__).with_name('freeze.py')))['fingerprint']
    rows = {}
    for p in (old / 'catalog').glob('rows-*.json'):
        rows.update({x['row_idx']: x['row'] for x in read(p)['rows']})
    by_index = defaultdict(list)
    for run in [*(Path(x) for x in read(old / 'campaign-progress.json')['runs']), root / 'production']:
        for unit in (run / 'units').glob('*'):
            match = re.search(r'row-(\d+)', unit.name)
            if match:
                by_index[int(match.group(1))].append((run, unit))
    paid = {i for i, units in by_index.items()
            if any((u / 'teacher').exists() or (u / 'student').exists() for _, u in units)}
    excluded = {fingerprint(rows[i]) for i in paid}
    heldout = {x['row_index'] for x in read(root / 'split-v1/selection.json')['holdout']}
    selection = []
    for i, units in sorted(by_index.items()):
        if i in paid or i in heldout or fingerprint(rows[i]) in excluded:
            continue
        if any(not (u / 'status.json').exists() or read(u / 'status.json')['phase'] != 'hold'
               for _, u in units):
            continue
        if any((u / 'controls/receipt.json').exists()
               and read(u / 'controls/receipt.json').get('initial', {}).get('reward') == 1
               for _, u in units):
            continue
        # Frozen dispatcher copy, not an inferred or reconstructed old input.
        specs = [run / 'specs' / (u.name + '.json') for run, u in reversed(units)]
        specs = [p for p in specs if p.exists()]
        if not specs:
            continue
        selection.append({'row_index': i, 'spec_path': str(specs[0]),
                          'contract_sha256': fingerprint(rows[i])})
        excluded.add(fingerprint(rows[i]))
    dest = root / 'legacy-control-repair-selection.json'
    assert not dest.exists()
    dest.write_text(json.dumps({'rows': selection, 'new_model_requests': 0,
        'policy': 'First model only after new controls; never replay a paid or semantically identical attempt'}, indent=2))
    print(json.dumps({'selected': len(selection), 'rows': [x['row_index'] for x in selection]}))


if __name__ == '__main__':
    main(Path(sys.argv[1]))
