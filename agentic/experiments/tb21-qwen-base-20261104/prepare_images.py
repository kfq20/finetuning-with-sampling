"""Mirror pinned official images without local pulls; keep task contents intact."""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import tomllib

from dotenv import dotenv_values


def prepare(root, crane, env_file, workers):
    os.umask(0o077)
    values = dotenv_values(env_file, interpolate=False)
    auth = root / 'private/registry-auth'
    auth.mkdir(parents=True, exist_ok=True)
    process_env = {**os.environ, 'DOCKER_CONFIG': str(auth)}
    registry = 'acr-rf-sg-registry.ap-southeast-8.cr.aliyuncs.com'

    def run(*args, **kwargs):
        result = subprocess.run([str(crane), *args], env=process_env, text=True,
                                capture_output=True, timeout=1200, **kwargs)
        if result.returncode:
            # Credentials must never enter logs or result files.
            message = result.stderr[-1200:]
            for key in ('REGISTRY_USERNAME', 'REGISTRY_PASSWORD'):
                message = message.replace(values[key], '<redacted>')
            raise RuntimeError(message)
        return result.stdout.strip()

    run('auth', 'login', registry, '-u', values['REGISTRY_USERNAME'],
        '--password-stdin', input=values['REGISTRY_PASSWORD'])
    (root / 'images').mkdir(exist_ok=True)

    def one(source):
        started = time.time()
        receipt = root / 'images' / (source.name + '.json')
        if receipt.exists() and (root / 'prepared-tasks' / source.name).exists():
            return json.loads(receipt.read_text())
        config = tomllib.loads((source / 'task.toml').read_text())
        image = config['environment']['docker_image']
        digest = run('digest', '--platform', 'linux/amd64', image)
        repository = image.split('@')[0].rsplit(':', 1)[0]
        tag = registry + '/mindlab/test:fanqi-tb21-base-1104-' + digest[7:31]
        run('copy', '--platform', 'linux/amd64', repository + '@' + digest, tag)
        assert run('digest', tag) == digest, 'Mirrored manifest differs'
        target_image = registry + '/mindlab/test@' + digest
        target = root / 'prepared-tasks' / source.name
        shutil.copytree(source, target, dirs_exist_ok=True)
        task = target / 'task.toml'
        text = task.read_text()
        assert text.count(image) == 1, 'Ambiguous image replacement'
        task.write_text(text.replace(image, target_image))
        hashes = {}
        for original in source.rglob('*'):
            if not original.is_file():
                continue
            relative = original.relative_to(source).as_posix()
            hashes[relative] = hashlib.sha256(original.read_bytes()).hexdigest()
            if relative != 'task.toml':
                assert hashlib.sha256((target / relative).read_bytes()).hexdigest() == hashes[relative]
        record = {'task': source.name, 'source_image': image, 'source_digest': digest,
                  'mirrored_image': target_image, 'manifest_digest_preserved': True,
                  'original_files': hashes, 'only_changed': ['task.toml:environment.docker_image'],
                  'started_at': started, 'finished_at': time.time(), 'model_requests': 0}
        receipt.write_text(json.dumps(record, indent=2) + '\n')
        return record

    tasks = sorted(p for p in (root / 'dataset/tasks').iterdir() if (p / 'task.toml').exists())
    failures = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(one, task): task.name for task in tasks}
        for future in as_completed(futures):
            name = futures[future]
            try:
                future.result()
                print(json.dumps({'task': name, 'prepared': True}), flush=True)
            except Exception as exc:
                failures.append({'task': name, 'error': type(exc).__name__, 'message': str(exc)})
                print(json.dumps(failures[-1]), flush=True)
    summary = {'total': len(tasks), 'prepared': len(tasks) - len(failures),
               'failures': failures, 'finished_at': time.time(), 'model_requests': 0}
    (root / 'image-preparation.json').write_text(json.dumps(summary, indent=2) + '\n')
    return 1 if failures else 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--crane', type=Path, required=True)
    parser.add_argument('--env-file', type=Path, required=True)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    raise SystemExit(prepare(args.root, args.crane, args.env_file, args.workers))
