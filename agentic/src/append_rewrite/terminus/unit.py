"""One owned Coq append unit: fresh native teacher then full student episode.

This adapter supports the existing Submission.v contract. Other domains require
explicit artifact/state adapters; the source index alone never admits them.
"""

import argparse
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
import time

from ..collect import dump, sha
from . import owned_mvp, episode
from .protocol import action, public_messages


async def run(args):
    out = args.output
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    started = time.monotonic()
    dump(
        out / "status.json",
        {"phase": "teacher_controls_and_rollout", "automatic_retry": False},
    )
    try:
        await owned_mvp.run(
            SimpleNamespace(
                source_protocol=args.source_protocol,
                teacher_config=args.teacher_config,
                sandbox_credentials=args.sandbox_credentials,
                runtime_assets=args.runtime_assets,
                output=out / "teacher",
            )
        )
        teacher = out / "teacher"
        receipt = json.loads((teacher / "teacher-receipt.json").read_text())
        assert receipt["expert_admitted_for_mvp"]
        history = public_messages(
            json.loads((teacher / "teacher-public-messages.json").read_text())
        )
        commands = [
            c["keystrokes"]
            for m in history
            if m["role"] == "assistant"
            for c in action(m["content"])["commands"]
        ]
        if any(
            path in c for c in commands for path in ("/tests", "/solution", ".secrets")
        ):
            raise ValueError("TeacherPrivatePathReviewRequired")
        dump(
            out / "status.json",
            {
                "phase": "full_reference_student",
                "teacher_receipt_sha256": sha(teacher / "teacher-receipt.json"),
            },
        )
        await episode.run(
            SimpleNamespace(
                teacher=teacher,
                tokenizer=args.tokenizer,
                fleet_config=args.fleet_config,
                sandbox_credentials=args.sandbox_credentials,
                runtime_assets=args.runtime_assets,
                output=out / "student",
                mode="reference",
            )
        )
        student = json.loads((out / "student/receipt.json").read_text())
        dump(
            out / "unit-receipt.json",
            {
                "teacher_receipt_sha256": sha(teacher / "teacher-receipt.json"),
                "student_receipt_sha256": sha(out / "student/receipt.json"),
                "source_protocol_sha256": sha(args.source_protocol),
                "training_admitted": student["training_admitted"],
                "original_reward": student["original"]["reward"],
                "fresh_reward": student["fresh"]["reward"],
                "elapsed_sec": time.monotonic() - started,
                "automatic_retry": False,
            },
        )
        dump(
            out / "status.json",
            {"phase": "completed", "training_admitted": student["training_admitted"]},
        )
    except BaseException as exc:
        dump(
            out / "status.json",
            {
                "phase": "error",
                "error_type": type(exc).__name__,
                "automatic_retry": False,
                "completed_substeps_preserved": True,
            },
        )
        raise


def main():
    parser = argparse.ArgumentParser(__doc__)
    for name in (
        "source-protocol",
        "teacher-config",
        "tokenizer",
        "fleet-config",
        "sandbox-credentials",
        "runtime-assets",
        "output",
    ):
        parser.add_argument("--" + name, type=Path, required=True)
    asyncio.run(run(parser.parse_args()))


if __name__ == "__main__":
    main()
