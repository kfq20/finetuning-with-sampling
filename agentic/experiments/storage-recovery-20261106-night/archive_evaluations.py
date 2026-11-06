"""Second finite wave: archive API journals of terminal historical eval trials."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import importlib.util
import json
import os
from pathlib import Path
import sys
import time

ROOTS = tuple(Path('/mnt/ecs-tb4/evaluations') / name for name in (
    'qwen38-http-base-timeout2x-20261105-a1',
    'qwen38-paired531-sft-20261105-a1',
    'qwen38-paired531-timeout4x-retry1-20261106-a1',
    'qwen38-cancellable-thinking-canary-20261106-a1',
    'qwen38-tb21-base-20261104'))


def write(path, data):
    pending = path.with_suffix('.pending'); pending.write_text(json.dumps(data, indent=2)); pending.replace(path)


def candidates(roots, opened, sha, now):
    items, protected = [], {}
    for root in roots:
        if root.is_symlink():
            continue
        results = set()
        for pattern in ('jobs/*/*/result.json', '*/jobs/*/*/result.json', 'model-jobs/*/*/result.json'):
            results.update(root.glob(pattern))
        for result in results:
            row = json.loads(result.read_text())
            if not row.get('task_name') or not row.get('finished_at'):
                continue
            ended = datetime.fromisoformat(row['finished_at'].replace('Z', '+00:00')).timestamp()
            if now - ended < 600:
                continue
            protected[str(result)] = sha(result)
            trajectory = result.parent / 'agent/trajectory.json'
            if trajectory.exists():
                protected[str(trajectory)] = sha(trajectory)
            for generation in (result.parent / 'native-generation', result.parent / 'agent/native-generation'):
                for name in ('wire.jsonl', 'wire-deltas.jsonl', 'request.json', 'response.json'):
                    for path in generation.glob('turn-*/' + name):
                        if path.is_symlink() or path.resolve() != path.absolute() or str(path) in opened:
                            continue
                        st = path.stat()
                        if st.st_nlink != 1 or st.st_size < 131072 or now - st.st_mtime < 600:
                            continue
                        items.append({'root': str(root), 'relative': str(path.relative_to(root)),
                            'inode': st.st_ino, 'device': st.st_dev, 'size': st.st_size,
                            'mtime_ns': st.st_mtime_ns, 'result_path': str(result),
                            'result_sha256': protected[str(result)]})
    return sorted(items, key=lambda x: x['size'], reverse=True), protected


def main(audit):
    spec = importlib.util.spec_from_file_location('verified_archive', audit / 'archive_closed.py')
    archive = importlib.util.module_from_spec(spec); spec.loader.exec_module(archive)
    opened = archive.opened_paths()
    items, protected = candidates(ROOTS, opened, archive.sha, time.time())
    write(audit / 'plan.json', {'at': time.time(), 'files': items,
        'logical_bytes': sum(x['size'] for x in items), 'protected_hashes': protected,
        'scope': 'Terminal historical eval API journals only; current SWE300 explicitly excluded'})
    totals = {'at': time.time(), 'archived': 0, 'net_freed_bytes': 0, 'errors': [], 'finished': False}
    ledgers = audit / 'ledgers'; ledgers.mkdir(exist_ok=True)
    def one(item):
        root = Path(item['root']); path = root / item['relative']; st = path.stat()
        assert (st.st_ino, st.st_dev, st.st_size, st.st_mtime_ns, st.st_nlink) == (
            item['inode'], item['device'], item['size'], item['mtime_ns'], 1)
        assert archive.sha(Path(item['result_path'])) == item['result_sha256']
        return archive.archive(path, ledgers / (root.name + '.jsonl'), root, item['result_sha256'])
    last = 0
    write(audit / 'progress.json', totals)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = {pool.submit(one, item): item for item in items}
        for future in as_completed(futures):
            item = futures.pop(future)
            try:
                totals['net_freed_bytes'] += future.result(); totals['archived'] += 1
            except Exception as error:
                totals['errors'].append({'root': item['root'], 'file': item['relative'], 'type': type(error).__name__})
            if time.monotonic() - last > 5:
                totals['at'] = time.time()
                totals['largest_remaining'] = [{'file': v['relative'], 'bytes': v['size']}
                    for v in sorted(futures.values(), key=lambda x:x['size'], reverse=True)[:2]]
                write(audit / 'progress.json', totals); last = time.monotonic()
    assert all(archive.sha(Path(p)) == digest for p, digest in protected.items())
    totals.update(at=time.time(), finished=True, protected_results_and_trajectories=len(protected),
                  protected_hashes_unchanged=True, largest_remaining=[])
    write(audit / 'progress.json', totals)
    print(json.dumps(totals), flush=True)


if __name__ == '__main__':
    main(Path(sys.argv[1]))
