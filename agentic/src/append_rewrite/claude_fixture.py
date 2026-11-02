"""Loopback-only deterministic Anthropic fixture. NO upstream/model requests."""

from __future__ import annotations
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path

MARKER = "NATIVE_PROTOCOL_OK"
CALL_ID = "toolu_protocol_fixture_1"


def reply(model, tool):
    message = {
        "id": "msg_fixture_tool" if tool else "msg_fixture_final",
        "type": "message",
        "role": "assistant",
        "content": [],
        "model": model,
        "stop_reason": None,
        "stop_sequence": None,
        "usage": {"input_tokens": 1, "output_tokens": 0},
    }
    frames = [{"type": "message_start", "message": message}]
    if tool:
        block = {"type": "tool_use", "id": CALL_ID, "name": "Bash", "input": {}}
        delta = {
            "type": "input_json_delta",
            "partial_json": json.dumps(
                {
                    "command": "printf " + MARKER + " | tee native-protocol-marker",
                    "description": "Deterministic offline protocol check",
                    "timeout": 10000,
                }
            ),
        }
    else:
        block = {"type": "text", "text": ""}
        delta = {"type": "text_delta", "text": "Offline protocol fixture completed."}
    frames.extend(
        [
            {"type": "content_block_start", "index": 0, "content_block": block},
            {"type": "content_block_delta", "index": 0, "delta": delta},
            {"type": "content_block_stop", "index": 0},
            {
                "type": "message_delta",
                "delta": {
                    "stop_reason": "tool_use" if tool else "end_turn",
                    "stop_sequence": None,
                },
                "usage": {"output_tokens": 1},
            },
            {"type": "message_stop"},
        ]
    )
    return "".join(
        "event: " + f["type"] + "\ndata: " + json.dumps(f) + "\n\n" for f in frames
    ).encode()


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, required=True)
    p.add_argument("--port", type=int, default=18771)
    a = p.parse_args()
    a.root.mkdir(parents=True, exist_ok=False)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            count = len(list(a.root.glob("request-*.json"))) + 1
            (a.root / f"request-{count:03d}.json").write_text(
                json.dumps({"path": self.path, "body": body})
            )
            if self.path.split("?")[0] == "/v1/messages/count_tokens":
                data = json.dumps({"input_tokens": 1000}).encode()
                kind = "application/json"
            elif self.path.split("?")[0] == "/v1/messages":
                has_result = any(
                    b.get("type") == "tool_result" and b.get("tool_use_id") == CALL_ID
                    for m in body.get("messages", [])
                    for b in m.get("content", [])
                    if isinstance(b, dict)
                )
                if has_result:
                    matches = [
                        b
                        for m in body["messages"]
                        for b in m.get("content", [])
                        if isinstance(b, dict) and b.get("tool_use_id") == CALL_ID
                    ]
                    if not any(MARKER in json.dumps(b) for b in matches):
                        self.send_error(400, "Real tool feedback missing")
                        return
                data = reply(body["model"], not has_result)
                kind = "text/event-stream"
            else:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
            self.wfile.flush()

    server = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    (a.root / "ready.json").write_text(
        json.dumps(
            {"port": a.port, "new_model_requests": 0, "upstream_network_used": False}
        )
    )
    server.serve_forever()


if __name__ == "__main__":
    main()
