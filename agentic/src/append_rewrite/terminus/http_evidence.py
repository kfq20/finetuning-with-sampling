"""Private transport evidence, with no authentication headers in receipts."""

import json
import time
from urllib.error import HTTPError


def headers(reply):
    allowed = {
        "content-type",
        "content-length",
        "date",
        "server",
        "via",
        "x-request-id",
        "x-correlation-id",
        "traceparent",
        "x-fleet-record-id",
        "retry-after",
    }
    return {k.lower(): v for k, v in reply.headers.items() if k.lower() in allowed}


def failure(exc, journal, started):
    record = {
        "error_type": type(exc).__name__,
        "http_status": getattr(exc, "code", None),
        "elapsed_sec": time.monotonic() - started,
    }
    if isinstance(exc, HTTPError):
        record["headers"] = headers(exc)
        # Saved only in the private journal; never rendered in user summaries.
        try:
            body = exc.read(16384)
        except Exception as read_error:
            body = b""
            record["error_body_read_error"] = type(read_error).__name__
        (journal / "http-error-body.bin").write_bytes(body)
        record["saved_error_body_bytes"] = len(body)
    (journal / "http-error.json").write_text(json.dumps(record, indent=2))
    return record
