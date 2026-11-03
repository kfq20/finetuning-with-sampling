"""Real zero-generation scorer checks over cached old proposals, no solving."""

import argparse
import concurrent.futures
import hashlib
import json
from pathlib import Path

from append_rewrite.terminus.protocol import public_messages
from append_rewrite.terminus.scoring import render_candidate
from append_rewrite.terminus.suffix_score import NativeSuffixStreamClient
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
    client = NativeSuffixStreamClient(args.config)

    def check(turn, index, label):
        old = args.previous / "generation" / f"turn-{turn:04d}"
        raw = json.loads((old / f"proposal-{index}/response.json").read_text())["text"]
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
            "new_response_bytes": (args.output / label / "response.json")
            .stat()
            .st_size,
            "request_elapsed_sec": new["request_elapsed_sec"],
        }
        old_response = old / f"score-{index}/response.json"
        if old_response.exists():
            old_value = json.loads(old_response.read_text())
            old_score = json.loads((old / f"score-{index}/score.json").read_text())
            old_rows = old_value["meta_info"]["input_token_logprobs"]
            assert [r[1] for r in old_rows] == list(rendered.input_ids)
            new_rows = json.loads((args.output / label / "response.json").read_text())[
                "meta_info"
            ]["input_token_logprobs"][1:]
            old_rows = old_rows[rendered.candidate_start :]
            assert len(old_rows) == len(new_rows) == new["token_count"]
            differences = [abs(a[0] - b[0]) for a, b in zip(old_rows, new_rows)]
            result.update(
                old_mean=old_score["mean_logprob"],
                mean_abs_token_diff=sum(differences) / len(differences),
                max_abs_token_diff=max(differences),
                old_response_bytes=old_response.stat().st_size,
            )
            result["probability_equivalence_passed"] = (
                abs(result["new_mean"] - result["old_mean"]) <= 0.001
                and result["mean_abs_token_diff"] <= 0.001
                and result["max_abs_token_diff"] <= 0.01
            )
        else:
            result["known_interrupted_score_now_completed"] = True
        return result

    checks = [check(1, 0, "short")]
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        checks.extend(pool.map(lambda i: check(23, i, f"long-pool-{i}"), range(8)))
    checks += [check(24, i, f"previously-failed-{i}") for i in (4, 7)]
    long = [r for r in checks if r["turn"] == 23]
    old_winner = max(long, key=lambda r: r["old_mean"])["index"]
    new_winner = max(long, key=lambda r: r["new_mean"])["index"]
    passed = old_winner == new_winner and all(
        c.get("probability_equivalence_passed", True) for c in checks
    )
    report = {
        "passed": passed,
        "old_winner": old_winner,
        "new_winner": new_winner,
        "checks": checks,
        "new_candidate_generations": 0,
        "zero_generation_score_requests": len(checks),
        "same_full_conditioning": True,
        "first_boundary_token_not_scored": True,
        "tolerances": {
            "mean_logprob_abs": 0.001,
            "mean_abs_token_lp": 0.001,
            "max_abs_token_lp": 0.01,
        },
        "calibration_source_sha256": hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest(),
        "scorer_source_sha256": hashlib.sha256(
            (
                Path(__file__).parents[2]
                / "src/append_rewrite/terminus/suffix_score.py"
            ).read_bytes()
        ).hexdigest(),
    }
    (args.output / "calibration.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    if not passed:
        raise SystemExit("Calibration failed; do not launch rollout")


if __name__ == "__main__":
    main()
