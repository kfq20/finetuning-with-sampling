"""Approved DeepSeek teacher via Anthropic transport, native Terminus actions.

Claude Code is not involved. Private reasoning stays in private wire evidence;
only text action JSON enters native Harbor chat. No retry, fallback or partial
response execution. Credentials remain on the controller.
"""

import asyncio
import hashlib
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen
from .http_evidence import failure, headers


class DeepSeekTeacher:
    def __init__(self, config, journals):
        p = Path(config)
        if p.stat().st_mode & 0o077:
            raise PermissionError("Private teacher config required")
        self.config = json.loads(p.read_text())
        c = self.config
        if (
            c["base_url"] != "https://mintcn.macaron.xin"
            or c["model_id"] != "deepseek-flash"
        ):
            raise ValueError("Teacher route not approved")
        if hashlib.sha256(c["api_key"].encode()).hexdigest() != c["credential_sha256"]:
            raise ValueError("Teacher credential drift")
        if (
            c["policy_sha256"]
            != "3ad60475c169516733eb736d97098a0577858b503b26e65673b56af035d87f4e"
        ):
            raise ValueError("Teacher policy drift")
        self.root = Path(journals)
        self.root.mkdir(parents=True, mode=0o700, exist_ok=False)
        self.model_name, self.n = c["model_id"], 0

    def get_model_context_limit(self):
        return 1000000

    def get_model_output_limit(self):
        return 128000

    def request(self, messages, journal):
        journal.mkdir(mode=0o700)
        body = {
            "model": self.model_name,
            "messages": messages,
            "max_tokens": 128000,
            "thinking": {"type": "adaptive"},
            "output_config": {"effort": "max"},
            "stream": True,
        }
        (journal / "intent.json").write_text(
            json.dumps(
                {
                    "body_sha256": hashlib.sha256(
                        json.dumps(body).encode()
                    ).hexdigest(),
                    "model": self.model_name,
                    "automatic_retry": False,
                }
            )
        )
        req = Request(
            self.config["base_url"] + "/v1/messages",
            data=json.dumps(body).encode(),
            headers={
                "Authorization": "Bearer " + self.config["api_key"],
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        )
        text = []
        usage = {}
        done = False
        stop = None
        model = None
        rid = None
        started = time.monotonic()
        try:
            with (
                urlopen(req, timeout=900) as response,
                (journal / "wire.jsonl").open("w") as log,
            ):
                (journal / "http.json").write_text(
                    json.dumps(
                        {
                            "status": response.status,
                            "headers": headers(response),
                            "headers_elapsed_sec": time.monotonic() - started,
                        }
                    )
                )
                for line in response:
                    if not line.startswith(b"data:"):
                        continue
                    payload = line[5:].strip()
                    if not payload or payload == b"[DONE]":
                        continue
                    event = json.loads(payload)
                    log.write(json.dumps(event) + "\n")
                    log.flush()
                    kind = event.get("type")
                    if kind == "error":
                        raise RuntimeError("TeacherUpstreamStreamError")
                    if kind == "message_start":
                        m = event["message"]
                        model = m.get("model")
                        rid = m.get("id")
                        usage.update(m.get("usage") or {})
                    elif (
                        kind == "content_block_delta"
                        and event.get("delta", {}).get("type") == "text_delta"
                    ):
                        text.append(event["delta"]["text"])
                    elif kind == "message_delta":
                        stop = event.get("delta", {}).get("stop_reason") or stop
                        usage.update(event.get("usage") or {})
                    elif kind == "message_stop":
                        done = True
                        break
            if not done or stop != "end_turn" or not text:
                raise RuntimeError("TeacherIncompleteResponse")
            if model != self.model_name:
                raise ValueError("TeacherModelIdentityMismatch")
            result = {
                "content": "".join(text),
                "usage": usage,
                "request_id": rid,
                "model": model,
                "stop_reason": stop,
            }
            (journal / "observable-response.json").write_text(
                json.dumps(result, indent=2)
            )
            return result
        except Exception as exc:
            failure(exc, journal, started)
            (journal / "error.json").write_text(
                json.dumps({"error_type": type(exc).__name__, "automatic_retry": False})
            )
            raise

    async def call(self, prompt, message_history=None, **kwargs):
        from harbor.llms.base import LLMResponse, UsageInfo

        self.n += 1
        start = time.monotonic()
        r = await asyncio.to_thread(
            self.request,
            list(message_history or []) + [{"role": "user", "content": prompt}],
            self.root / f"request-{self.n:04d}",
        )
        u = r["usage"]
        (self.root / f"request-{self.n:04d}" / "timing.json").write_text(
            json.dumps({"elapsed_sec": time.monotonic() - start})
        )
        return LLMResponse(
            content=r["content"],
            model_name=r["model"],
            usage=UsageInfo(
                prompt_tokens=u.get("input_tokens", 0),
                completion_tokens=u.get("output_tokens", 0),
                cache_tokens=u.get("cache_read_input_tokens", 0),
                cost_usd=0.0,
            ),
        )
