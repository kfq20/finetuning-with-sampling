"""Reclaim duplicate cold extraction caches; retain authoritative tar and restore ledger.

Only explicit archived payload directories are accepted. No Docker operations,
trajectory/log/score removal, or modification of current experiment inputs.
"""
import hashlib
import json
from pathlib import Path
import shutil
import tarfile
import time


BASE = Path('/mnt/ecs-tb4/archives/root-cold-20261102-v1/raw/tb4_scale315_quality_20261017_v1')


def sha_file(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def referenced(directory):
    target, payload = str(directory.resolve()), str(directory.parent.resolve())
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            paths = [str((proc / 'cwd').resolve())]
            args = (proc / 'cmdline').read_bytes().decode().split('\0')
            values = [v.split('=', 1)[1] for v in (proc / 'environ').read_bytes().decode().split('\0') if '=' in v]
            for value in args + values:
                for part in value.split(':'):
                    if part.startswith('/'):
                        paths.append(str(Path(part).resolve()))
            if any(p == payload or p.startswith(payload + '/') for p in paths):
                return True
            for fd in (proc / 'fd').iterdir():
                p = str(fd.resolve())
                if p == target or p.startswith(target + '/'):
                    return True
        except (OSError, UnicodeError):
            continue
    return False


def verify(directory, archive):
    assert directory.resolve().is_relative_to(BASE) and directory.parent.name == 'payload'
    assert directory.name in {'private-fixture', 'public-app', 'missing-fixture', 'fixture-missing'}
    assert archive == directory.parent.parent / 'payload.tar.gz' and not directory.is_symlink()
    prefix = str(directory.relative_to(archive.parent))
    actual = {str(p.relative_to(archive.parent)): p for p in directory.rglob('*') if p.is_file()}
    files = {}
    with tarfile.open(archive, 'r:gz') as tar:
        selected = [m for m in tar.getmembers() if m.name == prefix or m.name.startswith(prefix + '/')]
        assert all(m.isdir() or m.isfile() for m in selected)
        expected = {m.name: m for m in selected if m.isfile()}
        assert actual and actual.keys() == expected.keys()
        for name, path in actual.items():
            info, member = path.stat(), expected[name]
            assert not path.is_symlink() and info.st_nlink == 1
            assert info.st_size == member.size and info.st_mode & 511 == member.mode & 511
            digest = sha_file(path)
            assert hashlib.file_digest(tar.extractfile(member), 'sha256').hexdigest() == digest
            files[name] = {'sha256': digest, 'size': info.st_size, 'mode': info.st_mode & 511,
                           'mtime': info.st_mtime, 'allocated': info.st_blocks * 512}
    return files


def restore(receipt, destination=None):
    archive = Path(receipt['archive'])
    assert sha_file(archive) == receipt['archive_sha256']
    target = Path(destination) if destination else Path(receipt['directory'])
    target.mkdir(parents=True, exist_ok=False)
    prefix = Path(receipt['prefix'])
    with tarfile.open(archive, 'r:gz') as tar:
        for name, info in receipt['files'].items():
            relative = Path(name).relative_to(prefix)
            assert '..' not in relative.parts
            path = target / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            with tar.extractfile(name) as src, path.open('xb') as dst:
                shutil.copyfileobj(src, dst)
            path.chmod(info['mode'])
            assert sha_file(path) == info['sha256']


def main(candidates, output):
    output.mkdir(parents=True, exist_ok=False)
    removed, held = [], []
    for index, item in enumerate(json.loads(candidates.read_text())):
        directory, archive = Path(item['directory']), Path(item['archive'])
        try:
            assert not referenced(directory), 'Live process reference'
            checksum = sha_file(archive)
            files = verify(directory, archive)
            receipt = {'directory': str(directory), 'archive': str(archive),
                       'archive_sha256': checksum, 'prefix': str(directory.relative_to(archive.parent)),
                       'files': files, 'at': time.time(), 'authoritative_archive_preserved': True}
            record = output / f'cache-{index:03d}.json'
            record.write_text(json.dumps(receipt, indent=2))
            if not removed:
                temporary = output / f'restore-smoke-{index}'
                restore(receipt, temporary)
                shutil.rmtree(temporary)
            assert not referenced(directory) and sha_file(archive) == checksum
            assert all(sha_file(archive.parent / n) == f['sha256'] for n, f in files.items())
            # The verified archive is authoritative; remove only its unused expansion.
            shutil.rmtree(directory)
            directory.with_name(directory.name + '-CACHE-RESTORE.json').write_text(json.dumps({
                'receipt': str(record), 'restore_helper': str(Path(__file__).resolve()),
                'archive_sha256': checksum}, indent=2))
            removed.append({'directory': str(directory), 'receipt': str(record),
                            'allocated_bytes': sum(f['allocated'] for f in files.values())})
        except Exception as exc:
            held.append({'directory': str(directory), 'error_type': type(exc).__name__, 'reason': str(exc)[:200]})
        (output / 'progress.json').write_text(json.dumps({'removed': removed, 'held': held,
            'free_gib': shutil.disk_usage(output).free / 1024**3}, indent=2))
    (output / 'complete.json').write_text((output / 'progress.json').read_text())


if __name__ == '__main__':
    import sys
    main(Path(sys.argv[1]), Path(sys.argv[2]))
