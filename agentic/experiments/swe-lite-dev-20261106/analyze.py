"""Read-only comparable trajectory metrics; no raw reasoning or model requests."""
import csv
from datetime import datetime
import json
from pathlib import Path
import statistics
import sys


def seconds(stage):
    if not stage or not stage.get('started_at') or not stage.get('finished_at'):
        return None
    return (datetime.fromisoformat(stage['finished_at'].replace('Z', '+00:00')) -
            datetime.fromisoformat(stage['started_at'].replace('Z', '+00:00'))).total_seconds()


def metrics(path, arm):
    raw = json.loads(path.read_text())
    trajectory = path.parent / 'agent/trajectory.json'
    steps = json.loads(trajectory.read_text()).get('steps', []) if trajectory.exists() else []
    decisions = [json.loads(p.read_text()) for p in sorted(
        (path.parent / 'native-generation').glob('turn-*/decision.json'))]
    reward = (raw.get('verifier_result') or {}).get('rewards', {}).get('reward')
    error = (raw.get('exception_info') or {}).get('exception_type')
    return {'arm': arm, 'task': path.parent.name.rsplit('__', 1)[0],
        'result_path': str(path), 'finished': bool(raw.get('finished_at')),
        'error': error, 'valid': bool(raw.get('finished_at') and not error and reward in (0, 1)),
        'resolved': int(reward == 1) if not error and reward in (0, 1) else None,
        'assistant_turns': sum(s.get('source') == 'agent' for s in steps),
        'tool_calls': sum(len(s.get('tool_calls', [])) for s in steps),
        'completed_generations': len(decisions),
        'input_tokens_including_cache': sum(d['usage'].get('prompt_tokens', 0) or 0 for d in decisions),
        'output_tokens': sum(d['usage'].get('completion_tokens', 0) or 0 for d in decisions),
        'peak_context': max((d['usage'].get('prompt_tokens', 0) or 0 for d in decisions), default=0),
        'agent_sec': seconds(raw.get('agent_execution')),
        'environment_sec': seconds(raw.get('environment_setup')),
        'verifier_sec': seconds(raw.get('verifier')),
        'generation_sec': sum(d['elapsed_sec'] for d in decisions)}


def main(root):
    rows = [metrics(p, arm) for arm in ('base', 'method', 'expert')
            for p in sorted((root / arm / 'jobs/swe-lite-dev6').glob('*/result.json'))]
    out = root / 'analysis'; out.mkdir(exist_ok=True)
    if rows:
        with (out / 'per-task.csv').open('w') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    summary = {'checked_at': datetime.now().astimezone().isoformat(), 'arms': {}}
    for arm in ('base', 'method', 'expert'):
        part = [r for r in rows if r['arm'] == arm and r['finished']]
        valid = [r for r in part if r['valid']]
        summary['arms'][arm] = {'planned': 6, 'ended': len(part), 'valid': len(valid),
            'resolved': sum(r['resolved'] for r in valid), 'unknown': len(part) - len(valid),
            'medians_valid_only': {key: statistics.median([r[key] for r in valid if r[key] is not None])
                                  if any(r[key] is not None for r in valid) else None for key in
                                  ('agent_sec', 'assistant_turns', 'tool_calls', 'peak_context', 'output_tokens')}}
    (out / 'summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main(Path(sys.argv[1]))
