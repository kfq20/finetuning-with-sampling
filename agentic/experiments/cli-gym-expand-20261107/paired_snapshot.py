"""Freeze and validate source-separated expert/method pairs without inference.

Reuse the established paired exporter. Live producer files are copied only when
manifest and data agree; immutable snapshots never replace production evidence.
"""
import argparse
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import time


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def snapshot(source, destination):
    for _ in range(20):
        manifest = (source / 'manifest.json').read_bytes()
        data = (source / 'train.jsonl').read_bytes()
        record = json.loads(manifest)
        if sha(data) == record['train_sha256'] and manifest == (source / 'manifest.json').read_bytes():
            destination.mkdir(parents=True)
            (destination / 'manifest.json').write_bytes(manifest)
            (destination / 'train.jsonl').write_bytes(data)
            return {'manifest_sha256': sha(manifest), 'train_sha256': sha(data),
                    'method_count': record['valid_trajectories']}
        time.sleep(.1)
    raise RuntimeError('Live export was changing; no inconsistent snapshot accepted')


def main(root, output, tokenizer, support, *, sources=('cli-gym', 'swe-gym')):
    if not sources or len(set(sources)) != len(sources) or set(sources) - {'cli-gym', 'swe-gym'}:
        raise ValueError('Select distinct supported sources')
    output.mkdir(parents=True, exist_ok=False)
    scripts = Path(__file__).parent.parent / 'storage-and-paired-sft-20261105'
    export = runpy.run_path(str(scripts / 'export_pairs.py'))['main']
    validate = runpy.run_path(str(scripts / 'validate_release.py'))['validate']
    from append_rewrite.terminus.tokenizer import PinnedTokenizer
    pinned = PinnedTokenizer(tokenizer)
    result = {'created_at': time.time(), 'new_model_requests': 0, 'sources': {}}
    for kind in sources:
        work = output / kind
        binding = snapshot(root / 'campaign-sft' / kind, work / 'input/campaign-sft')
        package = work / 'package'
        package.mkdir()
        if kind == 'cli-gym':
            shutil.copy2(support, package / 'pilot-history-support.json')
        else:
            (package / 'pilot-history-support.json').write_text('{}')
        export(work / 'input', package, tokenizer)
        check = validate(package, pinned)
        (work / 'validation.json').write_text(json.dumps(check, indent=2))
        summary = json.loads((package / 'manifest.json').read_text())
        result['sources'][kind] = {**binding, 'paired_count': summary['paired'],
            'pair_holds': len(summary['holds']), 'package': str(package),
            'manifest_sha256': sha((package / 'manifest.json').read_bytes()), 'validation': check}
        (output / 'progress.json').write_text(json.dumps(result, indent=2))
    (output / 'complete.json').write_text(json.dumps(result, indent=2))
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(__doc__)
    for name in ['root', 'output', 'tokenizer', 'history-support']:
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--sources', nargs='+', choices=['cli-gym', 'swe-gym'], default=['cli-gym', 'swe-gym'])
    a = p.parse_args()
    main(a.root, a.output, a.tokenizer, a.history_support, sources=a.sources)
