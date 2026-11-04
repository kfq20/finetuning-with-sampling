"""Streamed zero-generation scoring: full conditioning, candidate-only LP range.

One boundary token is returned to protect the first candidate position. No
prefix logprob fabrication, no score semantics change, no retry/fallback.
"""

import hashlib
import json
from pathlib import Path
import time
from urllib.request import Request, urlopen
from contextlib import contextmanager
import fcntl
import os
import random

from .native_stream import NativeStreamClient, consume
from .protocol import digest
from .scoring import analyze_native
from .http_evidence import failure, headers


@contextmanager
def file_slot(root, capacity):
    """Persistent process-owned slots; process exit releases the lock."""
    if not root:
        yield
        return
    root = Path(root)
    root.mkdir(parents=True, mode=0o700, exist_ok=True)
    while True:
        reserved = 0
        grandfathered = root / "grandfathered.json"
        if grandfathered.exists():
            for p in json.loads(grandfathered.read_text()):
                try:
                    stat = (
                        Path(f"/proc/{p['pid']}/stat")
                        .read_text()
                        .split(") ")[1]
                        .split()
                    )
                    reserved += stat[0] != "Z" and stat[19] == p["start_ticks"]
                except FileNotFoundError:
                    pass
        for i in range(reserved, capacity):
            f = (root / f"score-{i}.lock").open("a+")
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                f.close()
                continue
            try:
                yield
            finally:
                f.close()
            return
        time.sleep(0.1)


def score_slot():
    """Explicit per-run prefill capacity; legacy workers retain their two slots."""
    capacity = int(os.environ.get("APPEND_REWRITE_SCORE_CAPACITY", "2"))
    if capacity < 1:
        raise ValueError("Positive score-prefill capacity required")
    return file_slot(os.environ.get("APPEND_REWRITE_SCORE_POOL"), capacity)


class NativeSuffixStreamClient(NativeStreamClient):
    def score(self, rendered, *, journal, timeout=120, full_input=False):
        rendered.validate()
        journal = Path(journal)
        journal.mkdir(parents=True, mode=0o700, exist_ok=False)
        offset = 0 if full_input else rendered.candidate_start - 1
        body = {
            ("text" if full_input else "input_ids"): rendered.text
            if full_input
            else list(rendered.input_ids),
            "sampling_params": {"max_new_tokens": 0, "temperature": 0},
            "return_logprob": True,
            "logprob_start_len": offset,
            "return_text_in_logprobs": full_input,
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
            headers=self.request_headers(),
        )
        started = time.monotonic()
        try:
            with urlopen(request, timeout=timeout) as reply:
                (journal / "http.json").write_text(
                    json.dumps(
                        {
                            "status": reply.status,
                            "headers": headers(reply),
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
                full_input_ids_supplied=not full_input,
                automatic_retry=False,
                request_elapsed_sec=time.monotonic() - started,
            )
            (journal / "score.json").write_text(json.dumps(result, indent=2))
            return result
        except BaseException as exc:
            failure(exc, journal, started)
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


class NativeFullStreamClient(NativeSuffixStreamClient):
    """Same full-input score request/analysis as legacy, only streamed transport."""

    def score(self, rendered, *, journal, timeout=120):
        return super().score(
            rendered, journal=journal, timeout=timeout, full_input=True
        )


class ResilientFullStreamClient(NativeFullStreamClient):
    """Retry only incomplete zero-generation scores, never action generation.

    Every POST has its own retained journal. A validated result is reused once;
    auth/policy, quota and validation errors never trigger transport retries.
    """

    def score(self, rendered, *, journal, timeout=120):
        import shutil
        from urllib.error import HTTPError, URLError
        from http.client import IncompleteRead

        journal = Path(journal)
        journal.mkdir(parents=True, mode=0o700, exist_ok=False)
        for attempt in range(1, 6):
            dest = journal / f"attempt-{attempt}"
            try:
                with score_slot():
                    result = super().score(rendered, journal=dest, timeout=timeout)
            except (
                HTTPError,
                URLError,
                IncompleteRead,
                TimeoutError,
                ConnectionError,
            ) as exc:
                retryable = not isinstance(exc, HTTPError) or exc.code in (
                    499,
                    500,
                    502,
                    503,
                    504,
                )
                with (journal / "error-events.jsonl").open("a") as events:
                    events.write(
                        json.dumps(
                            {
                                "attempt": attempt,
                                "error_type": type(exc).__name__,
                                "http_status": getattr(exc, "code", None),
                                "retryable_zero_generation_only": retryable,
                            }
                        )
                        + "\n"
                    )
                if not retryable or attempt == 5:
                    (journal / "error.json").write_text(
                        json.dumps(
                            {
                                "error_type": type(exc).__name__,
                                "http_status": getattr(exc, "code", None),
                                "attempts": attempt,
                                "generation_retried": False,
                            }
                        )
                    )
                    raise
                time.sleep(min(60, 3**attempt) + random.uniform(0, 1))
            else:
                for name in (
                    "request.json",
                    "intent.json",
                    "response.json",
                    "transport.json",
                    "http.json",
                ):
                    if (dest / name).exists():
                        shutil.copy2(dest / name, journal / name)
                result["score_transport_attempts"] = attempt
                result["generation_retried"] = False
                (journal / "score.json").write_text(json.dumps(result, indent=2))
                return result
