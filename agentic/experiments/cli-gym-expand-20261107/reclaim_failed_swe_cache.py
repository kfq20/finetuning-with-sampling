"""Reclaim only this campaign's failed SWE preparation caches, not evidence.

Require a recorded new download, canonical row hash, immutable registry config,
no published task/image reference and no container reference. Keep a pilot image.
"""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import time
from append_rewrite.terminus.docker_world import checked
from append_rewrite.terminus.production import dump


def read(path):
    return json.loads(path.read_text())


def pending_source_references(sources):
    """Protect repaired packages even before the producer publishes them."""
    units, images = set(), set()
    for source in sources:
        progress = read(source / 'progress.json') if (source / 'progress.json').exists() else {}
        failed = {x['task_id'] for x in progress.get('held', [])}
        # A row folder is created before Docker pull or progress publication.
        for folder in source.iterdir() if source.exists() else []:
            if folder.is_dir() and (folder / 'source-row.json').exists() and folder.name not in failed:
                units.add('swegym-' + folder.name)
        if (source / 'plan.json').exists():
            for item in read(source / 'plan.json')['units']:
                spec = read(Path(item['spec_path']))
                units.add(item['unit_id'])
                images.update(spec.get(k) for k in ['template_id', 'gold_template_id', 'verifier_template_id'])
    return units, images


def main(root, output, target_gib=90):
    assert os.environ['DOCKER_HOST'] == 'unix:///mnt/ecs-tb4/cli-gym-pilot-20261104/runtime/docker.sock'
    output.mkdir(parents=True, exist_ok=False)
    sources = [root / 'new-source-swegym' / name
               for name in ['full-prepared-v2', 'full-prepared-v3', 'full-prepared-v4']]
    held = [(source, item) for source in sources if (source / 'progress.json').exists()
            for item in read(source / 'progress.json').get('held', [])]
    scope = read(root / 'new-source-swegym/scope.json')
    published = read(root / 'acquisition-plan.json')['units']
    task_ids = {x['unit_id'] for x in published}
    protected = set()
    for item in published:
        spec = read(Path(item['spec_path']))
        protected.update(spec.get(k) for k in ['template_id', 'gold_template_id', 'verifier_template_id'])
    before, removed, holds = shutil.disk_usage(root).free, [], []
    with (root / 'support/storage-maintenance.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        for source, item in held:
            name = item['task_id']
            pending_units, pending_images = pending_source_references(sources)
            if name == 'facebookresearch__hydra-2189' or 'swegym-' + name in task_ids | pending_units:
                continue
            folder = source / name
            row_file, pull_file = folder/'source-row.json', folder/'pull.log'
            if not all(p.is_file() for p in [row_file, pull_file]) or time.time()-max(p.stat().st_mtime for p in [row_file,pull_file]) < 60:
                continue
            row = read(row_file)
            row_sha = hashlib.sha256(json.dumps(row, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
            assert row['instance_id'] == name and scope['tasks'][name] == row_sha
            tag = 'xingyaoww/sweb.eval.x86_64.' + name.replace('__','_s_').lower()
            if 'Status: Downloaded newer image for ' + tag not in pull_file.read_text():
                continue
            if shutil.disk_usage(root).free >= target_gib * 1024**3:
                break
            try:
                info = json.loads(checked('image','inspect',tag))[0]
                image = info['Id']
                if image in protected | pending_images or info.get('RepoTags') != [tag+':latest']:
                    continue
                ids = checked('ps','-aq').decode().split()
                if ids and image in {v['Image'] for v in json.loads(checked('inspect',*ids))}:
                    continue
                refs = [r for r in info.get('RepoDigests',[]) if r.startswith(tag+'@sha256:')]
                if len(refs)!=1 or json.loads(checked('manifest','inspect',refs[0],timeout=45))['config']['digest']!=image:
                    continue
                entry={'task':name,'image_id':image,'registry_digest':refs[0],'source_row_sha256':row_sha,'new_download_log_sha256':hashlib.sha256(pull_file.read_bytes()).hexdigest(),'at':time.time()}
                index=len(removed)
                dump(output/f'{index}-intent.json',entry)
                checked('image','rm','--no-prune',image,timeout=45)
                removed.append(entry)
                dump(output/f'{index}-removed.json',entry)
            except Exception as error:
                holds.append({'task':name,'error_type':type(error).__name__})
        result={'at':time.time(),'before_free':before,'after_free':shutil.disk_usage(root).free,'removed':removed,'held_operations':holds,'model_requests':0,'old_images_removed':0,'global_prune':False,'evidence_deleted':0}
        dump(output/'complete.json',result)
    print(json.dumps({k:v for k,v in result.items() if k!='removed'}),flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    main(a.root,a.output)
