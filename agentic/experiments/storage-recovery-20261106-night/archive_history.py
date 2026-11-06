"""Finite verified archive of idle CLI-Gym API journals; no model or Docker actions."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path('/mnt/ecs-tb4/cli-gym-scale-20261104/rolling-acquisition-20261104')


def sha(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        while chunk := stream.read(1024 * 1024):
            value.update(chunk)
    return value.hexdigest()


def write(path, data):
    pending = path.with_suffix('.pending'); pending.write_text(json.dumps(data, indent=2)); pending.replace(path)


def references(root):
    found = []
    for proc in Path('/proc').glob('[0-9]*'):
        if int(proc.name) == os.getpid():
            continue
        try:
            if str(root).encode() in (proc / 'cmdline').read_bytes():
                found.append(proc.name)
        except OSError:
            pass
    return found


def main(audit):
    module_path = audit / 'archive_closed.py'
    spec = importlib.util.spec_from_file_location('verified_archive', module_path)
    archive = importlib.util.module_from_spec(spec); spec.loader.exec_module(archive)
    assert (ROOT / 'complete.json').exists(), 'Closed producer receipt required'
    complete_sha = sha(ROOT / 'complete.json')
    assert not references(ROOT), 'Old acquisition still has process consumers'
    opened = archive.opened_paths()
    candidates = []
    context_cache = {}
    for unit in (ROOT / 'run/units').iterdir():
        if not unit.is_dir():
            continue
        for role in ('teacher', 'student'):
            context = unit / role / 'receipt.json'
            if not context.exists():
                context = unit / 'status.json'
            if not context.exists():
                continue
            context_cache[str(context)] = sha(context)
            for name in ('wire.jsonl', 'request.json', 'response.json'):
                for path in (unit / role).rglob(name):
                    if path.is_symlink() or str(path) in opened:
                        continue
                    stat = path.stat()
                    if stat.st_size < 131072 or stat.st_nlink != 1:
                        continue
                    candidates.append({'relative': str(path.relative_to(ROOT)),
                        'inode': stat.st_ino, 'device': stat.st_dev, 'size': stat.st_size,
                        'mtime_ns': stat.st_mtime_ns, 'context_path': str(context),
                        'terminal_context_sha256': context_cache[str(context)]})
    candidates.sort(key=lambda x: x['size'], reverse=True)
    write(audit / 'plan.json', {'at': time.time(), 'root': str(ROOT),
        'producer_complete_sha256': complete_sha, 'process_references': [],
        'files': candidates, 'logical_bytes': sum(x['size'] for x in candidates),
        'scope': 'API journals only; never trajectory, decision, scoring receipt, SFT, model or image'})
    assert not references(ROOT)
    totals = {'at': time.time(), 'archived': 0, 'net_freed_bytes': 0, 'errors': [], 'finished': False}
    def one(item):
        path = ROOT / item['relative']; stat = path.stat()
        assert (stat.st_ino, stat.st_dev, stat.st_size, stat.st_mtime_ns, stat.st_nlink) == (
            item['inode'], item['device'], item['size'], item['mtime_ns'], 1)
        assert sha(Path(item['context_path'])) == item['terminal_context_sha256']
        return archive.archive(path, audit / 'ledger.jsonl', ROOT, item['terminal_context_sha256'])
    write(audit / 'progress.json', totals)
    last = 0
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(one, item): item['relative'] for item in candidates}
        for future in as_completed(futures):
            try:
                totals['net_freed_bytes'] += future.result(); totals['archived'] += 1
            except Exception as error:
                totals['errors'].append({'file': futures[future], 'type': type(error).__name__})
            if time.monotonic() - last > 5:
                totals['at'] = time.time(); write(audit / 'progress.json', totals); last = time.monotonic()
    assert sha(ROOT / 'complete.json') == complete_sha
    totals.update(at=time.time(), finished=True, preserved_terminal_contexts=all(
        sha(Path(path)) == digest for path, digest in context_cache.items()))
    write(audit / 'progress.json', totals)
    print(json.dumps(totals), flush=True)


if __name__ == '__main__':
    main(Path(sys.argv[1]))
