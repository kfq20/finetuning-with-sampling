"""Lossless compaction of closed transport journals; never touch SFT/decisions."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import runpy
import shutil


def main(roots, output):
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        archive = runpy.run_path(str(Path(__file__).parents[1] / 'swe-lite-full-20261106/archive_closed.py'))
        opened = archive['opened_paths']()
        selected = []
        contexts = {}
        for root in roots:
            for status in root.rglob('units/*/status.json'):
                if json.loads(status.read_text()).get('phase') not in ('hold', 'completed', 'teacher_not_successful'):
                    continue
                digest = hashlib.sha256(status.read_bytes()).hexdigest()
                contexts[str(status)] = digest
                for wire in status.parent.glob('*/generation/turn-*/**/*'):
                    if wire.name not in ('wire.jsonl', 'response.json'):
                        continue
                    if not wire.is_symlink() and str(wire) not in opened and wire.stat().st_size >= 131072:
                        selected.append((wire, root, status, digest))
        (output / 'plan.json').write_text(json.dumps({'files': [str(x[0]) for x in selected],
            'logical_bytes': sum(x[0].stat().st_size for x in selected)}, indent=2))
        freed = 0
        for wire, root, status, digest in sorted(selected, key=lambda x: x[0].stat().st_size, reverse=True):
            assert hashlib.sha256(status.read_bytes()).hexdigest() == digest
            freed += archive['archive'](wire, output / 'ledger.jsonl', root, digest)
        assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in contexts.items())
        (output / 'complete.json').write_text(json.dumps({'files': len(selected),
            'net_freed_bytes': freed, 'data_free_gib': shutil.disk_usage(output).free / 1024**3,
            'all_terminal_status_hashes_unchanged': True}, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    p.add_argument('--roots', nargs='+', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    a = p.parse_args()
    main(a.roots, a.output)
