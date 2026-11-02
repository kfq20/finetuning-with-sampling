"""Scoped Anthropic transport relay. Run only in a trusted, non-solver sandbox.

Preserves native CLI payloads with optional explicitly configured buffered retry.
Early SSE headers/heartbeats protect prefill. No fallback; credentials stay here.
"""

from __future__ import annotations
import argparse
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import http.client
import json
from pathlib import Path
import secrets
import threading
import time
from urllib.parse import urlsplit


def sse_event(value):
    return (
        "event: " + value["type"] + "\ndata: " + json.dumps(value) + "\n\n"
    ).encode()


def validate_request(path, payload, model):
    if path.split("?")[0] not in ("/v1/messages", "/v1/messages/count_tokens"):
        raise ValueError("UnsupportedPath")
    if payload.get("model") != model:
        raise ValueError("ModelIdentityMismatch")
    if path.split("?")[0] == "/v1/messages" and payload.get("stream") is not True:
        raise ValueError("NativeStreamingRequired")


class StreamFailure(RuntimeError):
    def __init__(self, code, retryable=True, raw_error=None, status=None):
        super().__init__(code)
        self.retryable, self.raw_error, self.status = retryable, raw_error, status


def validated_stream(response, model):
    """Buffer one complete Anthropic message, with no downstream delivery.

    Reject malformed tool frames rather than guessing or repairing their meaning.
    Private thinking is opaque and is never included in diagnostics.
    """
    pending = b""
    frame = b""
    output = bytearray()
    blocks = {}
    tool_ids = set()
    begun = stopped = False
    usage = {}
    stop_reason = None
    while True:
        chunk = response.read1(8192)
        if not chunk:
            break
        pending += chunk
        while b"\n" in pending:
            line, pending = pending.split(b"\n", 1)
            line = line.rstrip(b"\r")
            frame += line + b"\n"
            if line.startswith(b"data:"):
                try:
                    data = json.loads(line[5:].strip())
                except ValueError as exc:
                    raise StreamFailure("MalformedSSEJSON") from exc
                kind = data.get("type")
                if kind == "error":
                    error_type = data.get("error", {}).get("type")
                    raise StreamFailure(
                        "ProviderSSEError",
                        retryable=error_type in ("api_error", "overloaded_error"),
                        raw_error=data,
                    )
                if stopped:
                    raise StreamFailure("EventsAfterMessageStop")
                if kind == "message_start":
                    if begun:
                        raise StreamFailure("DuplicateMessageStart")
                    msg = data.get("message", {})
                    if msg.get("model") != model:
                        raise StreamFailure("ResponseModelMismatch", retryable=False)
                    begun = True
                    usage.update(msg.get("usage", {}))
                elif kind == "content_block_start":
                    index = data["index"]
                    block = data["content_block"]
                    if not begun or index in blocks:
                        raise StreamFailure("DuplicateOrUnboundContentBlock")
                    if block["type"] == "tool_use":
                        if not block.get("id") or block["id"] in tool_ids:
                            raise StreamFailure("DuplicateToolUseID")
                        tool_ids.add(block["id"])
                    blocks[index] = {
                        "kind": block["type"],
                        "input": block.get("input", {}),
                        "partial": "",
                        "closed": False,
                    }
                elif kind == "content_block_delta":
                    block = blocks.get(data["index"])
                    if block is None or block["closed"]:
                        raise StreamFailure("UnboundContentDelta")
                    delta = data.get("delta", {})
                    if delta.get("type") == "input_json_delta":
                        if block["kind"] != "tool_use":
                            raise StreamFailure("ToolDeltaOnNonToolBlock")
                        block["partial"] += delta.get("partial_json", "")
                elif kind == "content_block_stop":
                    block = blocks.get(data["index"])
                    if block is None or block["closed"]:
                        raise StreamFailure("UnboundOrDuplicateBlockStop")
                    if block["kind"] == "tool_use":
                        try:
                            value = (
                                json.loads(block["partial"])
                                if block["partial"]
                                else block["input"]
                            )
                        except ValueError as exc:
                            raise StreamFailure("IncompleteToolInputJSON") from exc
                        if not isinstance(value, dict):
                            raise StreamFailure("NonObjectToolInput")
                    block["closed"] = True
                elif kind == "message_delta":
                    stop_reason = (
                        data.get("delta", {}).get("stop_reason") or stop_reason
                    )
                    usage.update(data.get("usage", {}))
                elif kind == "message_stop":
                    if (
                        not begun
                        or not stop_reason
                        or any(not b["closed"] for b in blocks.values())
                    ):
                        raise StreamFailure("IncompleteAnthropicMessage")
                    stopped = True
            if not line.strip():
                output.extend(frame)
                frame = b""
    if not stopped or pending.strip() or frame.strip():
        raise StreamFailure("IncompleteAnthropicStream")
    return bytes(output), {"usage": usage, "stop_reason": stop_reason}


