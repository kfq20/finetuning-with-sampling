"""Grounded single-block rewrite: prefix state → proposals → execute/grade → LP.

Coq-only files/fresh-shell adapter. Replays teacher TOOLS, never teacher models.
Candidate feasibility includes executing the original delivery suffix with NEW
observations and original/fresh verifier success. Only feasible proposals can win.
"""

import argparse
import asyncio
import json
from pathlib import Path
import time
import shutil

from .. import sandbox
from ..collect import dump, sha
from .owned_mvp import restore, fresh
from .environment import SDKEnvironment
from .runtime import make_agent
from .tokenizer import PinnedTokenizer
from .native import NativeClient
from .protocol import action, digest, public_messages
from .scoring import render_candidate
from .export import export_row


class NoInference:
    async def call(self, **kwargs):
        raise AssertionError("Tool replay must not infer")


async def terminal(sb, output):
    agent = make_agent(output, "tool-replay-only", backend=NoInference())
    await agent.setup(SDKEnvironment(sb, "/app/project"))
    await agent._session.send_keys("cd /app/project\n", min_timeout_sec=0.1)
    return agent


async def execute(agent, raw):
    from harbor.agents.terminus_2.terminus_2 import Command

    parsed = agent._parser.parse_response(raw)
    if parsed.error:
        raise ValueError("Native action parse failed")
    timeout, observation = await agent._execute_commands(
        [
            Command(keystrokes=c.keystrokes, duration_sec=min(c.duration, 60))
            for c in parsed.commands
        ],
        agent._session,
    )
    if timeout:
        raise RuntimeError("Tool execution timeout")
    return observation


