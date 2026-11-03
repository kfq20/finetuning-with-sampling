"""Fixed-start, full-reference student episodes; score only AFTER real execution.

One sampled action per native decision, never per-action likelihood selection.
Each episode owns a fresh sandbox. No teacher tools or observations are replayed
as student execution. Old block experiments and their receipts are untouched.
"""

import argparse
import asyncio
import difflib
import json
import math
from pathlib import Path
import tarfile
import time

from .. import sandbox
from ..collect import dump, sha
from .environment import SDKEnvironment
from .export import export_row
from .native import NativeClient
from .owned_mvp import restore, fresh
from .protocol import action, digest, public_messages
from .runtime import make_agent, verify_pin
from .scoring import render_candidate
from .tokenizer import PinnedTokenizer


def generation_history(public, reference):
    """Reference is privileged conditioning in the first user turn only."""
    result = public_messages(public)
    if reference is not None:
        result[0]["content"] += (
            "\n\n<expert_reference>\n" + reference + "\n</expert_reference>\n"
            "The complete expert interaction is reference material, not your "
            "execution history. Solve the task using your own actual terminal "
            "feedback. Expert observations are historical and do not establish "
            "your current state. You may use a different valid approach."
        )
    return result


def aggregate_scores(scores):
    if not scores or any(s["token_count"] <= 0 for s in scores):
        raise ValueError("Missing episode action scores")
    total = sum(s["token_count"] for s in scores)
    value = math.fsum(s["sum_logprob"] for s in scores)
    return {
        "action_tokens": total,
        "sum_logprob": value,
        "mean_logprob": value / total,
        "decisions": len(scores),
        "observations_scored": False,
        "extra_expert_reference_in_score": False,
    }


class EpisodeLLM:
    def __init__(self, config, tokenizer, root, reference=None, *, stream=False):
        if stream:
            from .native_stream import NativeStreamClient

            self.client = NativeStreamClient(config)
        else:
            self.client = NativeClient(config)
        self.tokenizer, self.reference = tokenizer, reference
        self.root = Path(root)
        self.root.mkdir(mode=0o700, exist_ok=False)
        self.model_name = self.client.config["model_id"]
        self.decisions = []

    def get_model_context_limit(self):
        return 1000000

    def get_model_output_limit(self):
        return 128000

    async def call(self, prompt, message_history=None, **kwargs):
        from harbor.llms.base import LLMResponse, UsageInfo

        public = public_messages(
            list(message_history or []) + [{"role": "user", "content": prompt}]
        )
        wire = self.tokenizer.apply_chat_template(
            generation_history(public, self.reference),
            tokenize=False,
            add_generation_prompt=True,
        )
        out = self.root / f"turn-{len(self.decisions) + 1:04d}"
        start = time.monotonic()
        result = await asyncio.to_thread(
            self.client.generate, wire, self.tokenizer, journal=out
        )
        raw = result["text"]
        if any(t in raw for t in ("<think>", "</think>", "<thinking>", "</thinking>")):
            raise ValueError("Private reasoning wrapper in public response")
        meta = result["meta_info"]
        record = {
            "public_history_sha256": digest(public),
            "wire_sha256": digest(wire),
            "raw_action_sha256": digest(raw),
            "elapsed_sec": time.monotonic() - start,
            "usage": {
                k: meta.get(k)
                for k in ("prompt_tokens", "completion_tokens", "cached_tokens", "id")
            },
        }
        dump(out / "decision.json", record)
        self.decisions.append(record)
        return LLMResponse(
            content=raw,
            model_name=self.model_name,
            usage=UsageInfo(
                prompt_tokens=meta.get("prompt_tokens", 0),
                completion_tokens=meta.get("completion_tokens", 0),
                cache_tokens=meta.get("cached_tokens", 0) or 0,
                cost_usd=0.0,
            ),
        )


