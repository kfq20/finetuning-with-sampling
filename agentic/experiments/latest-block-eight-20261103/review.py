"""Offline integrity review and observable-only comparison, no model requests."""

import argparse
import hashlib
import json
from pathlib import Path

from append_rewrite.terminus.protocol import action, digest, public_messages
from append_rewrite.terminus.validate import validate_row


def review(root):
    receipt = json.loads((root / "receipt.json").read_text())
    history = public_messages(json.loads((root / "public-messages.json").read_text()))
    assistants = [m["content"] for m in history if m["role"] == "assistant"]
    turns = sorted(root.glob("generation/turn-*/decision.json"))
    assert len(turns) == len(assistants) == receipt["decisions"]
    rows, usage, ids, command_batches = [], [], [], []
    for index, path in enumerate(turns):
        value = json.loads(path.read_text())
        prefix = history[: 2 * index + 1]
        assert value["public_history_sha256"] == digest(prefix)
        candidates = value["candidates"]
        assert value["candidate_count"] == len(candidates) == 8
        valid = [c for c in candidates if c["status"] == "scored"]
        best = max(valid, key=lambda c: c["score"]["mean_logprob"])
        assert best["index"] == value["selected_index"]
        assert best["raw"] == assistants[index]
        for candidate in valid:
            score = candidate["score"]
            assert score["history_sha256"] == digest(prefix)
            assert (
                score["action_sha256"]
                == hashlib.sha256(candidate["raw"].encode()).hexdigest()
            )
        for candidate in candidates:
            p = path.parent / f"proposal-{candidate['index']}"
            result = json.loads((p / "response.json").read_text())
            transport = json.loads((p / "transport.json").read_text())
            assert transport["complete_stop"]
            assert result["text"] == candidate["raw"]
            assert result["meta_info"]["finish_reason"]["type"] == "stop"
            ids.append(result["meta_info"]["id"])
            usage.append(result["meta_info"])
        chosen = action(best["raw"])
        batch = chosen["commands"]
        command_batches.append(batch)
        rows.append(
            {
                "block": index + 1,
                "selected_index": best["index"],
                "scored_candidates": len(valid),
                "mean_logprob": best["score"]["mean_logprob"],
                "unique_command_batches": len(
                    {digest(action(c["raw"])["commands"]) for c in valid}
                ),
                "selected_commands": [c["keystrokes"] for c in batch],
                "task_complete": chosen.get("task_complete", False),
                "candidate_scores": [
                    {
                        "index": c["index"],
                        "mean_logprob": c["score"]["mean_logprob"],
                        "tokens": c["score"]["token_count"],
                    }
                    for c in valid
                ],
            }
        )
    assert len(ids) == len(set(ids))
    assert not list(root.glob("**/error.json"))
    commands = [c["keystrokes"] for batch in command_batches for c in batch]
    assert not any(
        path in command
        for command in commands
        for path in ("/tests/", "/solution/", ".secrets")
    )
    nonempty = [digest(b) for b in command_batches if b]
    repeated = len(nonempty) - len(set(nonempty))
    result = {
        "passed_integrity_review": True,
        "receipt_sha256": hashlib.sha256(
            (root / "receipt.json").read_bytes()
        ).hexdigest(),
        "blocks": len(turns),
        "generated_candidates": len(ids),
        "scored_candidates": sum(r["scored_candidates"] for r in rows),
        "shell_commands": len(commands),
        "exact_repeated_nonempty_batches": repeated,
        "peak_input_tokens_with_reference": max(u["prompt_tokens"] for u in usage),
        "generation_input_tokens": sum(u["prompt_tokens"] for u in usage),
        "generation_output_tokens": sum(u["completion_tokens"] for u in usage),
        "original_reward": receipt["original"]["reward"],
        "fresh_reward": receipt["fresh"]["reward"],
        "phases": receipt["phases"],
        "copy_audit": receipt["copy_audit"],
        "intermediate_verifier_calls": 0,
        "environment_rollbacks": 0,
        "api_errors": 0,
        "actual_history_and_scoring_identity_verified": True,
        "rows": rows,
    }
    if (root / "sft.jsonl").exists():
        result["sft"] = validate_row(json.loads((root / "sft.jsonl").read_text()))
    return result


def main():
    parser = argparse.ArgumentParser(__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    result = review(args.root)
    (args.root / "QUALITY-REVIEW.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    lines = [
        "# Latest-block eight-candidate pilot",
        "",
        "At each block, eight candidates were sampled with the full expert reference. Highest unreferenced mean action logprob won; only that candidate executed.",
        "",
        "| Block | Selected candidate (0-based) | Scored | Distinct command batches | Selected mean logprob |",
        "|---|---:|---:|---:|---:|",
    ]
    for r in result["rows"]:
        lines.append(
            f"| {r['block']} | {r['selected_index']} | {r['scored_candidates']} | {r['unique_command_batches']} | {r['mean_logprob']:.6f} |"
        )
    lines += [
        "",
        f"Final original/fresh rewards: {result['original_reward']}/{result['fresh_reward']}.",
        f"Blocks: {result['blocks']}; candidates: {result['generated_candidates']}; shell commands: {result['shell_commands']}.",
        f"Exact repeated nonempty command batches: {result['exact_repeated_nonempty_batches']}. This counts literal duplicates, not semantic loops.",
        "",
        "Selected observable commands follow. No provider-private reasoning is included.",
    ]
    for r in result["rows"]:
        lines += [
            "",
            f"## Block {r['block']}",
            "",
            "```sh",
            "\n".join(r["selected_commands"])
            or "# Completion confirmation; no commands",
            "```",
        ]
    (args.root / "REVIEW.md").write_text("\n".join(lines) + "\n")
    print(
        json.dumps({k: v for k, v in result.items() if k != "rows"}, ensure_ascii=False)
    )


if __name__ == "__main__":
    main()
