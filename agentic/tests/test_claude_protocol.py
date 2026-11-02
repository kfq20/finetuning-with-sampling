"""Native import correctness without SDK, provider credentials or model calls."""

import json
from pathlib import Path
import tempfile
import unittest
import uuid
from append_rewrite.claude_protocol import (
    import_history,
    validate_pairs,
    append_instruction,
)


class NativeProtocol(unittest.TestCase):
    def test_hidden_parent_removed_without_losing_tool_feedback(self):
        sid = str(uuid.uuid4())
        records = []
        parent = None
        for role, content in [
            ("user", "original request"),
            (
                "assistant",
                [
                    {
                        "type": "thinking",
                        "thinking": "PRIVATE_SENTINEL",
                        "signature": "PRIVATE_SIGNATURE",
                    }
                ],
            ),
            (
                "assistant",
                [
                    {
                        "type": "tool_use",
                        "id": "one",
                        "name": "Bash",
                        "input": {"command": "echo hello", "timeout": 10000},
                    }
                ],
            ),
            (
                "user",
                [
                    {
                        "type": "tool_result",
                        "tool_use_id": "one",
                        "content": "hello",
                        "is_error": False,
                    }
                ],
            ),
            ("assistant", [{"type": "text", "text": "completed"}]),
        ]:
            key = str(uuid.uuid4())
            records.append(
                {
                    "uuid": key,
                    "parentUuid": parent,
                    "sessionId": sid,
                    "type": role,
                    "cwd": "/app/project",
                    "version": "2.1.207",
                    "message": {
                        "role": role,
                        "content": content,
                        "model": "source-model",
                    },
                }
            )
            parent = key
        records.append(
            {
                "type": "last-prompt",
                "leafUuid": parent,
                "sessionId": sid,
                "lastPrompt": "original request",
            }
        )
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "-app-project" / (sid + ".jsonl")
            path.parent.mkdir()
            path.write_text("".join(json.dumps(x) + "\n" for x in records))
            before = path.read_bytes()
            meta = import_history(path, Path(root) / "imported")
            data = Path(meta["imported_seed"]["path"]).read_text()
            self.assertNotIn("PRIVATE_SENTINEL", data)
            self.assertNotIn("PRIVATE_SIGNATURE", data)
            self.assertEqual(meta["public_messages"], 4)
            self.assertEqual(meta["tool_call_pairs"], 1)
            rows = [json.loads(x) for x in data.splitlines()]
            self.assertEqual(rows[1]["parentUuid"], rows[0]["uuid"])
            self.assertNotEqual(meta["session_id"], sid)
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(rows[2]["message"]["content"][0]["content"], "hello")

    def test_unfinished_tool_prefix_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "pending"):
            validate_pairs(
                [
                    {
                        "role": "assistant",
                        "content": [
                            {
                                "type": "tool_use",
                                "id": "one",
                                "name": "Bash",
                                "input": {},
                            }
                        ],
                    }
                ]
            )

    def test_compacted_history_is_not_silently_linearized(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "-app-project" / (str(uuid.uuid4()) + ".jsonl")
            source.parent.mkdir()
            source.write_text(
                json.dumps(
                    {
                        "type": "user",
                        "uuid": "summary",
                        "parentUuid": None,
                        "isCompactSummary": True,
                        "message": {"role": "user", "content": "summary"},
                    }
                )
                + "\n"
            )
            with self.assertRaisesRegex(ValueError, "compaction adapter"):
                import_history(source, Path(root) / "import")

    def test_new_instruction_has_no_serialized_parent_history(self):
        self.assertEqual(append_instruction("task"), "task")
        expert = [{"role": "assistant", "content": "public answer"}]
        result = append_instruction("task", expert)
        self.assertTrue(result.startswith("task\n\n<expert_reference"))
        self.assertNotIn("PUBLIC HISTORICAL CONTEXT", result)


class LiveGatewayContract(unittest.TestCase):
    def test_scoped_gateway_rejects_other_models_and_paths(self):
        from append_rewrite.claude_gateway import validate_request

        validate_request(
            "/v1/messages?beta=true", {"model": "selected", "stream": True}, "selected"
        )
        for path, body in [
            ("/v1/messages", {"model": "other", "stream": True}),
            ("/v1/completions", {"model": "selected", "stream": True}),
            ("/v1/messages", {"model": "selected", "stream": False}),
        ]:
            with self.assertRaises(ValueError):
                validate_request(path, body, "selected")

    def test_stream_parser_requires_real_native_terminal_record(self):
        from append_rewrite.claude_live_probe import terminal

        self.assertEqual(terminal('not json\n{"type":"assistant"}\n'), [])
        self.assertEqual(
            len(terminal('{"type":"result","is_error":false,"subtype":"success"}\n')), 1
        )


class NativeTrialMetricsTests(unittest.TestCase):
    def test_counts_only_new_native_tools(self):
        from append_rewrite.claude_trial import native_metrics

        with tempfile.TemporaryDirectory() as directory:
            seed = Path(directory) / "seed.jsonl"
            original = {
                "uuid": "old",
                "message": {
                    "content": [{"type": "tool_use", "id": "a", "name": "Bash"}]
                },
            }
            seed.write_text(json.dumps(original) + "\n")
            new = [
                {
                    "uuid": "new",
                    "message": {
                        "content": [{"type": "tool_use", "id": "b", "name": "Read"}]
                    },
                },
                {
                    "uuid": "feedback",
                    "message": {
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": "b",
                                "is_error": False,
                            }
                        ]
                    },
                },
            ]
            actual = native_metrics(
                seed, "\n".join(json.dumps(x) for x in [original] + new)
            )
            self.assertEqual(actual["tool_calls"], 1)
            self.assertTrue(actual["tool_pairs_complete"])
            self.assertEqual(actual["tools"][0]["name"], "Read")
