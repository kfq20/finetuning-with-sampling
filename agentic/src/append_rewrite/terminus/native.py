"""One native /generate path for generation AND candidate scoring.

The same local renderer supplies both paths. Input IDs returned by native engine
are checked against the local tokenizer on every request; no OpenAI server-side
chat rendering participates in this study.
"""

import asyncio
from pathlib import Path
import json
import time
from urllib.request import Request, urlopen
from .protocol import public_messages, action, digest
from .scoring import NativeInputScorer, render_candidate


class NativeClient(NativeInputScorer):
    def generate(self, prompt, tokenizer, *, journal, max_tokens=128000, timeout=900):
        journal = Path(journal)
        journal.mkdir(parents=True, mode=0o700, exist_ok=False)
        body = {
            "text": prompt,
            "sampling_params": {"max_new_tokens": max_tokens, "temperature": 0.6},
            "return_logprob": True,
            "logprob_start_len": 0,
            "return_text_in_logprobs": True,
            "stream": False,
        }
        (journal / "intent.json").write_text(
            json.dumps({"body_sha256": digest(body), "automatic_retry": False})
        )
        req = Request(
            self.endpoint,
            data=json.dumps(body).encode(),
            headers={
                "x-api-key": self.config["api_key"],
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(req, timeout=timeout) as response:
                raw = response.read()
            (journal / "response.json").write_bytes(raw)
            v = json.loads(raw)
            m = v["meta_info"]
            ids = tokenizer.encode(prompt, add_special_tokens=False)
            rows = m.get("input_token_logprobs") or []
            if m.get("prompt_tokens") != len(ids) or [x[1] for x in rows] != ids:
                raise ValueError("Native generation tokenizer mismatch")
            finish = m.get("finish_reason")
            if not isinstance(finish, dict) or finish.get("type") != "stop":
                raise ValueError("Incomplete native generation")
            if not isinstance(v.get("text"), str) or not v["text"]:
                raise ValueError("Empty native generation")
            return v
        except Exception as exc:
            (journal / "error.json").write_text(
                json.dumps({"error_type": type(exc).__name__, "automatic_retry": False})
            )
            raise


class NativeRewriteLLM:
    """Greedy blockwise MVP, not full MH/MCMC or per-candidate sandbox validation.

    Propose two referenced actions; score unreferenced raw actions; execute ONLY
    the chosen action via the native Harbor loop. Final environment verifier is
    required before SFT admission. Every following proposal sees actual feedback.
    """

    def __init__(self, config, tokenizer, journal_root, reference, *, proposals=2):
        if type(proposals) is not int or proposals < 1:
            raise ValueError("Positive proposal count required")
        self.client = NativeClient(config)
        self.tokenizer, self.reference = tokenizer, reference
        self.root = Path(journal_root)
        self.root.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.proposals, self.turn = proposals, 0
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
        private = public[:-1] + [
            {
                "role": "user",
                "content": prompt
                + "\n\n<expert_reference>\n"
                + self.reference
                + "\n</expert_reference>\nReference only. Use actual terminal feedback and do not claim observations you did not obtain.",
            }
        ]
        wire = self.tokenizer.apply_chat_template(
            private, tokenize=False, add_generation_prompt=True
        )
        self.turn += 1
        base = self.root / f"turn-{self.turn:04d}"
        base.mkdir(mode=0o700)
        candidates = []
        for index in range(self.proposals):
            start = time.monotonic()
            result = await asyncio.to_thread(
                self.client.generate,
                wire,
                self.tokenizer,
                journal=base / f"proposal-{index}",
            )
            raw = result["text"]
            try:
                action(raw)
            except (ValueError, TypeError):
                candidates.append(
                    {"index": index, "status": "invalid_action", "raw": raw}
                )
                continue
            rendered = render_candidate(
                public, raw, self.tokenizer, tokenizer_identity=self.tokenizer.identity
            )
            score = await asyncio.to_thread(
                self.client.score, rendered, journal=base / f"score-{index}"
            )
            score["generation_template_alignment_verified"] = True
            candidates.append(
                {
                    "index": index,
                    "status": "scored",
                    "raw": raw,
                    "score": score,
                    "generation_usage": result["meta_info"],
                    "elapsed_sec": time.monotonic() - start,
                }
            )
        usable = [c for c in candidates if c["status"] == "scored"]
        if not usable:
            raise ValueError("No admissible candidate; no automatic regeneration")
        best = max(usable, key=lambda c: c["score"]["mean_logprob"])
        record = {
            "algorithm": "greedy_native_block_rewrite_mvp",
            "public_history_sha256": digest(public),
            "selected_index": best["index"],
            "candidates": candidates,
            "training_admitted": False,
        }
        (base / "decision.json").write_text(json.dumps(record, indent=2))
        self.decisions.append(record)
        all_usage = [c["generation_usage"] for c in usable]
        return LLMResponse(
            content=best["raw"],
            model_name=self.model_name,
            usage=UsageInfo(
                prompt_tokens=sum(x.get("prompt_tokens", 0) for x in all_usage),
                completion_tokens=sum(x.get("completion_tokens", 0) for x in all_usage),
                cache_tokens=0,
                cost_usd=0.0,
            ),
        )
