"""Eight current-block proposals; pure unreferenced likelihood selection.

Unselected actions never execute. No semantic/verifier/progress/repetition score.
A command batch is one block. All proposals share the identical public prefix.
"""

import asyncio
import json
from pathlib import Path
import time

from ..collect import dump
from .episode import generation_history
from .suffix_score import ResilientFullStreamClient
from .protocol import action, digest, public_messages
from .scoring import render_candidate
from .scoring import analyze_native


def cached_proposal(source, wire, tokenizer):
    """Reuse only a complete response to this exact referenced token prefix."""
    request = json.loads((source / "request.json").read_text())
    result = json.loads((source / "response.json").read_text())
    ids = tokenizer.encode(wire, add_special_tokens=False)
    if request.get("input_ids") != ids:
        raise ValueError("Cached candidate conditioning mismatch")
    meta = result["meta_info"]
    if (
        meta.get("prompt_tokens") != len(ids)
        or meta.get("finish_reason", {}).get("type") != "stop"
        or not result.get("text")
    ):
        raise ValueError("Cached candidate incomplete")
    return result


def select(candidates):
    usable = [c for c in candidates if c["status"] == "scored"]
    if not usable:
        raise ValueError("No syntactically valid scored candidate")
    return max(usable, key=lambda c: c["score"]["mean_logprob"])


class BlockwiseLLM:
    def __init__(
        self, config, tokenizer, root, reference, *, proposals=8, cached_turn=None
    ):
        if type(proposals) is not int or proposals < 1:
            raise ValueError("Positive candidate count required")
        self.client = ResilientFullStreamClient(config)
        self.tokenizer, self.reference, self.proposals = tokenizer, reference, proposals
        self.root = Path(root)
        self.root.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.model_name = self.client.config["model_id"]
        self.decisions = []
        self.cached_turn = Path(cached_turn) if cached_turn else None
        self.turn = int(self.cached_turn.name.split("-")[-1]) - 1 if cached_turn else 0

    def get_model_context_limit(self):
        return 1000000

    def get_model_output_limit(self):
        return 128000

    async def call(self, prompt, message_history=None, **kwargs):
        from harbor.llms.base import LLMResponse, UsageInfo

        public = public_messages(
            list(message_history or []) + [{"role": "user", "content": prompt}]
        )
        cached = getattr(self, "cached_turn", None)
        if cached and json.loads((cached / "public-prefix.json").read_text()) != public:
            raise ValueError("Cached public prefix mismatch")
        wire = self.tokenizer.apply_chat_template(
            generation_history(public, self.reference),
            tokenize=False,
            add_generation_prompt=True,
        )
        self.turn += 1
        base = self.root / f"turn-{self.turn:04d}"
        base.mkdir(mode=0o700)
        dump(base / "public-prefix.json", public)

        async def propose(index):
            started = time.monotonic()
            if cached:
                source = cached / f"proposal-{index}"
                result = cached_proposal(source, wire, self.tokenizer)
                dump(
                    base / f"reused-proposal-{index}.json",
                    {
                        "source": str(source),
                        "response_sha256": digest(result),
                        "new_generation_requests": 0,
                    },
                )
            else:
                result = await asyncio.to_thread(
                    self.client.generate,
                    wire,
                    self.tokenizer,
                    journal=base / f"proposal-{index}",
                )
            raw = result["text"]
            item = {
                "index": index,
                "raw": raw,
                "generation_usage": {
                    k: result["meta_info"].get(k)
                    for k in (
                        "prompt_tokens",
                        "completion_tokens",
                        "cached_tokens",
                        "id",
                    )
                },
            }
            try:
                action(raw)
            except (ValueError, TypeError):
                item["status"] = "invalid_native_action"
                return item
            rendered = render_candidate(
                public, raw, self.tokenizer, tokenizer_identity=self.tokenizer.identity
            )
            old_score = cached / f"score-{index}" if cached else None
            if old_score and (old_score / "response.json").exists():
                req = json.loads((old_score / "request.json").read_text())
                if (
                    req.get("text") != rendered.text
                    or req.get("logprob_start_len") != 0
                ):
                    raise ValueError("Cached score conditioning mismatch")
                score = analyze_native(
                    json.loads((old_score / "response.json").read_text()), rendered
                )
                dump(base / f"reused-score-{index}.json", {"source": str(old_score)})
            else:
                score = await asyncio.to_thread(
                    self.client.score, rendered, journal=base / f"score-{index}"
                )
            item.update(
                status="scored",
                score=score,
                elapsed_sec=time.monotonic() - started,
                scoring_input_tokens=len(rendered.input_ids),
            )
            return item

        # First actual candidate validates native SSE before the remaining fanout.
        # Its result is reused as candidate0, never a discarded compatibility probe.
        first = [await propose(0)] if self.turn == 1 else []
        rest = await asyncio.gather(
            *(propose(i) for i in range(len(first), self.proposals)),
            return_exceptions=True,
        )
        if any(isinstance(r, BaseException) for r in rest):
            dump(
                base / "turn-error.json",
                {
                    "automatic_retry": False,
                    "errors": [
                        {"index": i + len(first), "error_type": type(r).__name__}
                        for i, r in enumerate(rest)
                        if isinstance(r, BaseException)
                    ],
                },
            )
            raise RuntimeError("Incomplete candidate pool; no action executed")
        candidates = first + rest
        best = select(candidates)
        record = {
            "algorithm": "latest-block-logprob-8.v1",
            "public_history_sha256": digest(public),
            "selected_index": best["index"],
            "candidates": candidates,
            "candidate_count": len(candidates),
            "selection": "mean unreferenced assistant-token logprob only",
            "intermediate_verifier_calls": 0,
            "environment_rollbacks": 0,
            "selected_commands_sha256": digest(action(best["raw"])["commands"]),
        }
        dump(base / "decision.json", record)
        self.cached_turn = None
        self.decisions.append(record)
        usage = [c["generation_usage"] for c in candidates]
        return LLMResponse(
            content=best["raw"],
            model_name=self.model_name,
            usage=UsageInfo(
                prompt_tokens=sum(x["prompt_tokens"] for x in usage)
                + sum(c.get("scoring_input_tokens", 0) for c in candidates),
                completion_tokens=sum(x["completion_tokens"] for x in usage),
                cache_tokens=sum(x.get("cached_tokens") or 0 for x in usage),
                cost_usd=0.0,
            ),
        )


def main():
    """Repair a failed block's scores without executing tools or generating actions."""
    import argparse
    from .tokenizer import PinnedTokenizer

    p = argparse.ArgumentParser(__doc__)
    for key in ("config", "tokenizer", "source-turn", "teacher", "output"):
        p.add_argument("--" + key, type=Path, required=True)
    a = p.parse_args()
    prefix = json.loads((a.source_turn / "public-prefix.json").read_text())
    reference = json.dumps(
        public_messages(json.loads(a.teacher.read_text())), ensure_ascii=False
    )
    backend = BlockwiseLLM(
        a.config,
        PinnedTokenizer(a.tokenizer),
        a.output,
        reference,
        cached_turn=a.source_turn,
    )
    asyncio.run(backend.call(prefix[-1]["content"], message_history=prefix[:-1]))
    dump(
        a.output / "recovery-receipt.json",
        {
            "source_turn": str(a.source_turn),
            "new_generation_requests": 0,
            "tools_executed": 0,
            "selected_index": backend.decisions[-1]["selected_index"],
            "scoring_recovered_only": True,
        },
    )


if __name__ == "__main__":
    main()
