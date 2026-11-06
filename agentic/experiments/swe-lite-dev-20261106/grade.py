"""Run the frozen SWE-bench evaluation script and require every F2P/P2P test."""
import json
from pathlib import Path
import subprocess
import sys


def classify(status, required):
    missing = sorted(set(required) - set(status))
    if missing:
        raise RuntimeError('Official tests missing from log: ' + ','.join(missing[:8]))
    return int(all(status[name] == 'PASSED' for name in required))


def main(root, output):
    import official_parsers
    record = json.loads((root / 'grading.json').read_text())
    output.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(['bash', str(root / 'eval.sh')], cwd='/testbed',
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, timeout=540)
    (output / 'test-output.txt').write_text(result.stdout)
    parser = getattr(official_parsers, record['log_parser'])
    status = parser(result.stdout, None)
    required = record['FAIL_TO_PASS'] + record['PASS_TO_PASS']
    assert required and record['FAIL_TO_PASS']
    reward = classify(status, required)
    (output / 'report.json').write_text(json.dumps({
        'resolved': bool(reward), 'all_required': len(required),
        'passed_required': sum(status[n] == 'PASSED' for n in required),
        'script_exit_code': result.returncode, 'test_status': status}, indent=2))
    (output / 'reward.txt').write_text(str(reward) + '\n')


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]))
