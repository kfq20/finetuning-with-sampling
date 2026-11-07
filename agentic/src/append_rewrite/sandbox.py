"""Owned cloud sandbox and immutable public-file restore, plus isolated grading."""

from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path
import shlex
import tarfile
import uuid
from types import SimpleNamespace


def command(sb, text, **kwargs):
    """Nonzero shell exits are tool observations, not SDK transport failures."""
    try:
        return sb.commands.run(text, **kwargs)
    except Exception as exc:
        if type(exc).__name__ != "CommandExitException":
            raise
        return SimpleNamespace(
            exit_code=exc.exit_code, stdout=exc.stdout, stderr=exc.stderr
        )


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def pack(root):
    out = io.BytesIO()
    with tarfile.open(fileobj=out, mode="w:gz") as t:
        for p in sorted(Path(root).rglob("*")):
            if p.is_symlink():
                raise ValueError("Public state symlink needs domain adapter")
            if p.is_file():
                t.add(p, arcname=str(p.relative_to(root)), recursive=False)
    return out.getvalue()


def upload(sb, root, destination):
    if hasattr(sb, 'upload_directory'):
        sb.upload_directory(Path(root), destination)
        return
    payload = pack(root)
    prefix = "/tmp/append-rewrite-" + uuid.uuid4().hex
    parts = []
    try:
        for offset in range(0, len(payload), 1048576):
            name = prefix + f".{len(parts):05d}.part"
            sb.files.write(
                name,
                payload[offset : offset + 1048576],
                user="root",
                request_timeout=240,
            )
            parts.append(name)
        archive = prefix + ".tgz"
        expected = hashlib.sha256(payload).hexdigest()
        script = (
            "cat "
            + " ".join(shlex.quote(x) for x in parts)
            + " > "
            + archive
            + " && test $(sha256sum "
            + archive
            + " | cut -d ' ' -f 1) = "
            + expected
            + " && mkdir -p "
            + shlex.quote(destination)
            + " && tar xzf "
            + archive
            + " -C "
            + shlex.quote(destination)
        )
        r = command(sb, script, user="root", timeout=120)
        if r.exit_code:
            raise RuntimeError("StateUploadFailed")
    finally:
        command(sb, "rm -f " + shlex.quote(prefix) + ".*", user="root", timeout=30)


def create(task, credential_file, owner, *, template_id=None):
    from dotenv import dotenv_values
    from e2b import Sandbox

    v = dotenv_values(credential_file, interpolate=False)
    binding = (
        json.loads((task / "runtime-binding.json").read_text())
        if template_id is None
        else {}
    )
    sb = Sandbox.create(
        template=template_id or binding["template_id"],
        timeout=3600,
        metadata={"envforge.owner": owner, "envforge.role": "qwen-append-rewrite"},
        network={"allow_out": [], "deny_out": ["0.0.0.0/0"]},
        api_key=v["E2B_API_KEY"],
        api_url=v["E2B_API_URL"],
        domain=v["E2B_DOMAIN"],
        request_timeout=60,
    )
    return sb


def prepare(sb, state):
    r = command(
        sb,
        "rm -rf /tests /solution /logs/verifier && mkdir -p /app",
        user="root",
        timeout=30,
    )
    if r.exit_code:
        raise RuntimeError("SolverSeparationFailed")
    for child in Path(state).iterdir():
        if child.name in (".", "..") or "/" in child.name:
            raise ValueError("InvalidStateRoot")
        r = command(
            sb, "rm -rf " + shlex.quote("/app/" + child.name), user="root", timeout=30
        )
        if r.exit_code:
            raise RuntimeError("StateResetFailed")
    upload(sb, state, "/app")


