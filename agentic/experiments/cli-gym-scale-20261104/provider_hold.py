"""Hold this wave's student admission locks while a provider deployment is absent.

No model requests, retries, process signals, credential changes or dispatch.
Existing expert episodes may finish and retain their receipts before waiting.
Release is an explicit operator act after service recovery, not a timed retry.
"""
import argparse
import fcntl
import json
import os
from pathlib import Path
import time


def main():
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--wave', type=Path, required=True)
    p.add_argument('--capacity', type=int, required=True)
    a = p.parse_args()
    assert a.capacity > 0
    gate = a.wave / 'provider-hold'
    gate.mkdir(mode=0o700, exist_ok=False)
    locks = {}
    try:
        while True:
            release_path = gate / 'RELEASE_APPROVED.json'
            if release_path.exists():
                release = json.loads(release_path.read_text())
                if release.get('service_health_verified') is True:
                    break
            for i in range(a.capacity):
                if i in locks:
                    continue
                f = (a.wave / 'student-pool' / f'score-{i}.lock').open('a+')
                try:
                    fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locks[i] = f
                except BlockingIOError:
                    f.close()
            target = gate / 'status.json'
            temp = gate / 'status.tmp'
            temp.write_text(json.dumps({'pid': os.getpid(), 'checked_at': time.time(),
                'held_student_slots': len(locks), 'capacity': a.capacity,
                'active': True, 'model_requests': 0,
                'reason': 'Qwen deployment_not_found404; explicit service recovery required'}, indent=2)+'\n')
            temp.replace(target)
            time.sleep(5)
    finally:
        for f in locks.values():
            f.close()


if __name__ == '__main__':
    main()
