"""Grade a user-stopped native episode from immutable captures, no model calls.

Does not signal workers or reconnect to a solver world. Requires the exact worker
to have exited and explicit operator-stop-start evidence. Original raw evidence
and error/receipts remain unchanged; this produces a separate operator receipt.
"""

import argparse
import json
from pathlib import Path
import time

from append_rewrite import sandbox
from append_rewrite.collect import dump, sha
from append_rewrite.terminus.owned_mvp import restore, fresh
from append_rewrite.terminus.protocol import public_messages, action


def run(args):
    out = args.output
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    attempt = args.attempt
    stop = json.loads((attempt / "operator-stop-start.json").read_text())
    if not stop["user_requested_stop"] or stop["normal_completion"]:
        raise ValueError("Explicit early-stop evidence required")
    process = Path(f"/proc/{stop['pid']}")
    if process.exists():
        stat = (process / "stat").read_text()
        if stat[stat.rfind(")") + 2 :].split()[19] == stop["start_ticks"]:
            raise RuntimeError("Wait for owned worker to exit")
    state = json.loads((attempt / "partial-state.json").read_text())["capture"]
    submission = json.loads((attempt / "partial-capture.json").read_text())
    if (
        sha(attempt / "partial-state.tgz") != state["archive_sha256"]
        or sha(attempt / "partial-submission.tgz") != submission["archive_sha256"]
    ):
        raise ValueError("Stopped capture drift")
    history = public_messages(
        json.loads((attempt / "public-messages.json").read_text())
    )
    responses = sorted(attempt.glob("generation/turn-*/response.json"))
    acted = [m["content"] for m in history if m["role"] == "assistant"]
    raw = [json.loads(p.read_text())["text"] for p in responses]
    if raw[: len(acted)] != acted:
        raise ValueError("Actual history differs from generation prefix")
    source = args.teacher / "inputs"
    record = {
        "terminal_reason": "operator_stopped_early",
        "normal_completed": False,
        "user_requested_stop": True,
        "new_model_requests": 0,
        "source_stop_sha256": sha(attempt / "operator-stop-start.json"),
        "current_state_sha256": state["archive_sha256"],
        "current_submission_sha256": submission["archive_sha256"],
        "executed_interactions": len(acted),
        "shell_commands": sum(len(action(a)["commands"]) for a in acted),
        "generated_responses": len(responses),
        "generated_but_unexecuted": len(responses) - len(acted),
        "scoring_closed": False,
        "started_at": time.time(),
        "review_tool_sha256": sha(Path(__file__)),
    }
    sb = None
    try:
        sb = restore(
            source / "task",
            source / "state",
            args.sandbox_credentials,
            "operator-stopped-state-review",
            args.runtime_assets,
        )
        sandbox.restore_archive(
            sb, attempt / "partial-state.tgz", ["/app/project", "/app/output"]
        )
        actual = sandbox.capture(
            sb, ["/app/project", "/app/output"], out / "restored-state.tgz"
        )
        if actual["files"] != state["files"]:
            raise ValueError("Stopped-state restore hash/mode mismatch")
        record["whole_state_restore_verified"] = True
        record["current_state_score"] = sandbox.grade(sb, source / "task")
        sb.kill()
        sb = None
        record["independent_submission_score"] = fresh(
            source / "task",
            source / "state",
            args.sandbox_credentials,
            attempt / "partial-submission.tgz",
            "operator-stopped-submission-review",
            args.runtime_assets,
        )
        record["scoring_closed"] = True
        record["scores_agree"] = (
            record["current_state_score"]["reward"]
            == record["independent_submission_score"]["reward"]
        )
    except BaseException as exc:
        record["review_error_type"] = type(exc).__name__
        raise
    finally:
        if sb is not None:
            sb.kill()
        record["finished_at"] = time.time()
        dump(out / "receipt.json", record)
    print(
        json.dumps(
            {
                k: v
                for k, v in record.items()
                if k not in ("current_state_score", "independent_submission_score")
            },
            ensure_ascii=False,
        )
    )
    print(
        "current_state_reward",
        record["current_state_score"]["reward"],
        "independent_submission_reward",
        record["independent_submission_score"]["reward"],
    )


def main():
    parser = argparse.ArgumentParser(__doc__)
    for name in (
        "attempt",
        "teacher",
        "sandbox-credentials",
        "runtime-assets",
        "output",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    run(parser.parse_args())


if __name__ == "__main__":
    main()
