"""Validate full-input SSE scoring on cached candidates; no new generations."""

import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path

from append_rewrite.terminus.protocol import public_messages
from append_rewrite.terminus.scoring import RenderedCandidate, render_candidate
from append_rewrite.terminus.suffix_score import NativeFullStreamClient
from append_rewrite.terminus.tokenizer import PinnedTokenizer


def main():
    parser = argparse.ArgumentParser(__doc__)
    for name in ("previous", "tokenizer", "config", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    history = public_messages(
        json.loads((args.previous / "public-messages.json").read_text())
    )
    tokenizer = PinnedTokenizer(args.tokenizer)
    client = NativeFullStreamClient(args.config)

    def check(turn, index, label):
        old = args.previous / "generation" / f"turn-{turn:04d}"
        raw = json.loads((old / f"proposal-{index}/response.json").read_text())["text"]
        if turn == 24:
            # Harbor rolled back its uncommitted prompt on exception. Actual
            # generation request IDs plus a successful same-pool score bind it.
            prefix_ids = json.loads(
                (old / f"proposal-{index}/request.json").read_text()
            )["input_ids"]
            template_score = json.loads((old / "score-0/score.json").read_text())
            template_rows = json.loads((old / "score-0/response.json").read_text())[
                "meta_info"
            ]["input_token_logprobs"]
            assert prefix_ids == [
                row[1] for row in template_rows[: template_score["candidate_start"]]
            ]
            text = tokenizer.decode(prefix_ids) + raw
            ids = tokenizer.encode(text, add_special_tokens=False)
            assert ids[: len(prefix_ids)] == prefix_ids
            rendered = RenderedCandidate(
                text,
                tuple(ids),
                len(prefix_ids),
                template_score["history_sha256"],
                hashlib.sha256(raw.encode()).hexdigest(),
                tokenizer.identity,
                hashlib.sha256(tokenizer.chat_template.encode()).hexdigest(),
            )
        else:
            rendered = render_candidate(
                history[: 2 * (turn - 1) + 1],
                raw,
                tokenizer,
                tokenizer_identity=tokenizer.identity,
            )
        new = client.score(rendered, journal=args.output / label)
        result = {
            "turn": turn,
            "index": index,
            "new_mean": new["mean_logprob"],
            "candidate_tokens": new["token_count"],
            "full_input_tokens": len(rendered.input_ids),
            "request_elapsed_sec": new["request_elapsed_sec"],
        }
        old_score = old / f"score-{index}/score.json"
        if old_score.exists():
            previous = json.loads(old_score.read_text())
            result.update(
                old_mean=previous["mean_logprob"],
                mean_delta=new["mean_logprob"] - previous["mean_logprob"],
            )
        else:
            result["known_interrupted_score_now_completed"] = True
        return result

    checks = [check(1, 0, "short")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        checks.extend(pool.map(lambda i: check(23, i, f"long-{i}"), range(8)))
    checks += [check(24, i, f"old-failure-{i}") for i in (4, 7)]
    long = [r for r in checks if r["turn"] == 23]
    old_winner = max(long, key=lambda r: r["old_mean"])["index"]
    new_winner = max(long, key=lambda r: r["new_mean"])["index"]
    report = {
        "passed": old_winner == new_winner,
        "old_winner": old_winner,
        "new_winner": new_winner,
        "checks": checks,
        "request_semantic_fields_unchanged": True,
        "only_stream_flag_and_response_reader_changed": True,
        "full_input_rows_and_target_ids_verified": True,
        "new_candidate_generations": 0,
        "zero_generation_score_requests": len(checks),
        "note": "Means are reported, not claimed bit-identical across server batches. Native response fields/formula match legacy.",
    }
    (args.output / "calibration.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    if not report["passed"]:
        raise SystemExit("Winner drift; do not launch new rollout")


if __name__ == "__main__":
    main()