async def run(args):
    from harbor.agents.terminus_2.terminus_json_plain_parser import (
        TerminusJSONPlainParser,
    )

    out = args.output
    out.mkdir(parents=True, mode=0o700, exist_ok=False)
    start = time.time()
    teacher = args.teacher
    receipt = json.loads((teacher / "teacher-receipt.json").read_text())
    review = json.loads((teacher / "TEACHER-REVIEW.json").read_text())
    if (
        not receipt["expert_admitted_for_mvp"]
        or not review["approved_for_mvp_reference"]
    ):
        raise ValueError("Expert not admitted")
    source = teacher / "inputs"
    task, state = source / "task", source / "state"
    identity = json.loads((teacher / "input-manifest.json").read_text())
    for name, meta in identity["files"].items():
        if sha(source / name) != meta["sha256"]:
            raise ValueError("Frozen input drift")
    history = public_messages(
        json.loads((teacher / "teacher-public-messages.json").read_text())
    )
    target = args.expert_decision
    prefix = history[: 2 * (target - 1) + 1]
    target_raw = history[2 * target - 1]["content"]
    if prefix[-1]["role"] != "user":
        raise ValueError("Not at model boundary")
    parser = TerminusJSONPlainParser()
    p = parser.parse_response(target_raw)
    reference = json.dumps(
        {
            "next_expert_commands": [
                {"keystrokes": c.keystrokes, "duration": c.duration} for c in p.commands
            ],
            "requirement": "Rewrite this next proof-repair command batch, preserving its outcome and existing APIs. Apply the repair rather than restarting project exploration.",
        },
        ensure_ascii=False,
    )
    # Actual replay materializes the intermediate state; no final solved state
    # is substituted for the prefix checkpoint.
    if args.prepared_prefix:
        previous = args.prepared_prefix
        info = json.loads((previous / "checkpoint.json").read_text())
        if info["teacher_prefix_sha256"] != digest(prefix) or info["capture"][
            "archive_sha256"
        ] != sha(previous / "checkpoint.tgz"):
            raise ValueError("Prepared prefix identity drift")
        for name in ["checkpoint.tgz", "checkpoint.json", "initial-control.json"]:
            shutil.copyfile(previous / name, out / name)
        initial = json.loads((out / "initial-control.json").read_text())
        if initial["reward"] != 0:
            raise ValueError("Prepared prefix task already complete")
        dump(
            out / "prepared-prefix-binding.json",
            {
                "source": str(previous),
                "checkpoint_sha256": sha(previous / "checkpoint.tgz"),
                "model_generations_replayed": 0,
            },
        )
    else:
        sb = restore(
            task,
            state,
            args.sandbox_credentials,
            "block-mvp-prefix-replay",
            args.runtime_assets,
        )
        try:
            agent = await terminal(sb, out / "prefix-agent")
            observations = []
            for i in range(target - 1):
                raw = history[2 * i + 1]["content"]
                observations.append(await execute(agent, raw))
            active = await SDKEnvironment(sb, "/app/project").exec(
                command="tmux display-message -p -t terminus-2 '#{pane_current_command}'"
            )
            if active.stdout.strip() not in ["bash", "sh"]:
                raise ValueError("Prefix terminal not quiescent")
            snap = sandbox.capture(
                sb, ["/app/project", "/app/output"], out / "checkpoint.tgz"
            )
            dump(
                out / "checkpoint.json",
                {
                    "teacher_prefix_sha256": digest(prefix),
                    "capture": snap,
                    "expert_next_decision": target,
                    "scope": ["files", "fresh shell cwd"],
                    "replayed_teacher_model_requests": 0,
                },
            )
            dump(out / "prefix-replay-observations.json", observations)
            initial = sandbox.grade(sb, task)
            dump(out / "initial-control.json", initial)
            if initial["reward"] != 0:
                raise ValueError("Selected prefix task already complete")
        finally:
            sb.kill()
    suffix = [
        m["content"]
        for m in history[2 * target :]
        if m["role"] == "assistant" and parser.parse_response(m["content"]).commands
    ]

    async def evaluate(raw, label):
        branch = out / label
        branch.mkdir(mode=0o700)
        sb = restore(
            task,
            state,
            args.sandbox_credentials,
            "block-mvp-" + label,
            args.runtime_assets,
        )
        try:
            sandbox.restore_archive(
                sb, out / "checkpoint.tgz", ["/app/project", "/app/output"]
            )
            agent = await terminal(sb, branch / "agent")
            own_observation = await execute(agent, raw)
            dump(
                branch / "actual-candidate-observation.json",
                {"content": own_observation},
            )
            candidate_state = sandbox.capture(
                sb, ["/app/project", "/app/output"], branch / "candidate-state.tgz"
            )
            suffix_observations = []
            for following in suffix:
                suffix_observations.append(await execute(agent, following))
            dump(branch / "actual-suffix-observations.json", suffix_observations)
            capture = sandbox.capture(
                sb, ["/app/output/Submission.v"], branch / "submission.tgz"
            )
            original = sandbox.grade(sb, task)
            restored = fresh(
                task,
                state,
                args.sandbox_credentials,
                branch / "submission.tgz",
                "block-mvp-" + label + "-fresh",
                args.runtime_assets,
            )
            verdict = {
                "feasible": original["reward"] == restored["reward"] == 1,
                "original": original,
                "fresh": restored,
                "capture": capture,
                "candidate_state": candidate_state,
                "suffix_executed_with_actual_feedback": True,
            }
            dump(branch / "verdict.json", verdict)
            return verdict
        finally:
            sb.kill()

    if args.prepared_prefix:
        oracle_path = args.prepared_prefix / "expert-control/verdict.json"
        oracle = json.loads(oracle_path.read_text())
        dump(
            out / "expert-control-reused.json",
            {
                "source": str(oracle_path),
                "sha256": sha(oracle_path),
                "original_reward": oracle["original"]["reward"],
                "fresh_reward": oracle["fresh"]["reward"],
            },
        )
    else:
        oracle = await evaluate(target_raw, "expert-control")
    if not oracle["feasible"]:
        raise ValueError("Expert block/suffix control failed")
    noop = await evaluate(
        '{"analysis":"No-op control","plan":"Leave checkpoint unchanged","commands":[],"task_complete":false}',
        "noop-control",
    )
    if noop["feasible"]:
        raise ValueError("Target block is unnecessary: no-op plus suffix passes")
    t = PinnedTokenizer(args.tokenizer)
    client = NativeClient(args.fleet_config)
    private = prefix[:-1] + [
        {
            "role": "user",
            "content": prefix[-1]["content"]
            + "\n\n<expert_reference>\n"
            + reference
            + "\n</expert_reference>\nGenerate a replacement command batch for this same step. Use the original JSON response format.",
        }
    ]
    wire = t.apply_chat_template(private, tokenize=False, add_generation_prompt=True)
    results = []
    for i in range(2):
        result = await asyncio.to_thread(
            client.generate, wire, t, journal=out / f"generation-{i}"
        )
        raw = result["text"]
        action(raw)
        verdict = await evaluate(raw, f"candidate-{i}")
        rendered = render_candidate(prefix, raw, t, tokenizer_identity=t.identity)
        score = await asyncio.to_thread(
            client.score, rendered, journal=out / f"score-{i}"
        )
        score["generation_template_alignment_verified"] = True
        results.append(
            {
                "index": i,
                "raw": raw,
                "feasible": verdict["feasible"],
                "score": score,
                "verdict_path": str(out / f"candidate-{i}/verdict.json"),
            }
        )
        dump(out / "candidates.json", results)
    valid = [x for x in results if x["feasible"]]
    summary = {
        "algorithm": "grounded_greedy_block_rewrite_mvp",
        "expert_decision": target,
        "teacher_receipt_sha256": sha(teacher / "teacher-receipt.json"),
        "checkpoint_sha256": sha(out / "checkpoint.tgz"),
        "initial_reward": initial["reward"],
        "expert_control_feasible": True,
        "noop_control_feasible": False,
        "generated_candidates": 2,
        "feasible_candidates": len(valid),
        "model_replays": 0,
        "training_admitted": False,
        "elapsed_sec": time.time() - start,
    }
    if valid:
        best = max(valid, key=lambda x: x["score"]["mean_logprob"])
        row = export_row(
            prefix + [{"role": "assistant", "content": best["raw"]}],
            t,
            provenance={
                "teacher_receipt_sha256": summary["teacher_receipt_sha256"],
                "checkpoint_sha256": summary["checkpoint_sha256"],
                "candidate_index": best["index"],
                "verdict_sha256": sha(out / f"candidate-{best['index']}/verdict.json"),
                "scope": "one actual replacement block, expert prefix masked; real suffix validates feasibility",
            },
            target_start_message=len(prefix),
        )
        (out / "sft.jsonl").write_text(json.dumps(row, ensure_ascii=False) + "\n")
        summary.update(
            selected_index=best["index"],
            training_admitted=True,
            sft_sha256=sha(out / "sft.jsonl"),
            supervised_tokens=row["supervised_tokens"],
            total_tokens=row["total_tokens"],
        )
    dump(out / "receipt.json", summary)


def main():
    p = argparse.ArgumentParser(__doc__)
    for name in [
        "teacher",
        "tokenizer",
        "fleet-config",
        "sandbox-credentials",
        "runtime-assets",
        "output",
    ]:
        p.add_argument("--" + name, type=Path, required=True)
    p.add_argument("--expert-decision", type=int, required=True)
    p.add_argument("--prepared-prefix", type=Path)
    args = p.parse_args()
    try:
        asyncio.run(run(args))
    except Exception as exc:
        if args.output.exists():
            dump(
                args.output / "error.json",
                {
                    "error_type": type(exc).__name__,
                    "effective_completion": False,
                    "automatic_retry": False,
                },
            )
        raise


if __name__ == "__main__":
    main()
