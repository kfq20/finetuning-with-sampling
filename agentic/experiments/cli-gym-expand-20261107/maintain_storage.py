"""One bounded housekeeping pass owned by the acquisition producer, not a daemon.

Compact settled journals losslessly. Under pressure, evict only completed SWE
source caches whose exact immutable registry image can be restored. Never prune
Docker globally, remove task evidence, or touch running/queued images.
"""
import fcntl
import json
import os
from pathlib import Path
import runpy
import shutil
import sys
import time

from append_rewrite.terminus.docker_world import docker
from append_rewrite.terminus.production import dump


TERMINAL = {'completed', 'hold', 'teacher_not_successful'}
SOCKET = 'unix:///mnt/ecs-tb4/cli-gym-pilot-20261104/runtime/docker.sock'


def read(p):
    return json.loads(p.read_text())


def source_images(root):
    needed, candidates, protected = set(), {}, set()
    for item in read(root / 'acquisition-plan.json')['units']:
        spec = read(Path(item['spec_path']))
        image = spec['template_id']
        if spec['source']['kind'] != 'swe-gym':
            protected.update(spec.get(k) for k in ('template_id', 'gold_template_id', 'verifier_template_id'))
            continue
        status = root / 'production/units' / item['unit_id'] / 'status.json'
        if not status.exists() or read(status).get('phase') not in TERMINAL or time.time() - status.stat().st_mtime < 600:
            needed.add(image)
        elif spec.get('capture_format') == 'git-patch' and spec.get('source_registry_image'):
            candidates[image] = spec['source_registry_image']
    return {image: ref for image, ref in candidates.items() if image not in needed | protected}


def checked(*args, timeout=45):
    result = docker(*args, timeout=timeout)
    if result.returncode:
        raise RuntimeError(result.stderr.decode(errors='replace')[-400:])
    return result.stdout


def cache_candidates(root, limit=16):
    # Already-evicted images must not consume the bounded work allowance.
    present = set(checked('image', 'ls', '--quiet', '--no-trunc').decode().split())
    return dict(list((image, ref) for image, ref in source_images(root).items()
                     if image in present)[:limit])


def main(root, output):
    assert os.environ.get('DOCKER_HOST') == SOCKET, 'Only the study-owned Docker endpoint is allowed'
    output.mkdir(parents=True, exist_ok=True)
    with (root / 'support/storage-maintenance.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            dump(output / 'complete.json', {'phase': 'another_finite_pass_running'})
            return
        before = shutil.disk_usage(root).free
        compact = runpy.run_path(str(Path(__file__).with_name('compact_wires.py')))['main']
        compact([root / 'production'], output / 'journals')
        removed, held = [], []
        if shutil.disk_usage(root).free < 100 * 1024**3:
            for image, ref in cache_candidates(root).items():
                if shutil.disk_usage(root).free >= 120 * 1024**3:
                    break
                try:
                    info = json.loads(checked('image', 'inspect', image))[0]
                    tags = info.get('RepoTags') or []
                    if len(tags) != 1 or not tags[0].startswith('xingyaoww/sweb.eval.x86_64.') or ref not in info.get('RepoDigests', []):
                        continue
                    ids = checked('ps', '-aq').decode().split()
                    if ids and image in {v['Image'] for v in json.loads(checked('inspect', *ids))}:
                        continue
                    registry = json.loads(checked('manifest', 'inspect', ref))
                    if registry.get('config', {}).get('digest') != image or image not in source_images(root):
                        continue
                    intent = {'image_id': image, 'registry_digest': ref, 'at': time.time()}
                    index = len(removed)
                    dump(output / f'cache-{index}-intent.json', intent)
                    # No force and no recursive parent pruning. The engine also
                    # rejects removal if a container acquired a reference.
                    checked('image', 'rm', '--no-prune', image)
                    removed.append(intent)
                    dump(output / f'cache-{index}-removed.json', intent)
                except Exception as error:
                    held.append({'image_id': image, 'error_type': type(error).__name__})
        dump(output / 'complete.json', {'at': time.time(), 'before_free': before,
            'after_free': shutil.disk_usage(root).free, 'removed_source_cache': removed,
            'held_cache_operations': held, 'model_requests': 0, 'global_prune': False})
    # This helper takes the same storage lock. Run after releasing our pass's
    # lock so failed source downloads cannot refill the disk or deadlock us.
    if shutil.disk_usage(root).free < 100 * 1024**3:
        reclaim = runpy.run_path(str(Path(__file__).with_name('reclaim_failed_swe_cache.py')))['main']
        reclaim(root, output / 'failed-source-caches')


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]))
