"""Eight current-block proposals; pure unreferenced likelihood selection.

Unselected actions never execute. No semantic/verifier/progress/repetition score.
A command batch is one block. All proposals share the identical public prefix.
"""

import asyncio
from pathlib import Path
import time

from ..collect import dump
from .episode import generation_history
from .native_stream import NativeStreamClient
from .protocol import action, digest, public_messages
from .scoring import render_candidate


def select(candidates):
    usable = [c for c in candidates if c["status"] == "scored"]
    if not usable:
        raise ValueError("No syntactically valid scored candidate")
    return max(usable, key=lambda c: c["score"]["mean_logprob"])


class BlockwiseLLM:
    def __init__(self, config, tokenizer, root, reference, *, proposals=8):
        if type(proposals) is not int or proposals < 1:
            raise ValueError("Positive candidate count required")
        self.client = NativeStreamClient(config)
        self.tokenizer, self.reference, self.proposals = tokenizer, reference, proposals
        self.root = Path(root)
        self.root.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.model_name = self.client.config["model_id"]
        self.decisions = []
        self.turn = 0

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
        self.turn += 1
        base = self.root / f"turn-{self.turn:04d}"
        base.mkdir(mode=0o700)

        async def propose(index):
            started = time.monotonic()
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
