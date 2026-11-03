"""No partial native SSE response may become an executable candidate."""

import json
from pathlib import Path
import tempfile
import unittest

from append_rewrite.terminus.native_stream import consume


def event(text, finish=None, request_id="fixture"):
    return {
        "text": text,
        "meta_info": {"id": request_id, "prompt_tokens": 3, "finish_reason": finish},
    }


def stream(values):
    for v in values:
        if v is None:
            raise AssertionError("Must stop at explicit model stop before EOF")
        yield ("data: " + json.dumps(v) + "\n").encode()
        yield b"\n"


class NativeSSE(unittest.TestCase):
    def test_normal_stop_no_eof_wait(self):
        with tempfile.TemporaryDirectory() as d:
            result = consume(
                stream([event("a"), event("ab", {"type": "stop"}), None]), d, 3
            )
            self.assertEqual(result["text"], "ab")
            self.assertTrue((Path(d) / "transport.json").exists())

    def test_truncated_is_error(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                consume(stream([event("partial")]), d, 3)
            self.assertFalse((Path(d) / "transport.json").exists())

    def test_length_or_error_not_normal(self):
        for value in (event("partial", {"type": "length"}), {"error": "interrupted"}):
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaises((ValueError, RuntimeError)):
                    consume(stream([value]), d, 3)

    def test_identity_text_or_input_drift_rejected(self):
        for value in (event("different"), event("ab", request_id="other")):
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaises(ValueError):
                    consume(stream([event("a"), value]), d, 3)
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                consume(stream([event("a")]), d, 4)
