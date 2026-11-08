"""Lossless compaction of closed transport journals; never touch SFT/decisions."""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import time


def main(roots, output):
    output.mkdir(parents=True, exist_ok=True)
    with (output / 'lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        archive = runpy.run_path(str(Path(__file__).parents[1] / 'swe-lite-full-20261106/archive_closed.py'))
        opened = archive['opened_paths']()
        live = set()
        for process in Path('/proc').glob('[0-9]*/cmdline'):
            try:
                argv = process.read_bytes().decode().strip('\0').split('\0')
                if 'append_rewrite.terminus.production' in argv and 'unit' in argv and '--output' in argv:
                    live.add(Path(argv[argv.index('--output') + 1]))
            except OSError:
                pass
        selected = []
        contexts = {}
        for root in roots:
            policy_path = root.parent / 'storage-policy.json'
            policy = json.loads(policy_path.read_text()) if policy_path.exists() else {}
            request_only = policy.get('preserve_transport_evidence', False)
            # The run layout is flat. rglob also walks every candidate journal
            # directory again after yielding units, delaying the entire plan.
            for index, status in enumerate((root / 'units').glob('*/status.json')):
                if index % 25 == 0:
                    (output / 'scan-progress.json').write_text(json.dumps({
                        'units_scanned': index, 'selected_caches': len(selected), 'at': time.time()}))
                if status.parent in live or time.time() - status.stat().st_mtime < 600:
                    continue
                if json.loads(status.read_text()).get('phase') not in ('hold', 'completed', 'teacher_not_successful'):
                    continue
                digest = hashlib.sha256(status.read_bytes()).hexdigest()
                contexts[str(status)] = digest
                for wire in status.parent.glob('*/generation/turn-*/**/*'):
                    if wire.name not in ('wire.jsonl', 'response.json', 'request.json'):
                        continue
                    if request_only and wire.name != 'request.json':
                        continue
                    minimum = 4096 if request_only else 131072
                    if (not wire.is_symlink() and str(wire) not in opened
                        and wire.stat().st_size >= minimum and time.time() - wire.stat().st_mtime >= 600):
                        if request_only:
                            body = json.loads(wire.read_text())
                            if 'sampling_params' not in body or not ('input_ids' in body or 'text' in body):
                                continue  # Only reconstructible request-body caches.
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
