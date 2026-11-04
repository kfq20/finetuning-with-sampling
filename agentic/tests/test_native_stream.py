"""No partial native SSE response may become an executable candidate."""

import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace

from append_rewrite.terminus.native_stream import consume, NativeStreamClient


class ContextBudget(unittest.TestCase):
    def test_reserve_only_remaining_context_and_reject_full_prompt_before_post(self):
        c = object.__new__(NativeStreamClient)
        c.config = {"context_limit": 5, "api_key": "fixture", "model_id": "fixture"}
        c.endpoint = "https://example.test/generate"
        tokenizer = SimpleNamespace(encode=lambda *a, **k: [1, 2, 3])
        with (
            tempfile.TemporaryDirectory() as d,
            patch(
                "append_rewrite.terminus.native_stream.urlopen",
                side_effect=TimeoutError,
            ) as request,
        ):
            with self.assertRaises(TimeoutError):
                c.generate("prompt", tokenizer, journal=Path(d) / "request")
            body = json.loads((Path(d) / "request/request.json").read_text())
            self.assertEqual(body["sampling_params"]["max_new_tokens"], 2)
            self.assertEqual(request.call_count, 1)
        c.config["context_limit"] = 3
        with (
            tempfile.TemporaryDirectory() as d,
            patch("append_rewrite.terminus.native_stream.urlopen") as request,
        ):
            with self.assertRaises(ValueError):
                c.generate("prompt", tokenizer, journal=Path(d) / "request")
            request.assert_not_called()


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


class ZeroGenerationSSE(unittest.TestCase):
    def test_expected_zero_length_stop_is_complete_score(self):
        v = event("", {"type": "length", "length": 0})
        v["meta_info"]["completion_tokens"] = 0
        with tempfile.TemporaryDirectory() as d:
            result = consume(stream([v, None]), d, 3, scoring=True)
            self.assertEqual(result["meta_info"]["completion_tokens"], 0)

    def test_score_cannot_deliver_generated_text_or_tokens(self):
        for text, tokens in (("unexpected", 0), ("", 1)):
            v = event(text, {"type": "length", "length": 0})
            v["meta_info"]["completion_tokens"] = tokens
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaises(ValueError):
                    consume(stream([v]), d, 3, scoring=True)
