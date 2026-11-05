"""Move proven-idle owned historical assets; retain original-path symlinks."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import time

NAMES = ['tb4_family_scale_batch02_20261015_v1', 'tb4_coverage63_completion_20261017_v1',
         'tb4_family63_five_comparable_20261017', 'tb21_h20_qwen36_35b_base_official_20261007',
         'tb21_h20_corrected_full_pair_20261010']
AUDIT = Path('/mnt/ecs-tb4/audits/storage-recovery-20261105')
TARGET = Path('/mnt/ecs-tb4/archives/root-cold-20261105/raw')


def references(source):
    prefix = str(source)
    hits = []
    for proc in Path('/proc').glob('[0-9]*'):
        try:
            if prefix.encode() in (proc / 'cmdline').read_bytes():
                hits.append(str(proc) + ':cmdline')
            if prefix in (proc / 'mountinfo').read_text():
                hits.append(str(proc) + ':mount')
            for entry in [proc / 'cwd', proc / 'root', *(proc / 'fd').iterdir()]:
                try:
                    value = os.readlink(entry)
                    if value == prefix or value.startswith(prefix + '/'):
                        hits.append(str(entry))
                except OSError:
                    pass
        except OSError:
            pass
    return hits


def inventory(folder):
    result = {}
    for path in [folder, *folder.rglob('*')]:
        info = path.lstat()
        item = {'mode': info.st_mode, 'uid': info.st_uid, 'gid': info.st_gid, 'mtime_ns': info.st_mtime_ns}
        if stat.S_ISREG(info.st_mode):
            digest = hashlib.sha256()
            with path.open('rb') as stream:
                while chunk := stream.read(8 * 1024 * 1024):
                    digest.update(chunk)
            item.update(size=info.st_size, sha256=digest.hexdigest())
        elif stat.S_ISLNK(info.st_mode):
            item['link'] = os.readlink(path)
        elif not stat.S_ISDIR(info.st_mode):
            raise RuntimeError('Special file: ' + str(path))
        result[str(path.relative_to(folder))] = item
    return result


def main():
    AUDIT.mkdir(parents=True, exist_ok=True)
    TARGET.mkdir(parents=True, exist_ok=True)
    receipts = []
    for name in NAMES:
        source = Path('/root/bench') / name
        if not source.exists() or source.is_symlink():
            continue
        assert not references(source), 'Active reference: ' + name
        destination = TARGET / name
        assert not destination.exists(), 'Destination already exists'
        before = inventory(source)
        size = sum(item.get('size', 0) for item in before.values())
        assert shutil.disk_usage(TARGET).free > size + 25 * 2**30, 'Data disk headroom'
        destination.mkdir()
        subprocess.run(['rsync', '-aHAX', '--numeric-ids', '--', str(source) + '/', str(destination) + '/'], check=True)
        assert inventory(destination) == before, 'Destination mismatch'
        assert inventory(source) == before, 'Source changed during copy'
        assert not references(source), 'New active reference'
        (AUDIT / (name + '-manifest.json')).write_text(json.dumps(before, separators=(',', ':')) + '\n')
        inode = source.stat().st_ino
        retired = source.with_name(source.name + '.verified-migration-20261105')
        assert not retired.exists()
        source.rename(retired)
        try:
            source.symlink_to(destination, target_is_directory=True)
        except BaseException:
            retired.rename(source)
            raise
        assert retired.stat().st_ino == inode and source.resolve() == destination
        shutil.rmtree(retired)
        rec = {'source': str(source), 'authoritative_destination': str(destination), 'entries': len(before),
               'logical_bytes': size, 'all_sha256_metadata_verified': True, 'time': time.time()}
        receipts.append(rec)
        (AUDIT / 'cold-migration.json').write_text(json.dumps(receipts, indent=2) + '\n')
        print(json.dumps(rec), flush=True)


if __name__ == '__main__':
    main()
