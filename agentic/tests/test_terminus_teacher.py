"""Teacher transport invariants without model requests."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from append_rewrite.terminus.teacher import DeepSeekTeacher


class TeacherTransport(unittest.TestCase):
    def test_user_route_is_bound_to_policy_and_credential(self):
        config = {
            "base_url": "https://mint.macaron.im",
            "model_id": "deepseek-flash", "api_key": "fixture",
            "credential_sha256": "66c75200769a56ae92942b85c1f005293686eef6e6069d7413720e3a125055bd",
            "policy_sha256": "cd3e3f4a35b3de4e1019cbb16f2f7a983b65b42d36f49eef9de35390ba333ad5",
        }
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "private.json"
            p.touch(mode=0o600)
            def load(c, name):
                p.write_text(json.dumps(c))
                return DeepSeekTeacher(p, Path(d) / name)
            with patch("append_rewrite.terminus.teacher.hashlib.sha256") as h:
                h.return_value.hexdigest.return_value = config["credential_sha256"]
                self.assertEqual(load(config, "accepted").model_name, "deepseek-flash")
                for key, value in (("policy_sha256", "wrong"), ("model_id", "other"),
                                   ("base_url", "https://other.invalid")):
                    with self.assertRaises(ValueError):
                        load(dict(config, **{key: value}), key)
                h.return_value.hexdigest.return_value = "wrong"
                with self.assertRaises(ValueError):
                    load(config, "bad-credential")

    def backend(self, root):
        b = DeepSeekTeacher.__new__(DeepSeekTeacher)
        b.config = {"base_url": "https://mintcn.macaron.xin", "api_key": "fixture"}
        b.model_name = "deepseek-flash"
        return b

    def stream(self, events):
        class Response:
            status = 200
            headers = {"x-request-id": "fixture-request"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                pass

            def __iter__(self):
                for event in events:
                    if event is None:
                        raise AssertionError(
                            "Must stop at message_stop without waiting for EOF"
                        )
                    yield ("data: " + json.dumps(event) + "\n").encode()

        return Response()

    def events(self):
        return [
            {
                "type": "message_start",
                "message": {
                    "id": "fixture",
                    "model": "deepseek-flash",
                    "usage": {"input_tokens": 12},
                },
            },
            {
                "type": "content_block_delta",
                "delta": {"type": "thinking_delta", "thinking": "PRIVATE_FIXTURE"},
            },
            {
                "type": "content_block_delta",
                "delta": {
                    "type": "text_delta",
                    "text": '{"commands":[],"task_complete":true}',
                },
            },
            {
                "type": "message_delta",
                "delta": {"stop_reason": "end_turn"},
                "usage": {"output_tokens": 4},
            },
            {"type": "message_stop"},
            None,
        ]

    def test_complete_and_no_hidden_text(self):
        with tempfile.TemporaryDirectory() as d:
            b = self.backend(Path(d))
            with patch(
                "append_rewrite.terminus.teacher.urlopen",
                return_value=self.stream(self.events()),
            ) as request:
                r = b.request(
                    [{"role": "user", "content": "task"}], Path(d) / "request"
                )
            self.assertEqual(request.call_count, 1)
            self.assertNotIn("PRIVATE_FIXTURE", r["content"])
            self.assertEqual(r["request_id"], "fixture")

    def test_incomplete_does_not_deliver_partial(self):
        with tempfile.TemporaryDirectory() as d:
            b = self.backend(Path(d))
            with patch(
                "append_rewrite.terminus.teacher.urlopen",
                return_value=self.stream(self.events()[:3]),
            ):
                with self.assertRaises(RuntimeError):
                    b.request([], Path(d) / "request")
            self.assertFalse((Path(d) / "request/observable-response.json").exists())

    def test_error_does_not_retry(self):
        with tempfile.TemporaryDirectory() as d:
            b = self.backend(Path(d))
            with patch(
                "append_rewrite.terminus.teacher.urlopen",
                return_value=self.stream([{"type": "error"}]),
            ) as request:
                with self.assertRaises(RuntimeError):
                    b.request([], Path(d) / "request")
            self.assertEqual(request.call_count, 1)