async def run(args):
    from harbor.models.agent.context import AgentContext

    teacher = args.teacher
    receipt = json.loads((teacher / "teacher-receipt.json").read_text())
    if not receipt["expert_admitted_for_mvp"] or any(
        receipt[k]["reward"] != 1 for k in ("original", "fresh")
    ):
        raise ValueError("Teacher not admitted")
    source = teacher / "inputs"
    identity = json.loads((teacher / "input-manifest.json").read_text())
    for name, item in identity["files"].items():
        p = source / name
        if sha(p) != item["sha256"] or p.stat().st_mode & 511 != item["mode"]:
            raise ValueError("Frozen task/state drift")
    expert = public_messages(
        json.loads((teacher / "teacher-public-messages.json").read_text())
    )
    reference = (
        json.dumps(expert, ensure_ascii=False) if args.mode == "reference" else None
    )
    variant = getattr(args, "algorithm", "full-episode")
    blockwise = variant == "latest-block-8"
    stream = variant == "full-episode-stream"
    algorithm = {
        "latest-block-8": "latest-block-logprob-8.v1",
        "full-episode-stream": "fixed-start-direct-stream.v1",
        "full-episode": "fixed-start-full-episode-rewrite.v1",
    }[variant]
    out = args.output
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    dump(
        out / "identity.json",
        {
            "algorithm": algorithm,
            "proposals_per_block": 8 if blockwise else 1,
            "online_likelihood_selection": blockwise,
            "scoring_protocol": "native-suffix-logprob-sse.v1"
            if blockwise
            else "native-full-input-nonstream.v1",
            "generation_transport": "native-sse-explicit-input-ids"
            if (blockwise or stream)
            else "native-buffered-text",
            "mode": args.mode,
            "teacher_receipt_sha256": sha(teacher / "teacher-receipt.json"),
            "teacher_history_sha256": sha(teacher / "teacher-public-messages.json"),
            "input_manifest_sha256": sha(teacher / "input-manifest.json"),
            "harbor": verify_pin(),
            "reference_messages": len(expert) if reference else 0,
            "expert_prefix_replayed": False,
            "expert_suffix_executed": False,
            "runtime_assets_sha256": sha(args.runtime_assets / "manifest.json"),
        },
    )
    tokenizer = PinnedTokenizer(args.tokenizer)
    sb = None
    phases = {}
    started = time.monotonic()
    try:
        sb = restore(
            source / "task",
            source / "state",
            args.sandbox_credentials,
            "fixed-start-qwen-episode",
            args.runtime_assets,
        )
        dump(out / "sandbox.json", {"sandbox_id": sb.sandbox_id})
        if blockwise:
            from .blockwise import BlockwiseLLM

            backend = BlockwiseLLM(
                args.fleet_config, tokenizer, out / "generation", reference, proposals=8
            )
        else:
            backend = EpisodeLLM(
                args.fleet_config,
                tokenizer,
                out / "generation",
                reference,
                stream=stream,
            )
        agent = make_agent(out / "agent", backend.model_name, backend=backend)
        env = SDKEnvironment(sb, "/app/project")
        await agent.setup(env)
        await agent._session.send_keys("cd /app/project\n", min_timeout_sec=0.1)
        phases["setup_sec"] = time.monotonic() - started
        ctx = AgentContext()
        rollout_start = time.monotonic()
        try:
            await asyncio.wait_for(
                agent.run((source / "instruction.md").read_text(), env, ctx), 28800
            )
        finally:
            if agent._chat:
                dump(
                    out / "public-messages.json", public_messages(agent._chat.messages)
                )
            dump(out / "context.json", ctx.model_dump(mode="json"))
            phases["rollout_sec"] = time.monotonic() - rollout_start
            dump(out / "phases.json", phases)
        history = public_messages(agent._chat.messages)
        complete = len(history) >= 4 and all(
            agent._parser.parse_response(m["content"]).is_task_complete
            for m in (history[-3], history[-1])
        )
        if not complete:
            raise RuntimeError("StudentDidNotConfirmCompletion")
        before = time.monotonic()
        submission_present = (
            sandbox.command(
                sb, "test -f /app/output/Submission.v", user="root", timeout=30
            ).exit_code
            == 0
        )
        capture = sandbox.capture(
            sb,
            ["/app/output/Submission.v"] if submission_present else ["/app/output"],
            out / "submission.tgz",
        )
        original = sandbox.grade(sb, source / "task")
        if submission_present:
            restored = fresh(
                source / "task",
                source / "state",
                args.sandbox_credentials,
                out / "submission.tgz",
                "fixed-start-qwen-fresh",
                args.runtime_assets,
            )
        else:
            empty = restore(
                source / "task",
                source / "state",
                args.sandbox_credentials,
                "fixed-start-empty-submission-grade",
                args.runtime_assets,
            )
            try:
                restored = sandbox.grade(empty, source / "task")
            finally:
                empty.kill()
        phases["capture_grading_sec"] = time.monotonic() - before

        def submitted(path):
            with tarfile.open(path, "r:gz") as archive:
                if "app/output/Submission.v" not in archive.getnames():
                    return ""
                return archive.extractfile("app/output/Submission.v").read().decode()

        student, gold = (
            submitted(out / "submission.tgz"),
            submitted(teacher / "teacher-submission.tgz"),
        )
        passed = original["reward"] == restored["reward"] == 1
        record = {
            "terminal_reason": "completed",
            "algorithm": algorithm,
            "intermediate_verifier_calls": 0,
            "environment_rollbacks": 0,
            "execution_closed_normally": True,
            "original": original,
            "fresh": restored,
            "capture": capture,
            "submission_present": submission_present,
            "mode": args.mode,
            "training_admitted": False,
            "decisions": len(backend.decisions),
            "tool_commands": sum(
                len(action(m["content"])["commands"])
                for m in history
                if m["role"] == "assistant"
            ),
            "copy_audit": {
                "exact_submission_match": student == gold,
                "submission_similarity": difflib.SequenceMatcher(
                    None, student, gold
                ).ratio(),
            },
            "phases": phases,
        }
        # Preserve completed execution even if later offline likelihood work fails.
        dump(out / "execution-receipt.json", record)
        if blockwise:
            selected_scores = [
                d["candidates"][d["selected_index"]]["score"] for d in backend.decisions
            ]
            record["likelihood"] = aggregate_scores(selected_scores)
            record["proposals_per_block"] = 8
            record["proposals_total"] = sum(
                d["candidate_count"] for d in backend.decisions
            )
        if (passed or stream) and not blockwise:
            before = time.monotonic()
            scores = []
            for i, m in enumerate(history):
                if m["role"] == "assistant":
                    rendered = render_candidate(
                        history[:i],
                        m["content"],
                        tokenizer,
                        tokenizer_identity=tokenizer.identity,
                    )
                    scores.append(
                        await asyncio.to_thread(
                            backend.client.score,
                            rendered,
                            journal=out / "scores" / f"action-{len(scores) + 1:04d}",
                        )
                    )
            phases["unreferenced_scoring_sec"] = time.monotonic() - before
            record["likelihood"] = aggregate_scores(scores)
        if passed:
            row = export_row(
                history,
                tokenizer,
                provenance={
                    "algorithm": algorithm,
                    "mode": args.mode,
                    "teacher_receipt_sha256": sha(teacher / "teacher-receipt.json"),
                    "input_manifest_sha256": sha(teacher / "input-manifest.json"),
                    "capture_sha256": capture["archive_sha256"],
                    "reference_removed": True,
                },
            )
            (out / "sft.jsonl").write_text(json.dumps(row, ensure_ascii=False) + "\n")
            record.update(
                training_admitted=True,
                sft_sha256=sha(out / "sft.jsonl"),
                total_tokens=row["total_tokens"],
                supervised_tokens=row["supervised_tokens"],
            )
        phases["total_sec"] = time.monotonic() - started
        dump(out / "receipt.json", record)
    except BaseException as exc:
        dump(
            out / "error.json",
            {
                "error_type": type(exc).__name__,
                "effective_completion": False,
                "automatic_retry": False,
                "execution_receipt_preserved": (
                    out / "execution-receipt.json"
                ).exists(),
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
            except Exception as capture_error:
                dump(
                    out / "partial-capture-error.json",
                    {"error_type": type(capture_error).__name__},
                )
            try:
                state_capture = sandbox.capture(
                    sb, ["/app/project", "/app/output"], out / "partial-state.tgz"
                )
                dump(
                    out / "partial-state.json",
                    {
                        "capture": state_capture,
                        "scope": "files only; no process rollback claim",
                    },
                )
            except Exception as state_error:
                dump(
                    out / "partial-state-error.json",
                    {"error_type": type(state_error).__name__},
                )
        raise
    finally:
        if sb is not None:
            sb.kill()


def main():
    p = argparse.ArgumentParser(__doc__)
    for name in (
        "teacher",
        "tokenizer",
        "fleet-config",
        "sandbox-credentials",
        "runtime-assets",
        "output",
    ):
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--mode", choices=("reference", "no-reference"), required=True)
    p.add_argument(
        "--algorithm",
        choices=("full-episode", "full-episode-stream", "latest-block-8"),
        default="full-episode",
    )
    asyncio.run(run(p.parse_args()))


if __name__ == "__main__":
    main()
