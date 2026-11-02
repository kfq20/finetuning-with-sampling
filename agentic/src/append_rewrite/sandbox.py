"""Owned cloud sandbox and immutable public-file restore, plus isolated grading."""

from __future__ import annotations
import hashlib
import io
import json
from pathlib import Path
import shlex
import tarfile
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
    sb.files.write("/tmp/append-rewrite-upload.tgz", pack(root), user="root")
    r = command(
        sb,
        "mkdir -p "
        + shlex.quote(destination)
        + " && tar xzf /tmp/append-rewrite-upload.tgz -C "
        + shlex.quote(destination)
        + " && rm /tmp/append-rewrite-upload.tgz",
        user="root",
        timeout=120,
    )
    if r.exit_code:
        raise RuntimeError("StateUploadFailed")


def create(task, credential_file, owner):
    from dotenv import dotenv_values
    from e2b import Sandbox

    v = dotenv_values(credential_file, interpolate=False)
    binding = json.loads((task / "runtime-binding.json").read_text())
    sb = Sandbox.create(
        template=binding["template_id"],
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
    r = command(sb, "cd /app && bash /tests/test.sh", user="root", timeout=900)
    if r.exit_code:
        raise RuntimeError("GraderInfrastructureError")
    value = float(sb.files.read("/logs/verifier/reward.txt", user="root").strip())
    if value not in (0.0, 1.0):
        raise RuntimeError("InvalidReward")
    details = {}
    for name in (
        "checks.json",
        "append-checks.json",
        "review-checks.json",
        "reconcile-checks.json",
    ):
        exists = command(sb, "test -f /logs/verifier/" + name, user="root", timeout=10)
        if exists.exit_code == 0:
            details[name] = json.loads(
                sb.files.read("/logs/verifier/" + name, user="root")
            )
    return {"reward": value, "details": details}


def capture(sb, artifacts, target):
    allowed = []
    for path in artifacts:
        if not path.startswith("/app/") or ".." in Path(path).parts:
            raise ValueError("Unexpected artifact scope")
        allowed.append(path.lstrip("/"))
    command = "tar czf /tmp/append-submission.tgz -C / " + " ".join(
        shlex.quote(p) for p in allowed
    )
    r = command(sb, command, user="root", timeout=120)
    if r.exit_code:
        raise RuntimeError("CaptureFailed")
    target.write_bytes(
        sb.files.read("/tmp/append-submission.tgz", format="bytes", user="root")
    )
    target.chmod(0o600)
    return {"archive_sha256": digest(target), "artifact_paths": artifacts}


def restore_archive(sb, path):
    with tarfile.open(path, mode="r:gz") as t:
        for m in t.getmembers():
            p = Path(m.name)
            if (
                p.is_absolute()
                or ".." in p.parts
                or not m.name.startswith("app/")
                or m.issym()
                or m.islnk()
            ):
                raise RuntimeError("UnsafeCaptureMember")
    sb.files.write("/tmp/append-submission.tgz", path.read_bytes(), user="root")
    r = command(sb, "tar xzf /tmp/append-submission.tgz -C /", user="root", timeout=120)
    if r.exit_code:
        raise RuntimeError("RestoreFailed")
