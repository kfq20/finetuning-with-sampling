"""Losslessly compact only terminal trials' request/SSE journals in this run."""
import fcntl
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def archive(path, ledger, root, result_sha):
    before = path.stat(); target = path.with_suffix(path.suffix + '.gz')
    digest = sha(path)
    if not target.exists():
        partial = target.with_suffix('.gz.partial')
        with path.open('rb') as source, gzip.open(partial, 'wb', compresslevel=1) as out:
            while chunk := source.read(1024 * 1024):
                out.write(chunk)
        partial.replace(target)
    restored = hashlib.sha256(); size = 0
    with gzip.open(target, 'rb') as stream:
        while chunk := stream.read(1024 * 1024):
            restored.update(chunk); size += len(chunk)
    assert size == before.st_size and restored.hexdigest() == digest
    after = path.stat()
    assert (before.st_ino, before.st_size, before.st_mtime_ns) == (after.st_ino, after.st_size, after.st_mtime_ns)
    record = {'at': time.time(), 'original': str(path.relative_to(root)),
        'archive': str(target.relative_to(root)), 'source_sha256': digest,
        'archive_sha256': sha(target), 'source_bytes': before.st_size,
        'archive_bytes': target.stat().st_size, 'mode': before.st_mode,
        'mtime_ns': before.st_mtime_ns, 'terminal_result_sha256': result_sha,
        'verified_full_decompression': True}
    with ledger.open('a') as log:
        log.write(json.dumps(record) + '\n'); log.flush(); os.fsync(log.fileno())
    freed = before.st_blocks * 512 - target.stat().st_blocks * 512
    path.unlink()
    return freed


def opened_paths():
    opened = set()
    for process in Path('/proc').glob('[0-9]*'):
        try:
            for fd in (process / 'fd').iterdir():
                try:
                    opened.add(os.readlink(fd))
                except OSError:
                    pass
        except OSError:
            pass
    return opened


def main(root):
    support = root / 'support/closed-journal-archives'; support.mkdir(parents=True, exist_ok=True)
    with (support / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        owner = json.loads((root / 'launch.json').read_text())
        freed = 0
        while True:
            opened = opened_paths()
            for arm in ('base', 'method', 'expert'):
                for receipt in (root / arm).glob('*/receipt.json'):
                    data = json.loads(receipt.read_text()); result = Path(data['result_path'])
                    assert sha(result) == data['result_sha256']
                    for pattern in ('request.json', 'wire-deltas.jsonl', 'wire.jsonl'):
                        for path in (result.parent / 'native-generation').glob('turn-*/' + pattern):
                            if path.stat().st_size < 65536 or str(path) in opened:
                                continue
                            freed += archive(path, support / 'ledger.jsonl', root, data['result_sha256'])
            (support / 'status.json').write_text(json.dumps({'at': time.time(), 'net_freed_bytes': freed,
                'scope': 'Only completed model trials in this root; all result/decision/trajectory files unchanged'}))
            proc = Path(f'/proc/{owner["pid"]}/stat')
            if not proc.exists():
                break
            stat = proc.read_text().split()
            if stat[21] != owner['start_ticks'] or stat[2] == 'Z':
                break
            time.sleep(30)


if __name__ == '__main__':
    main(Path(sys.argv[1]))
