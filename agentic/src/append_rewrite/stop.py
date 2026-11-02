"""User-requested stop: preserve the live world, score it, never call a model.

The caller must first SIGSTOP the identity-verified owned worker and record
operator-stop-start.json. This entry retires that exact worker and owned sandbox.
Original inference evidence is preserved; operator results are separate receipts.
"""

from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import signal
import time
import tomllib
from . import sandbox
from .collect import dump, sha


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--attempt", type=Path, required=True)
    p.add_argument("--sandbox-credentials", type=Path, required=True)
    a = p.parse_args()
    out = a.attempt / "operator-review"
    out.mkdir(mode=0o700, exist_ok=False)
    stop = json.loads((a.attempt / "operator-stop-start.json").read_text())
    source = json.loads((a.attempt / "source.json").read_text())
    task = Path(source["task_path"])
    config = tomllib.loads((task / "task.toml").read_text())
    from dotenv import dotenv_values
    from e2b import Sandbox, SandboxQuery

    v = dotenv_values(a.sandbox_credentials, interpolate=False)
    opts = dict(
        api_key=v["E2B_API_KEY"], api_url=v["E2B_API_URL"], domain=v["E2B_DOMAIN"]
    )
    owner = "projection-agent-20261102-" + source["sample_id"]
    pages = Sandbox.list(query=SandboxQuery(metadata={"envforge.owner": owner}), **opts)
    ids = []
    while pages.has_next:
        ids += [s.sandbox_id for s in pages.next_items()]
    if stop["sandbox_id"] not in ids:
        raise ValueError("OwnedSandboxIdentityMismatch")
    sb = Sandbox.connect(sandbox_id=stop["sandbox_id"], **opts)
    fresh = None
    result = {
        "status": "operator_stopped_not_normal_completion",
        "normal_completed": False,
        "user_requested_stop": True,
        "new_model_requests": 0,
        "originals_unchanged": True,
        "attempt_path": str(a.attempt),
        "stop_start_sha256": sha(a.attempt / "operator-stop-start.json"),
        "started_at": time.time(),
    }
    try:
        proc = Path(f"/proc/{stop['pid']}")
        if proc.exists():
            stat = proc.joinpath("stat").read_text().split()
            assert stat[21] == stop["start_ticks"] and stat[2] == "T"
            assert "append_rewrite.run" in proc.joinpath(
                "cmdline"
            ).read_bytes().decode().replace("\0", " ")
            os.kill(stop["pid"], signal.SIGTERM)
            os.kill(stop["pid"], signal.SIGCONT)
        result["full_app_capture"] = sandbox.capture(
            sb, ["/app/"], out / "full-app-state.tgz"
        )
        q = sandbox.command(
            sb,
            "if test -d /tmp/dev; then tar czf /tmp/observer-debug.tgz -C / tmp/dev; else exit 3; fi",
            user="root",
            timeout=120,
        )
        if q.exit_code == 0:
            (out / "debug-tmp-dev.tgz").write_bytes(
                sb.files.read("/tmp/observer-debug.tgz", format="bytes", user="root")
            )
            result["debug_capture_sha256"] = sha(out / "debug-tmp-dev.tgz")
        result["artifact_presence"] = {
            path: sandbox.command(
                sb,
                "test -e " + __import__("shlex").quote(path),
                user="root",
                timeout=10,
            ).exit_code
            == 0
            for path in config["artifacts"]
        }
        result["score_current_submission"] = sandbox.grade(sb, task)
        fresh = sandbox.create(
            task,
            a.sandbox_credentials,
            "projection-agent-20261102-stopped-fresh-" + source["sample_id"],
        )
        sandbox.restore_archive(fresh, out / "full-app-state.tgz", ["/app/"])
        restored = sandbox.capture(fresh, ["/app/"], out / "fresh-app-state.tgz")
        result["fresh_app_files_match"] = (
            restored["files"] == result["full_app_capture"]["files"]
        )
        if not result["fresh_app_files_match"]:
            raise ValueError("FreshFileMismatch")
        result["fresh_score_current_submission"] = sandbox.grade(fresh, task)
        if (
            result["score_current_submission"]["reward"]
            != result["fresh_score_current_submission"]["reward"]
        ):
            raise ValueError("FreshScoreMismatch")
        result["scoring_closed"] = True
    except Exception as exc:
        result["scoring_error_type"] = type(exc).__name__
        result["scoring_closed"] = False
    finally:
        for name, instance in [("original", sb), ("fresh", fresh)]:
            if instance is not None:
                try:
                    instance.kill()
                    result[name + "_sandbox_retired"] = True
                except Exception as exc:
                    result[name + "_cleanup_error_type"] = type(exc).__name__
        result["finished_at"] = time.time()
        result["evidence_files"] = {
            str(p.relative_to(a.attempt)): sha(p)
            for p in a.attempt.rglob("*")
            if p.is_file() and "operator-review" not in p.relative_to(a.attempt).parts
        }
        dump(out / "receipt.json", result)
    print(
        json.dumps(
            {
                k: v
                for k, v in result.items()
                if k not in ("evidence_files", "full_app_capture")
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
