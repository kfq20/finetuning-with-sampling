"""Controller-only Fleet adapter for native Terminus text, with no paid retries."""

import asyncio
from pathlib import Path
import time
from ..fleet import Fleet, FleetError


class FleetLLM:
    def __init__(self, private_config, journal_root, *, deadline, max_output_tokens):
        self.fleet = Fleet(Path(private_config))
        if self.fleet.config.get("inference_transport") != "sse":
            raise ValueError(
                "Selected deployment requires SSE; Jobs fallback forbidden"
            )
        self.model_name = self.fleet.config["model_id"]
        self.root = Path(journal_root)
        self.root.mkdir(mode=0o700, parents=True, exist_ok=False)
        self.deadline, self.max_output_tokens = deadline, max_output_tokens
        self.requests = 0

    def get_model_context_limit(self):
        return 1000000

    def get_model_output_limit(self):
        return self.max_output_tokens

    async def call(self, prompt, message_history=None, **kwargs):
        from harbor.llms.base import LLMResponse, UsageInfo

        if time.time() >= self.deadline:
            raise TimeoutError("StudyDeadline")
        self.requests += 1
        result = await asyncio.to_thread(
            self.fleet.chat,
            list(message_history or []) + [{"role": "user", "content": prompt}],
            max_tokens=self.max_output_tokens,
            journal=self.root / f"request-{self.requests:06d}",
            deadline=self.deadline,
        )
        choice = result["choices"][0]
        if choice["finish_reason"] != "stop" or choice["message"].get("tool_calls"):
            raise FleetError("IncompleteOrNonTerminusGeneration")
        content = choice["message"].get("content")
        if not isinstance(content, str) or not content:
            raise FleetError("EmptyTerminusGeneration")
        u = result.get("usage") or {}
        # Do not turn output-only LP into prompt/candidate scores.
        return LLMResponse(
            content=content,
            model_name=self.model_name,
            usage=UsageInfo(
                prompt_tokens=u.get("prompt_tokens", 0),
                completion_tokens=u.get("completion_tokens", 0),
                cache_tokens=(u.get("prompt_tokens_details") or {}).get(
                    "cached_tokens", 0
                ),
                cost_usd=0.0,
            ),
        )
