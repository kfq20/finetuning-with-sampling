"""Freeze an internal holdout and prospective acquisition inventory; no inference."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def read(path):
    return json.loads(path.read_text())


def fingerprint(row):
    # Exclude task names/author metadata: bind the actual task, fault and grader.
    instruction = row['task_yaml'].partition('instruction: |')[2]
    instruction = re.split(r'\nauthor_(?:email|name):', instruction, maxsplit=1)[0]
    parts = [instruction.strip(), row['dockerfile'].strip(), row['run_tests'].strip()]
    return sha(json.dumps(parts, ensure_ascii=False).encode())


def freeze(source, output):
    assert not output.exists(), 'Frozen selection must not be overwritten'
    catalog = read(source / 'catalog/manifest.json')
    rows = {}
    for name, expected in catalog['pages'].items():
        p = Path(name)
        assert sha(p.read_bytes()) == expected
        rows.update({x['row_idx']: x['row'] for x in read(p)['rows']})
    assert len(rows) == catalog['rows'] == 1655
    prior = read(source / 'campaign-progress.json')
    claimed, trained = set(), set()
    for run in prior['runs']:
        for p in (Path(run) / 'units').glob('*'):
            match = re.search(r'row-(\d+)', p.name)
            if match:
                claimed.add(int(match.group(1)))
    manifest = read(source / 'campaign-sft/manifest.json')
    assert sha((source / 'campaign-sft/train.jsonl').read_bytes()) == manifest['train_sha256']
    for record in manifest['records']:
        trained.add(int(re.search(r'row-(\d+)', Path(record['unit']).name).group(1)))
    assert trained <= claimed
    # Exclude identical task contracts to ANY historically dispatched source row.
    old_contracts = {fingerprint(rows[i]) for i in claimed}
    candidates, seen = [], set(old_contracts)
    for i, row in sorted(rows.items()):
        key = fingerprint(row)
        if i not in claimed and key not in seen:
            candidates.append(i)
            seen.add(key)
    # Tail was never included in preparation or acquisition. Outcome-blind order.
    fresh = [i for i in candidates if i >= prior['next_source_offset']]
    fresh.sort(key=lambda i: sha(f'cli-gym-holdout-v1-seed42:{i}'.encode()))
    assert len(fresh) >= 100
    holdout = set(fresh[:100])
    acquire = set(candidates) - holdout
    assert not (holdout & acquire or holdout & claimed or acquire & claimed)

    def entry(i):
        row = rows[i]
        return {'row_index': i, 'task_id': row['task_id'],
                'contract_sha256': fingerprint(row),
                'row_sha256': sha(json.dumps(row, sort_keys=True).encode()),
                'base_image': re.search(r'^FROM\s+(\S+)', row['dockerfile'], re.M).group(1),
                'previously_preparation_scanned': i < prior['next_source_offset']}

    result = {'created_at': datetime.now(timezone.utc).isoformat(),
              'revision': catalog['revision'], 'source_pool': len(rows),
              'existing_sft': len(trained), 'previously_claimed_distinct': len(claimed),
              'holdout': [entry(i) for i in sorted(holdout)],
              'acquisition_candidates': [entry(i) for i in sorted(acquire)],
              'target_additional_admitted_pairs': 531,
              'target_total_admitted_pairs': len(trained) + 531,
              'new_model_requests': 0,
              'official_split': 'train', 'our_split': 'internal-heldout-test',
              'policy': 'Do not train on holdout; no failed paid task replay; no outcome-based test replacement.'}
    output.mkdir(parents=True)
    (output / 'selection.json').write_text(json.dumps(result, indent=2) + '\n')
    for name, indices in [('holdout', holdout), ('acquisition', acquire)]:
        (output / f'{name}-rows.json').write_text(json.dumps(
            {'rows': [{'row_idx': i, 'row': rows[i]} for i in sorted(indices)]}) + '\n')
    summary = {k: v for k, v in result.items() if k not in ('holdout', 'acquisition_candidates')}
    summary.update(holdout_count=len(holdout), acquisition_candidate_count=len(acquire),
                   fresh_unprepared_acquisition=sum(i >= prior['next_source_offset'] for i in acquire),
                   heldout_projects=dict(Counter(entry(i)['base_image'] for i in holdout)),
                   selection_sha256=sha((output / 'selection.json').read_bytes()))
    (output / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n')
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    freeze(a.source, a.output)
