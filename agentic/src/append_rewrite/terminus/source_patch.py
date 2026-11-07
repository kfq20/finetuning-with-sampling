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


def initialize_repo(sb, spec):
    base = spec['source_base_commit']
    if not re.fullmatch(r'[0-9a-f]{40}', base):
        raise ValueError('Pinned public base commit required')
    q = sb.run('git rev-parse HEAD', cwd='/testbed')
    if q.exit_code or q.stdout.strip() != base:
        raise ValueError('Source image base commit mismatch')
    # Official images may contain dependency edits (e.g. pyproject/pdm.lock).
    # Preserve that authentic initial state as a deterministic diff baseline.
    q = sb.run("set -e; git add -A; GIT_AUTHOR_DATE='2000-01-01T00:00:00+0000' "
               "GIT_COMMITTER_DATE='2000-01-01T00:00:00+0000' git "
               "-c user.name=Environment -c user.email=environment@example.invalid "
               "-c core.hooksPath=/dev/null -c commit.gpgsign=false "
               "commit --allow-empty -m 'Frozen environment baseline' >/dev/null; git rev-parse HEAD",
               cwd='/testbed')
    if q.exit_code:
        raise RuntimeError('Source baseline could not be frozen')
    commit = q.stdout.strip()
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise ValueError('Invalid frozen baseline identity')
    if spec.get('source_baseline_commit', commit) != commit:
        raise ValueError('Initial source tree identity drift')
    return commit


def capture_patch(sb, destination, baseline='HEAD'):
    if baseline != 'HEAD' and not re.fullmatch(r'[0-9a-f]{40}', baseline):
        raise ValueError('Invalid source diff baseline')
    # Intent-to-add includes newly created source files without copying Git state.
    q = sb.run('set -euo pipefail; git ls-files --others --exclude-standard -z | '
               'xargs -0 -r git add -N --; git diff --binary ' + baseline, cwd='/testbed', raw=True)
    if q.exit_code:
        raise RuntimeError('SourcePatchCaptureFailed')
    raw = q.stdout.encode() if isinstance(q.stdout, str) else q.stdout
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
