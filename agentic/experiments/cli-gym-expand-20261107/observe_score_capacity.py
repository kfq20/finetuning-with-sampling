"""Finite read-only production observation; never sends inference or signals."""
import argparse
import collections
import json
import os
from pathlib import Path
import statistics
import time


def write(path, data):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(data, indent=2))
    temp.replace(path)


def workers(root, capacity):
    result = []
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        try:
            args = proc.joinpath('cmdline').read_bytes().decode().split('\0')
            if '--output' not in args:
                continue
            unit = Path(args[args.index('--output') + 1])
            if unit.parent != root / 'production/units':
                continue
            env = dict(x.split('=', 1) for x in proc.joinpath('environ').read_bytes().decode().split('\0') if '=' in x)
            if env.get('APPEND_REWRITE_SCORE_CAPACITY') == str(capacity):
                result.append(unit.name)
        except (OSError, ValueError, IndexError):
            continue
    return result


def statistics_for(values):
    values = sorted(values)
    return {'median': statistics.median(values),
            'p90': values[min(len(values) - 1, int(.9 * len(values)))]} if values else None


def snapshot(root, start, end):
    rows, success, errors = [], 0, collections.Counter()
    base = root / 'production/units'
    for path in base.glob('*/student/generation/turn-*/score-*/score.json'):
        if start <= path.stat().st_mtime <= end:
            rows.append(json.loads(path.read_text()))
    for path in base.glob('*/student/generation/turn-*/score-*/attempt-*/score.json'):
        success += start <= path.stat().st_mtime <= end
    for path in base.glob('*/student/generation/turn-*/score-*/attempt-*/error.json'):
        if start <= path.stat().st_mtime <= end:
            record = json.loads(path.read_text())
            errors[f"{record.get('http_status')}:{record.get('error_type')}"] += 1
    failures = sum(errors.values())
    return {'window_start_epoch': start, 'window_end_epoch': end,
            'logical_completed_scores': len(rows), 'logical_scores_per_min': len(rows) * 60 / (end - start),
            'queue_sec': statistics_for([x.get('score_queue_wait_sec', 0) for x in rows]),
            'request_sec': statistics_for([x['request_elapsed_sec'] for x in rows]),
            'context_tokens': statistics_for([x['candidate_start'] for x in rows]),
            'successful_scoring_attempts': success, 'failed_scoring_attempts': failures,
            'scoring_attempt_errors': dict(errors),
            'score_api_attempt_error_fraction': failures / (success + failures) if success + failures else None}


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--capacity', type=int, required=True)
    args = parser.parse_args()
    args.output.mkdir(exist_ok=False)
    began, start, units = time.time(), None, set()
    while time.time() - began < 1800:
        units.update(workers(args.root, args.capacity))
        if start is None:
            if any(list((args.root / 'production/units' / unit / 'student/generation').glob('turn-*/score-*/score.json')) for unit in units):
                start = time.time()  # Prospective window; excludes earlier completions.
        now = time.time()
        state = {'checked_at': now, 'observer_pid': os.getpid(), 'capacity': args.capacity,
                 'observed_capacity_units': sorted(units), 'window_start_epoch': start,
                 'new_model_requests': 0, 'process_signals': 0}
        write(args.output / 'progress.json', state)
        if start is not None and now - start >= 600:
            write(args.output / 'result.json', {**state, **snapshot(args.root, start, start + 600),
                  'complete_observation_window': True, 'causal_speedup_proven': False})
            return
        time.sleep(5)
    write(args.output / 'result.json', {**state, 'complete_observation_window': False,
          'reason': 'Finite observer ended; experiments unchanged'})


if __name__ == '__main__':
    main()
