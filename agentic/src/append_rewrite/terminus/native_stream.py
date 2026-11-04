"""Native /generate SSE with exact request input IDs and strict stop admission.

Generation needs no prompt logprobs: input IDs are supplied explicitly. Forced
candidate scoring remains the existing zero-generation path with returned-ID
validation. No fallback, hidden retries or partial response execution.
"""

import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

from .native import NativeClient
from .protocol import digest
from .http_evidence import failure, headers


def consume(response, journal, input_count, *, scoring=False):
    text, metadata, request_id = "", {}, None
    started = time.monotonic()
    first = None
    events = 0
    data = []
    journal = Path(journal)
    with (journal / "wire.jsonl").open("x") as wire:
        for line in response:
            if first is None:
                first = time.monotonic() - started
            if isinstance(line, bytes):
                line = line.decode("utf-8")
            if line.startswith(":"):
                continue
            if line.startswith("data:"):
                data.append(line[5:].strip())
                continue
            if line.strip():
                if line.startswith("event:") or line.startswith("id:"):
                    continue
                raise ValueError("Unexpected native SSE framing")
            if not data:
                continue
            raw = "\n".join(data)
            data = []
            if raw == "[DONE]":
                raise ValueError("Native stream ended before normal stop")
            value = json.loads(raw)
            wire.write(json.dumps(value, ensure_ascii=False) + "\n")
            wire.flush()
            events += 1
            if "error" in value or value.get("type") == "error":
                raise RuntimeError("Native upstream stream error")
            current, meta = value.get("text"), value.get("meta_info")
            if not isinstance(current, str) or not isinstance(meta, dict):
                raise ValueError("Missing native text/metadata")
            if not current.startswith(text):
                raise ValueError("Native cumulative text changed")
            if meta.get("prompt_tokens") != input_count:
                raise ValueError("Native generation input length drift")
            if request_id is not None and meta.get("id") != request_id:
                raise ValueError("Native stream request identity drift")
            request_id = meta.get("id")
            if not request_id:
                raise ValueError("Missing native request identity")
            text, metadata = current, meta
            finish = meta.get("finish_reason")
            if finish is not None:
                if not isinstance(finish, dict):
                    raise ValueError("Invalid native termination metadata")
                if scoring:
                    valid_finish = finish.get("type") == "stop" or (
                        finish.get("type") == "length" and finish.get("length") == 0
                    )
                    if not valid_finish or meta.get("completion_tokens") != 0 or text:
                        raise ValueError("Unexpected generation or incomplete scoring")
                elif finish.get("type") != "stop" or not text:
                    raise ValueError("Incomplete native generation")
                # Stop at explicit model termination, never wait for HTTP EOF.
                (journal / "transport.json").write_text(
                    json.dumps(
                        {
                            "request_id": request_id,
                            "complete_stop": True,
                            "events": events,
                            "first_byte_sec": first,
                            "elapsed_sec": time.monotonic() - started,
                        }
                    )
                )
                return {"text": text, "meta_info": metadata}
    raise ValueError("Native stream EOF without normal stop")


class NativeStreamClient(NativeClient):
    def generate(self, prompt, tokenizer, *, journal, max_tokens=128000, timeout=900):
        journal = Path(journal)
        journal.mkdir(parents=True, mode=0o700, exist_ok=False)
        ids = tokenizer.encode(prompt, add_special_tokens=False)
        context_limit = self.config.get("context_limit", 262144)
        max_tokens = min(max_tokens, context_limit - len(ids))
        if max_tokens <= 0:
            raise ValueError("Generation input exceeds serving context before POST")
        body = {
            "input_ids": ids,
            "sampling_params": {"max_new_tokens": max_tokens, "temperature": 0.6},
            "return_logprob": False,
            "stream": True,
        }
        (journal / "request.json").write_text(json.dumps(body))
        (journal / "intent.json").write_text(
            json.dumps(
                {
                    "endpoint": self.endpoint,
                    "model_id": self.config["model_id"],
                    "body_sha256": digest(body),
                    "automatic_retry": False,
                    "input_ids_supplied_explicitly": True,
                    "serving_context_limit": context_limit,
                    "effective_max_new_tokens": max_tokens,
                }
            )
        )
        request = Request(
            self.endpoint,
            data=json.dumps(body).encode(),
            headers=self.request_headers(),
        )
        started = time.monotonic()
        try:
            with urlopen(request, timeout=timeout) as response:
                (journal / "http.json").write_text(
                    json.dumps(
                        {
                            "status": response.status,
                            "headers": headers(response),
                            "headers_elapsed_sec": time.monotonic() - started,
                        }
                    )
                )
                result = consume(response, journal, len(ids))
            (journal / "response.json").write_text(
                json.dumps(result, ensure_ascii=False)
            )
            return result
        except BaseException as exc:
            failure(exc, journal, started)
            (journal / "error.json").write_text(
                json.dumps(
                    {
                        "error_type": type(exc).__name__,
                        "automatic_retry": False,
                        "partial_bytes": len(getattr(exc, "partial", b"")),
                    }
                )
            )
            raise
