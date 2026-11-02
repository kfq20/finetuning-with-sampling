"""Grade one preserved interrupted-trial submission offline; no solver calls."""

from __future__ import annotations
import argparse
import json
from pathlib import Path
import time
import tomllib
from . import sandbox
from .collect import dump, sha


def run(a):
    receipt_path = a.attempt / "receipt.json"
    receipt = json.loads(receipt_path.read_text())
    archive = a.attempt / "partial-submission.tgz"
    if sha(archive) != receipt["partial_capture"]["archive_sha256"]:
        raise ValueError("CaptureIdentityMismatch")
    if a.output.exists():
        raise FileExistsError("Offline score already exists")
    row = json.loads((a.attempt / "source.json").read_text())
    task = Path(row["task_path"])
    artifacts = tomllib.loads((task / "task.toml").read_text())["artifacts"]
    for name, digest in receipt["task_tests"].items():
        if sha(task / name) != digest:
            raise ValueError("GraderIdentityMismatch")
    started = time.time()
    result = {
        "classification": "interrupted_submission_snapshot_only",
        "normal_model_completion": False,
        "new_model_requests": 0,
        "original_receipt_sha256": sha(receipt_path),
        "archive_sha256": sha(archive),
    }
    sb = None
    try:
        sb = sandbox.create(
            task,
            a.sandbox_credentials,
            "projection-native-offline-snapshot-" + a.attempt.name,
        )
        result["sandbox_id"] = sb.sandbox_id
        sandbox.prepare(sb, Path(row["state_path"]))
        sandbox.restore_archive(sb, archive, artifacts)
        result["score"] = sandbox.grade(sb, task)
        result["status"] = "offline_snapshot_scored"
    except Exception as exc:
        result.update(status="offline_snapshot_hold", error_type=type(exc).__name__)
    finally:
        if sb:
            sb.kill()
            result["sandbox_retired"] = True
        result["elapsed_seconds"] = time.time() - started
        dump(a.output, result)
    print(json.dumps(result))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--attempt", type=Path, required=True)
    parser.add_argument("--sandbox-credentials", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
