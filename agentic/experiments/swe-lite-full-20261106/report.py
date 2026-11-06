"""Read-only full-cohort report; no model requests, scheduling or raw reasoning."""
import csv
import importlib.util
import json
from pathlib import Path
import statistics
import sys
from datetime import datetime, timezone, timedelta


def main(root):
    source = root / 'runtime/source/agentic/experiments/swe-lite-dev-20261106/analyze.py'
    spec = importlib.util.spec_from_file_location('pilot_metrics', source)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    rows = []
    for arm in ('base', 'method', 'expert'):
        for receipt in sorted((root / arm).glob('*/receipt.json')):
            record = json.loads(receipt.read_text())
            path = Path(record['result_path'])
            rows.append(mod.metrics(path, arm))
    plan = json.loads((root / 'plan.json').read_text())
    summary = {'checked_at': datetime.now(timezone(timedelta(hours=8))).isoformat(),
               'split': plan['split'], 'cohort': plan['cohort'], 'arms': {},
               'preflight_held': len(list((root / 'gates').glob('*/hold.json')))}
    sets = []
    for arm in ('base', 'method', 'expert'):
        part = [r for r in rows if r['arm'] == arm]
        valid = [r for r in part if r['valid']]
        sets.append({r['task'] for r in valid})
        summary['arms'][arm] = {'valid': len(valid), 'resolved': sum(r['resolved'] == 1 for r in valid),
            'execution_unknown': len(part) - len(valid),
            'medians_valid_only': {key: statistics.median([r[key] for r in valid if r[key] is not None])
                if any(r[key] is not None for r in valid) else None for key in
                ('agent_sec', 'assistant_turns', 'tool_calls', 'peak_context', 'output_tokens')}}
    common = set.intersection(*sets)
    summary['common_valid_cohort'] = {'tasks': len(common),
        'resolved': {arm: sum(r['resolved'] == 1 for r in rows if r['arm'] == arm and r['task'] in common)
                     for arm in ('base', 'method', 'expert')}}
    out = root / 'reports'; out.mkdir(exist_ok=True)
    if rows:
        with (out / 'per-task.csv').open('w') as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0])); writer.writeheader(); writer.writerows(rows)
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main(Path(sys.argv[1]))
