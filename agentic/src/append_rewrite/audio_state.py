"""Materialize original AudioEnvironment startup without invoking any model."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import tarfile
import shutil
from . import sandbox
from .collect import dump, sha


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--inventory", type=Path, required=True)
    p.add_argument("--sandbox-credentials", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--reuse", type=Path)
    a = p.parse_args()
    a.output.mkdir(parents=True, exist_ok=False, mode=0o700)
    entries = {}
    for row in json.loads(a.inventory.read_text())["rows"]:
        if row.get("holds") != ["needs_domain_state_adapter"] or not row[
            "tag"
        ].startswith("audio-"):
            continue
        sid = row["sample_id"]
        task = Path(row["task_path"])
        dest = a.output / sid
        dest.mkdir(mode=0o700)
        sb = None
        entry = {
            "task_path": str(task),
            "status": "preparing",
            "new_solver_requests": 0,
            "runtime_binding_sha256": sha(task / "runtime-binding.json"),
            "environment_files": {
                str(p.relative_to(task / "environment")): sha(p)
                for p in (task / "environment").rglob("*")
                if p.is_file()
            },
        }
        try:
            prior = a.reuse / sid / "source-state.tgz" if a.reuse else None
            if prior and prior.is_file():
                files = sandbox.archive_manifest(prior)
                shutil.copy2(prior, dest / "source-state.tgz")
                meta = {
                    "archive_sha256": sha(prior),
                    "files": files,
                    "reused_from": str(prior),
                }
            else:
                sb = sandbox.create(
                    task, a.sandbox_credentials, "projection-audio-source-" + sid
                )
                # Mirrors AudioEnvironment.start: writable mounts, then upload
                # environment_dir to /app in the original selected template.
                sandbox.command(sb, "mkdir -p /app/output", user="root", timeout=30)
                sandbox.upload(sb, task / "environment", "/app")
                meta = sandbox.capture(sb, ["/app/"], dest / "source-state.tgz")
            state = dest / "start_state"
            state.mkdir()
            with tarfile.open(dest / "source-state.tgz") as archive:
                for member in archive:
                    if member.isdir():
                        continue
                    name = Path(member.name)
                    if not name.is_relative_to("app"):
                        raise ValueError("UnexpectedSnapshotPath")
                    target = state / name.relative_to("app")
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(archive.extractfile(member).read())
                    target.chmod(member.mode & 511)
            files = {
                str(p.relative_to(state)): {
                    "sha256": sha(p),
                    "mode": p.stat().st_mode & 511,
                }
                for p in state.rglob("*")
                if p.is_file()
            }
            entry.update(
                status="snapshot_complete",
                state_path=str(state),
                files=files,
                capture=meta,
                template_id=json.loads((task / "runtime-binding.json").read_text())[
                    "template_id"
                ],
            )
        except Exception as exc:
            entry.update(
                status="hold",
                error_type=type(exc).__name__,
                error_code=str(exc)
                if str(exc)
                in ("UnsafeCaptureMember", "CaptureFailed", "StateUploadFailed")
                else None,
            )
        finally:
            if sb is not None:
                sb.kill()
        entries[sid] = entry
        dump(a.output / "index.json", entries)
        print(json.dumps({"sample_id": sid, "status": entry["status"]}), flush=True)


if __name__ == "__main__":
    main()