def buffered_retry(open_response, model, max_attempts, on_event, sleep=time.sleep):
    """Retry only undelivered responses. The caller writes output exactly once."""
    if type(max_attempts) is not int or not 1 <= max_attempts <= 3:
        raise ValueError("Explicit upstream attempts must be 1..3")
    for attempt in range(1, max_attempts + 1):
        connection = None
        on_event("started", attempt, {})
        try:
            connection, response = open_response()
            if response.status != 200:
                raw = response.read(8192)
                raise StreamFailure(
                    "UpstreamHTTP_" + str(response.status),
                    retryable=response.status in (408, 502, 503, 504),
                    raw_error={"body": raw.decode(errors="replace")},
                    status=response.status,
                )
            payload, metadata = validated_stream(response, model)
            on_event("completed", attempt, metadata)
            return payload, metadata
        except (StreamFailure, OSError, http.client.HTTPException) as exc:
            retryable = not isinstance(exc, StreamFailure) or exc.retryable
            on_event(
                "error",
                attempt,
                {
                    "code": str(exc)
                    if isinstance(exc, StreamFailure)
                    else type(exc).__name__,
                    "status": getattr(exc, "status", None),
                    "retryable": retryable,
                    "raw_error": getattr(exc, "raw_error", None),
                    "usage_unknown": True,
                    "delivered_upstream_content_bytes": 0,
                },
            )
            if not retryable or attempt == max_attempts:
                raise
        finally:
            if connection is not None:
                connection.close()
        sleep(2**attempt)
    raise AssertionError("Unreachable")


