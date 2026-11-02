"""One actual Qwen rewrite using a fresh admitted Terminus DeepSeek expert."""

import argparse
import asyncio
import json
from pathlib import Path
import time
import tarfile
import difflib

from ..collect import dump, sha
from .. import sandbox
from .owned_mvp import restore, fresh
from .environment import SDKEnvironment
from .runtime import make_agent
from .native import NativeRewriteLLM
from .tokenizer import PinnedTokenizer
from .protocol import public_messages
from .export import export_row


async def run(args):
    from harbor.models.agent.context import AgentContext
    from harbor.agents.terminus_2.terminus_json_plain_parser import (
        TerminusJSONPlainParser,
    )

    teacher = args.teacher
    receipt = json.loads((teacher / "teacher-receipt.json").read_text())
    if (
        not receipt["expert_admitted_for_mvp"]
        or receipt["original"]["reward"] != 1
        or receipt["fresh"]["reward"] != 1
    ):
        raise ValueError("Teacher not admitted")
    source = teacher / "inputs"
    task, state = source / "task", source / "state"
    identity = json.loads((teacher / "input-manifest.json").read_text())
    for name, item in identity["files"].items():
        p = source / name
        if sha(p) != item["sha256"] or p.stat().st_mode & 511 != item["mode"]:
            raise ValueError("Frozen teacher task/state drift")
    h = json.loads((teacher / "teacher-public-messages.json").read_text())
    parser = TerminusJSONPlainParser()
    reference = []
    for i, m in enumerate(h):
        if m["role"] != "assistant":
            continue
        p = parser.parse_response(m["content"])
        if p.error:
            raise ValueError("Invalid teacher action")
        reference.append(
            {
                "commands": [
                    {"keystrokes": c.keystrokes, "duration": c.duration}
                    for c in p.commands
                ],
                "task_complete": p.is_task_complete,
                "actual_observation": h[i + 1]["content"] if i + 1 < len(h) else None,
            }
        )
    out = args.output
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    dump(out / "reference-public-actions.json", reference)
    dump(
        out / "identity.json",
        {
            "teacher_receipt_sha256": sha(teacher / "teacher-receipt.json"),
            "teacher_history_sha256": sha(teacher / "teacher-public-messages.json"),
            "input_manifest_sha256": sha(teacher / "input-manifest.json"),
            "harness": "harbor-terminus-2-json.v1",
            "model": "Qwen/Qwen3.8-27B",
            "algorithm": "greedy_native_block_rewrite_mvp",
            "proposals_per_decision": 2,
        },
    )
    tokenizer = PinnedTokenizer(args.tokenizer)
    sb = None
    start = time.time()
    try:
        sb = restore(
            task,
            state,
            args.sandbox_credentials,
            "owned-terminus-mvp-qwen",
            args.runtime_assets,
        )
        dump(out / "sandbox.json", {"sandbox_id": sb.sandbox_id})
        backend = NativeRewriteLLM(
            args.fleet_config,
            tokenizer,
            out / "candidates",
            json.dumps(reference, ensure_ascii=False),
            proposals=2,
        )
        agent = make_agent(out / "agent", backend.model_name, backend=backend)
        env = SDKEnvironment(sb, "/app/project")
        await agent.setup(env)
        await agent._session.send_keys("cd /app/project\n", min_timeout_sec=0.1)
        ctx = AgentContext()
        try:
            await asyncio.wait_for(
                agent.run((source / "instruction.md").read_text(), env, ctx), 28800
            )
        finally:
            if agent._chat:
                dump(
                    out / "student-public-messages.json",
                    public_messages(agent._chat.messages),
                )
            dump(out / "context.json", ctx.model_dump(mode="json"))
        h = agent._chat.messages
        if len(h) < 4 or not all(
            agent._parser.parse_response(m["content"]).is_task_complete
            for m in [h[-3], h[-1]]
        ):
            raise RuntimeError("StudentDidNotConfirmCompletion")
        capture = sandbox.capture(
            sb, ["/app/output/Submission.v"], out / "submission.tgz"
        )
        original = sandbox.grade(sb, task)
        restored = fresh(
            task,
            state,
            args.sandbox_credentials,
            out / "submission.tgz",
            "owned-terminus-mvp-student-fresh",
            args.runtime_assets,
        )
        passed = original["reward"] == restored["reward"] == 1
        audit = {}

        def submitted(path):
            with tarfile.open(path, "r:gz") as t:
                return t.extractfile("app/output/Submission.v").read().decode()

        expert_text, student_text = (
            submitted(teacher / "teacher-submission.tgz"),
            submitted(out / "submission.tgz"),
        )
        audit = {
            "exact_submission_match": expert_text == student_text,
            "submission_text_similarity": difflib.SequenceMatcher(
                None, expert_text, student_text
            ).ratio(),
        }
        dump(out / "copy-audit.json", audit)
        record = {
            "terminal_reason": "completed",
            "original": original,
            "fresh": restored,
            "capture": capture,
            "elapsed_sec": time.time() - start,
            "decisions": backend.turn,
            "training_admitted": False,
            "copy_audit": audit,
        }
        if passed:
            row = export_row(
                h,
                tokenizer,
                provenance={
                    "teacher_receipt_sha256": sha(teacher / "teacher-receipt.json"),
                    "capture_sha256": capture["archive_sha256"],
                    "source_input_manifest_sha256": sha(
                        teacher / "input-manifest.json"
                    ),
                    "algorithm": "greedy_native_block_rewrite_mvp",
                    "reference_removed": True,
                },
            )
            (out / "sft.jsonl").write_text(json.dumps(row, ensure_ascii=False) + "\n")
            record.update(
                training_admitted=True,
                sft_sha256=sha(out / "sft.jsonl"),
                supervised_tokens=row["supervised_tokens"],
                total_tokens=row["total_tokens"],
            )
        dump(out / "receipt.json", record)
    except Exception as exc:
        dump(
            out / "error.json",
            {
                "error_type": type(exc).__name__,
                "effective_completion": False,
                "automatic_retry": False,
            },
        )
        if sb is not None and not (out / "submission.tgz").exists():
            try:
                dump(
                    out / "partial-capture.json",
                    sandbox.capture(
                        sb, ["/app/output/Submission.v"], out / "partial-submission.tgz"
                    ),
                )
            except Exception:
                pass
        raise
    finally:
        if sb is not None:
            sb.kill()


def main():
    p = argparse.ArgumentParser(__doc__)
    for x in [
        "teacher",
        "tokenizer",
        "fleet-config",
        "sandbox-credentials",
        "runtime-assets",
        "output",
    ]:
        p.add_argument("--" + x, type=Path, required=True)
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