def grade(sb, task):
    # Only after the agent has stopped. Grader is never visible during rollout.
    r = command(
        sb,
        "rm -rf /tests /solution /logs/verifier && mkdir -p /logs/verifier",
        user="root",
        timeout=30,
    )
    if r.exit_code:
        raise RuntimeError("GraderSetupFailed")
    upload(sb, task / "tests", "/tests")
    import tomllib
    from .grading import parse_rewards

    config = tomllib.loads((task / "task.toml").read_text())
    r = command(
        sb,
        "cd /app && bash /tests/test.sh",
        user="root",
        timeout=config.get("verifier", {}).get("timeout_sec", 900),
    )
    if r.exit_code:
        raise RuntimeError("GraderInfrastructureError")
    channels = {}
    for name in ("reward.txt", "reward.json"):
        exists = command(sb, "test -f /logs/verifier/" + name, user="root", timeout=30)
        if exists.exit_code == 0:
            channels[name] = sb.files.read("/logs/verifier/" + name, user="root")
    value = parse_rewards(channels)
    if value is None:
        raise RuntimeError("RewardFileMissing")
    details = {}
    for name in (
        "checks.json",
        "grade.json",
        "details.json",
        "append-checks.json",
        "review-checks.json",
        "reconcile-checks.json",
    ):
        exists = command(sb, "test -f /logs/verifier/" + name, user="root", timeout=10)
        if exists.exit_code == 0:
            text = sb.files.read("/logs/verifier/" + name, user="root")
            try:
                details[name] = json.loads(text)
            except ValueError:
                # Reward remains authoritative; optional diagnostic stdout may
                # be empty on a legitimate rejected submission.
                details[name] = {
                    "format": "unparsed_diagnostic",
                    "sha256": hashlib.sha256(text.encode()).hexdigest(),
                    "bytes": len(text.encode()),
                }
    return {"reward": value, "details": details}


def capture(sb, artifacts, target):
    allowed = []
    for path in artifacts:
        if not path.startswith("/app/") or ".." in Path(path).parts:
            raise ValueError("Unexpected artifact scope")
        allowed.append(path.lstrip("/"))
    cmd = "tar czf /tmp/append-submission.tgz -C / " + " ".join(
        shlex.quote(p) for p in allowed
    )
    r = command(sb, cmd, user="root", timeout=120)
    if r.exit_code:
        raise RuntimeError("CaptureFailed")
    target.write_bytes(
        sb.files.read("/tmp/append-submission.tgz", format="bytes", user="root")
    )
    target.chmod(0o600)
    return {
        "archive_sha256": digest(target),
        "artifact_paths": artifacts,
        "files": archive_manifest(target),
    }


def archive_manifest(path):
    manifest = {}
    with tarfile.open(path, mode="r:gz") as t:
        for member in t.getmembers():
            p = Path(member.name)
            if (
                p.is_absolute()
                or ".." in p.parts
                or (
                    not member.name.startswith("app/")
                    and not (member.name == "app" and member.isdir())
                )
                or member.issym()
                or member.islnk()
            ):
                raise RuntimeError("UnsafeCaptureMember")
            if member.isfile():
                manifest[p.as_posix()] = {
                    "mode": member.mode & 511,
                    "sha256": hashlib.sha256(t.extractfile(member).read()).hexdigest(),
                }
    return manifest


def restore_archive(sb, path, artifacts):
    with tarfile.open(path, mode="r:gz") as t:
        for m in t.getmembers():
            p = Path(m.name)
            if (
                p.is_absolute()
                or ".." in p.parts
                or (
                    not m.name.startswith("app/")
                    and not (m.name == "app" and m.isdir())
                )
                or m.issym()
                or m.islnk()
            ):
                raise RuntimeError("UnsafeCaptureMember")
    for artifact in artifacts:
        if not artifact.startswith("/app/") or ".." in Path(artifact).parts:
            raise ValueError("UnexpectedArtifactScope")
        q = command(sb, "rm -rf " + shlex.quote(artifact), user="root", timeout=30)
        if q.exit_code:
            raise RuntimeError("RestoreResetFailed")
    payload = path.read_bytes()
    prefix = "/tmp/append-capture-" + uuid.uuid4().hex
    parts = []
    try:
        for offset in range(0, len(payload), 1048576):
            name = prefix + f".{len(parts):05d}.part"
            sb.files.write(
                name,
                payload[offset : offset + 1048576],
                user="root",
                request_timeout=240,
            )
            parts.append(name)
        q = command(
            sb,
            "cat "
            + " ".join(shlex.quote(x) for x in parts)
            + " > /tmp/append-submission.tgz && test $(sha256sum /tmp/append-submission.tgz | cut -d ' ' -f 1) = "
            + hashlib.sha256(payload).hexdigest(),
            user="root",
            timeout=120,
        )
        if q.exit_code:
            raise RuntimeError("CaptureUploadHashMismatch")
    finally:
        command(sb, "rm -f " + shlex.quote(prefix) + ".*", user="root", timeout=30)
    r = command(sb, "tar xzf /tmp/append-submission.tgz -C /", user="root", timeout=120)
    if r.exit_code:
        raise RuntimeError("RestoreFailed")