def serve(config_file, root, port):
    if config_file.stat().st_mode & 0o077:
        raise PermissionError("Private gateway config required")
    config = json.loads(config_file.read_text())
    up = urlsplit(config["base_url"])
    if up.scheme != "https" or up.path not in ("", "/") or up.query or up.fragment:
        raise ValueError("Unapproved upstream URL")
    model = config["model_id"]
    if config.get("stream_mode", "passthrough") not in (
        "passthrough",
        "validated_buffer",
    ):
        raise ValueError("UnsupportedTransportPolicy")
    if config.get("stream_mode") == "validated_buffer" and config.get(
        "max_upstream_attempts", 1
    ) not in (1, 2, 3):
        raise ValueError("UnsupportedAttemptPolicy")
    root.mkdir(parents=True, exist_ok=True)
    lock = threading.Lock()

    def event(value):
        with lock:
            with (root / "requests.jsonl").open("a") as f:
                f.write(json.dumps({"time": time.time(), **value}) + "\n")

    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, *args):
            pass

        def do_POST(self):
            token = self.headers.get("x-api-key") or self.headers.get(
                "Authorization", ""
            ).removeprefix("Bearer ")
            if not secrets.compare_digest(
                hashlib.sha256(token.encode()).hexdigest(), config["client_sha256"]
            ):
                self.send_error(401)
                return
            if (root / "STOP.json").exists():
                self.send_error(503)
                return
            rid = secrets.token_hex(8)
            started = time.time()
            conn = None
            finished = threading.Event()
            write_lock = threading.Lock()
            early = False
            complete = False
            usage = {}
            stop_reason = None

            def write(data):
                with write_lock:
                    self.wfile.write(data)
                    self.wfile.flush()

            def heartbeat():
                while not finished.wait(5):
                    try:
                        write(b": keepalive\n\n")
                    except (OSError, ValueError):
                        return

            try:
                payload = json.loads(
                    self.rfile.read(int(self.headers["Content-Length"]))
                )
                validate_request(self.path, payload, model)
                body = json.dumps(payload).encode()
                (root / (rid + "-request.json")).write_bytes(body)
                event(
                    {
                        "id": rid,
                        "phase": "started",
                        "path": self.path,
                        "model": model,
                        "request_sha256": hashlib.sha256(body).hexdigest(),
                        "max_tokens": payload.get("max_tokens"),
                        "thinking": payload.get("thinking"),
                        "output_config": payload.get("output_config"),
                    }
                )
                early = payload.get("stream") is True
                if early:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.send_header("Connection", "close")
                    self.end_headers()
                    write(b": gateway-ready\n\n")
                    threading.Thread(target=heartbeat, daemon=True).start()
                if early and config.get("stream_mode") == "validated_buffer":

                    def open_response():
                        upstream = http.client.HTTPSConnection(
                            up.hostname, up.port or 443, timeout=28800
                        )
                        headers = {
                            "Content-Type": "application/json",
                            "Accept-Encoding": "identity",
                            "x-api-key": config["api_key"],
                            "anthropic-version": self.headers.get(
                                "anthropic-version", "2023-06-01"
                            ),
                        }
                        if self.headers.get("anthropic-beta"):
                            headers["anthropic-beta"] = self.headers["anthropic-beta"]
                        try:
                            upstream.request(
                                "POST",
                                "/d/" + config["task_id"] + self.path,
                                body,
                                headers,
                            )
                            return upstream, upstream.getresponse()
                        except BaseException:
                            upstream.close()
                            raise

                    def attempt_event(phase, attempt, detail):
                        detail = dict(detail)
                        raw_error = detail.pop("raw_error", None)
                        if raw_error is not None:
                            error_file = root / (
                                rid + "-attempt" + str(attempt) + "-error.json"
                            )
                            error_file.write_text(json.dumps(raw_error))
                            detail["error_sha256"] = hashlib.sha256(
                                error_file.read_bytes()
                            ).hexdigest()
                        if detail.get("status") in (401, 403):
                            (root / "STOP.json").write_text(
                                json.dumps(
                                    {
                                        "reason": "upstream_auth",
                                        "status": detail["status"],
                                    }
                                )
                            )
                        event(
                            {
                                "id": rid,
                                "phase": "upstream_attempt_" + phase,
                                "attempt": attempt,
                                "elapsed": time.time() - started,
                                **detail,
                            }
                        )

                    payload, metadata = buffered_retry(
                        open_response,
                        model,
                        config.get("max_upstream_attempts", 1),
                        attempt_event,
                    )
                    usage = metadata["usage"]
                    stop_reason = metadata["stop_reason"]
                    write(payload)
                    complete = True
                    event(
                        {
                            "id": rid,
                            "phase": "completed",
                            "status": 200,
                            "stream_complete": True,
                            "stop_reason": stop_reason,
                            "usage": usage,
                            "elapsed": time.time() - started,
                            "transport": "validated_buffer",
                        }
                    )
                    return
                conn = http.client.HTTPSConnection(
                    up.hostname, up.port or 443, timeout=28800
                )
                path = "/d/" + config["task_id"] + self.path
                headers = {
                    "Content-Type": "application/json",
                    "Accept-Encoding": "identity",
                    "x-api-key": config["api_key"],
                    "anthropic-version": self.headers.get(
                        "anthropic-version", "2023-06-01"
                    ),
                }
                if self.headers.get("anthropic-beta"):
                    headers["anthropic-beta"] = self.headers["anthropic-beta"]
                conn.request("POST", path, body, headers)
                response = conn.getresponse()
                if response.status != 200:
                    raw = response.read(8192)
                    (root / (rid + "-error.bin")).write_bytes(raw)
                    event(
                        {
                            "id": rid,
                            "phase": "upstream_error",
                            "status": response.status,
                            "error_sha256": hashlib.sha256(raw).hexdigest(),
                            "elapsed": time.time() - started,
                            "usage_unknown": True,
                        }
                    )
                    if response.status in (401, 403):
                        (root / "STOP.json").write_text(
                            json.dumps(
                                {"reason": "upstream_auth", "status": response.status}
                            )
                        )
                    raise RuntimeError("UpstreamHTTP_" + str(response.status))
                if not early:
                    raw = response.read()
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    write(raw)
                    complete = True
                else:
                    pending = b""
                    frame = b""
                    while True:
                        chunk = response.read1(8192)
                        if not chunk:
                            break
                        pending += chunk
                        while b"\n" in pending:
                            line, pending = pending.split(b"\n", 1)
                            frame += line + b"\n"
                            if line.startswith(b"data:"):
                                data = json.loads(line[5:].strip())
                                if data.get("type") == "error":
                                    # Private diagnostic only: preserve the actual provider
                                    # error frame, never hidden reasoning or auth headers.
                                    raw_error = json.dumps(data).encode()
                                    (root / (rid + "-sse-error.json")).write_bytes(
                                        raw_error
                                    )
                                    event(
                                        {
                                            "id": rid,
                                            "phase": "provider_sse_error",
                                            "provider_error_type": data.get(
                                                "error", {}
                                            ).get("type"),
                                            "error_sha256": hashlib.sha256(
                                                raw_error
                                            ).hexdigest(),
                                            "elapsed": time.time() - started,
                                        }
                                    )
                                    raise RuntimeError("ProviderSSEError")
                                msg = data.get("message") or {}
                                reported = data.get("model") or msg.get("model")
                                if reported and reported != model:
                                    raise RuntimeError("ResponseModelMismatch")
                                usage.update(
                                    data.get("usage") or msg.get("usage") or {}
                                )
                                stop_reason = (
                                    data.get("delta", {}).get("stop_reason")
                                    or stop_reason
                                )
                                if data.get("type") == "message_stop":
                                    complete = True
                            if not line.strip():
                                write(frame)
                                frame = b""
                    if not complete or pending.strip() or frame.strip():
                        raise RuntimeError("IncompleteAnthropicStream")
                event(
                    {
                        "id": rid,
                        "phase": "completed",
                        "status": 200,
                        "stream_complete": complete,
                        "stop_reason": stop_reason,
                        "usage": usage,
                        "elapsed": time.time() - started,
                    }
                )
            except Exception as exc:
                code = (
                    str(exc)
                    if isinstance(exc, (RuntimeError, ValueError))
                    and len(str(exc)) < 100
                    else type(exc).__name__
                )
                event(
                    {
                        "id": rid,
                        "phase": "error",
                        "error_type": type(exc).__name__,
                        "code": code,
                        "stream_complete": complete,
                        "elapsed": time.time() - started,
                        "usage": usage,
                    }
                )
                try:
                    if early:
                        write(
                            sse_event(
                                {
                                    "type": "error",
                                    "error": {
                                        "type": "api_error",
                                        "message": "Gateway " + code,
                                    },
                                }
                            )
                        )
                    else:
                        self.send_error(502, "Scoped gateway error")
                except OSError:
                    pass
            finally:
                finished.set()
                if conn:
                    conn.close()
                self.close_connection = True

    server = ThreadingHTTPServer(("0.0.0.0", port), Handler)
    (root / "ready.json").write_text(
        json.dumps(
            {
                "port": port,
                "model": model,
                "entry_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "upstream_retry": config.get("stream_mode") == "validated_buffer"
                and config.get("max_upstream_attempts", 1) > 1,
                "stream_mode": config.get("stream_mode", "passthrough"),
                "max_upstream_attempts": config.get("max_upstream_attempts", 1),
            }
        )
    )
    server.serve_forever()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, required=True)
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--port", type=int, default=18570)
    a = p.parse_args()
    serve(a.config, a.root, a.port)


if __name__ == "__main__":
    main()
