"""Fault injection for request-level retry without a provider or sandbox."""

import json
import unittest
from append_rewrite.claude_gateway import (
    StreamFailure,
    buffered_retry,
    sse_event,
    validated_stream,
)


def valid_tool_stream(model="selected", partials=None):
    events = [
        {
            "type": "message_start",
            "message": {"model": model, "usage": {"input_tokens": 7}},
        },
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {
                "type": "tool_use",
                "id": "call-1",
                "name": "Bash",
                "input": {},
            },
        },
    ]
    for piece in partials or ['{"command":', '"echo ok"}']:
        events.append(
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "input_json_delta", "partial_json": piece},
            }
        )
    events += [
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "tool_use"},
            "usage": {"output_tokens": 9},
        },
        {"type": "message_stop"},
    ]
    return b"".join(sse_event(x) for x in events)


class Response:
    def __init__(self, raw, status=200, fragment=13):
        self.raw, self.status, self.fragment = raw, status, fragment

    def read1(self, length):
        part, self.raw = self.raw[: self.fragment], self.raw[self.fragment :]
        return part

    def read(self, length):
        return self.raw[:length]


class Connection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


class BufferedRetryTests(unittest.TestCase):
    def test_late_error_discards_first_tool_then_delivers_only_valid_attempt(self):
        good = valid_tool_stream()
        # A complete tool block was emitted before a transient SSE error.
        failed = good[: good.index(b"event: message_delta")] + sse_event(
            {
                "type": "error",
                "error": {
                    "type": "api_error",
                    "message": "upstream stream interrupted",
                },
            }
        )
        responses = iter([Response(failed), Response(good)])
        connections, events, delays = [], [], []

        def open_response():
            c = Connection()
            connections.append(c)
            return c, next(responses)

        delivered, meta = buffered_retry(
            open_response,
            "selected",
            2,
            lambda *x: events.append(x),
            sleep=delays.append,
        )
        self.assertEqual(delivered, good)
        self.assertEqual(delivered.count(b'"type": "tool_use"'), 1)
        self.assertEqual(meta["stop_reason"], "tool_use")
        self.assertEqual(len(connections), 2)
        self.assertTrue(all(c.closed for c in connections))
        error = next(x[2] for x in events if x[0] == "error")
        self.assertEqual(error["delivered_upstream_content_bytes"], 0)
        self.assertTrue(error["usage_unknown"])
        self.assertEqual(delays, [2])

    def test_fragmented_valid_json_is_preserved(self):
        raw = valid_tool_stream()
        actual, _ = validated_stream(Response(raw, fragment=1), "selected")
        self.assertEqual(actual, raw)

    def test_incomplete_tool_input_is_rejected_before_delivery(self):
        with self.assertRaisesRegex(StreamFailure, "IncompleteToolInputJSON"):
            validated_stream(
                Response(valid_tool_stream(partials=['{"command":'])), "selected"
            )

    def test_auth_failure_is_not_retried(self):
        attempts = []

        def open_response():
            attempts.append(1)
            return Connection(), Response(
                json.dumps({"error": "unauthorized"}).encode(), status=401
            )

        with self.assertRaisesRegex(StreamFailure, "UpstreamHTTP_401"):
            buffered_retry(open_response, "selected", 3, lambda *x: None)
        self.assertEqual(len(attempts), 1)

    def test_model_mismatch_is_not_retried(self):
        attempts = []

        def open_response():
            attempts.append(1)
            return Connection(), Response(valid_tool_stream(model="wrong"))

        with self.assertRaisesRegex(StreamFailure, "ResponseModelMismatch"):
            buffered_retry(open_response, "selected", 3, lambda *x: None)
        self.assertEqual(len(attempts), 1)

    def test_transient_failures_stop_at_explicit_attempt_count(self):
        attempts = []

        def open_response():
            attempts.append(1)
            return Connection(), Response(b"", status=503)

        with self.assertRaisesRegex(StreamFailure, "UpstreamHTTP_503"):
            buffered_retry(
                open_response, "selected", 2, lambda *x: None, sleep=lambda _: None
            )
        self.assertEqual(len(attempts), 2)
