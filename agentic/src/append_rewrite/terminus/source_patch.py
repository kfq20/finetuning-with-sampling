"""Opt-in code-task capture; immutable registry base plus real submitted diff."""
import hashlib
from pathlib import Path
import re
from .docker_world import checked


def ensure_image(spec):
    import json
    from .docker_world import docker
    image = spec['template_id']
    q = docker('image', 'inspect', image)
    if q.returncode:
        reference = spec['source_registry_image']
        if not re.fullmatch(r'[a-z0-9._/:-]+@sha256:[0-9a-f]{64}', reference):
            raise ValueError('Immutable registry digest required')
        checked('pull', reference, timeout=900)
        actual = json.loads(checked('image', 'inspect', reference))[0]['Id']
        if actual != image:
            raise ValueError('Restored image identity drift')


def capture_patch(sb, destination):
    # Intent-to-add includes newly created source files without copying Git state.
    q = sb.run('set -euo pipefail; git ls-files --others --exclude-standard -z | '
               'xargs -0 -r git add -N --; git diff --binary HEAD', cwd='/testbed')
    if q.exit_code:
        raise RuntimeError('SourcePatchCaptureFailed')
    raw = q.stdout.encode()
    Path(destination).write_bytes(raw)
    return {'storage_format': 'git-source-diff.v1',
            'archive_sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}


def apply_patch(sb, submission):
    raw = Path(submission).read_bytes()
    sb.write('/tmp/owned-submission.patch', raw)
    if raw:
        q = sb.run('git apply --binary /tmp/owned-submission.patch', cwd='/testbed')
        if q.exit_code:
            raise RuntimeError('SourcePatchRestoreFailed')
