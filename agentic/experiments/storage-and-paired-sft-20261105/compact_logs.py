"""Lossless archive of closed TB21 cumulative SSE journals, no model requests."""
import gzip
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

ROOT = Path('/mnt/ecs-tb4/evaluations/qwen38-tb21-base-20261104')
AUDIT = Path('/mnt/ecs-tb4/audits/storage-recovery-20261105')


def main():
    AUDIT.mkdir(parents=True, exist_ok=True)
    journal = AUDIT / 'compression.jsonl'
    files = list((ROOT / 'model-jobs').glob('*/*/agent/native-generation/turn-*/wire.jsonl'))
    opened = set()
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            for fd in (proc / 'fd').iterdir():
                try:
                    opened.add(os.readlink(fd))
                except OSError:
                    pass
        except OSError:
            pass
    freed = 0
    for path in files:
        if str(path) in opened or path.stat().st_size < 1024 * 1024:
            continue
        trial = path.parents[3]
        result = json.loads((trial / 'result.json').read_text())
        assert result['finished_at']
        original = path.stat()
        target = path.with_suffix(path.suffix + '.gz')
        if target.exists():
            raise RuntimeError('Existing archive requires review: ' + str(target))
        temporary = target.with_suffix('.gz.partial')
        digest = hashlib.sha256()
        with path.open('rb') as source, gzip.open(temporary, 'wb', compresslevel=1) as output:
            while chunk := source.read(8 * 1024 * 1024):
                digest.update(chunk)
                output.write(chunk)
        check = hashlib.sha256()
        restored = 0
        with gzip.open(temporary, 'rb') as source:
            while chunk := source.read(8 * 1024 * 1024):
                restored += len(chunk)
                check.update(chunk)
        assert restored == original.st_size and digest.digest() == check.digest()
        current = path.stat()
        assert (current.st_ino, current.st_size, current.st_mtime_ns) == (original.st_ino, original.st_size, original.st_mtime_ns)
        temporary.replace(target)
        os.utime(target, ns=(original.st_atime_ns, original.st_mtime_ns))
        record = {'original_path': str(path), 'archive': str(target), 'bytes': original.st_size,
                  'archive_bytes': target.stat().st_size, 'original_sha256': digest.hexdigest(),
                  'mode': original.st_mode, 'mtime_ns': original.st_mtime_ns,
                  'verified_full_decompression': True, 'time': time.time()}
        with journal.open('a') as log:
            log.write(json.dumps(record) + '\n')
            log.flush()
            os.fsync(log.fileno())
        path.unlink()
        freed += original.st_blocks * 512 - target.stat().st_blocks * 512
    (AUDIT / 'compression-summary.json').write_text(json.dumps({'finished_at': time.time(), 'net_freed_bytes': freed,
        'original_result_files_unchanged': True, 'scope': 'closed original TB21 wire journals only; retry57 untouched'}) + '\n')
    print('freed_bytes', freed, flush=True)


if __name__ == '__main__':
    main()
