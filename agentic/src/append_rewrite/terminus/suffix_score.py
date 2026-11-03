"""Streamed zero-generation scoring: full conditioning, candidate-only LP range.

One boundary token is returned to protect the first candidate position. No
prefix logprob fabrication, no score semantics change, no retry/fallback.
"""

import hashlib
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen

from .native_stream import NativeStreamClient, consume
from .protocol import digest
from .scoring import analyze_native


class NativeSuffixStreamClient(NativeStreamClient):
    def score(self, rendered, *, journal, timeout=120):
        rendered.validate()
        journal = Path(journal)
        journal.mkdir(parents=True, mode=0o700, exist_ok=False)
        offset = rendered.candidate_start - 1
        body = {
            "input_ids": list(rendered.input_ids),
            "sampling_params": {"max_new_tokens": 0, "temperature": 0},
            "return_logprob": True,
            "logprob_start_len": offset,
            "return_text_in_logprobs": False,
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
                    "candidate_start": rendered.candidate_start,
                    "returned_logprob_start": offset,
                    "full_conditioning_tokens": len(rendered.input_ids),
                }
            )
        )
        request = Request(
            self.endpoint,
            data=json.dumps(body).encode(),
            headers={
                "x-api-key": self.config["api_key"],
                "Content-Type": "application/json",
            },
        )
        started = time.monotonic()
        try:
            with urlopen(request, timeout=timeout) as reply:
                allowed = {
                    "content-type",
                    "content-length",
                    "transfer-encoding",
                    "x-request-id",
                    "x-correlation-id",
                    "traceparent",
                    "date",
                }
                headers = {
                    k.lower(): v
                    for k, v in reply.headers.items()
                    if k.lower() in allowed
                }
                (journal / "http.json").write_text(
                    json.dumps(
                        {
                            "status": reply.status,
                            "headers": headers,
                            "headers_elapsed_sec": time.monotonic() - started,
                        }
                    )
                )
                response = consume(
                    reply, journal, len(rendered.input_ids), scoring=True
                )
            raw = json.dumps(response, ensure_ascii=False).encode()
            (journal / "response.json").write_bytes(raw)
            result = analyze_native(response, rendered, logprob_start=offset)
            result.update(
                model_id=self.config["model_id"],
                response_sha256=hashlib.sha256(raw).hexdigest(),
                full_input_ids_supplied=True,
                automatic_retry=False,
                request_elapsed_sec=time.monotonic() - started,
            )
            (journal / "score.json").write_text(json.dumps(result, indent=2))
            return result
        except BaseException as exc:
            partial = getattr(exc, "partial", b"")
            if partial:
                (journal / "partial-response.bin").write_bytes(partial[:65536])
            (journal / "error.json").write_text(
                json.dumps(
                    {
                        "error_type": type(exc).__name__,
                        "automatic_retry": False,
                        "elapsed_sec": time.monotonic() - started,
                        "http_status": getattr(exc, "code", None),
                        "partial_bytes": len(partial),
                        "partial_saved_bytes": min(len(partial), 65536),
                    }
                )
            )
            raise
