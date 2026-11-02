"""Meaningful local boundaries; no model, cloud or credentials required."""

from pathlib import Path
import tempfile
import unittest
from append_rewrite.collect import observable, project
from append_rewrite.sandbox import pack


class Boundaries(unittest.TestCase):
    def test_private_thinking_is_removed_but_real_tools_remain(self):
        blocks = [
            {"type": "thinking", "thinking": "private"},
            {"type": "redacted_thinking", "data": "opaque"},
            {
                "type": "tool_use",
                "id": "one",
                "name": "Bash",
                "input": {"command": "ls"},
            },
            {"type": "text", "text": "Public statement"},
        ]
        result = observable(blocks)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["input"]["command"], "ls")
        self.assertNotIn("private", str(result))

    def test_nested_tool_results_do_not_reintroduce_private_blocks(self):
        value = observable(
            [
                {
                    "type": "tool_result",
                    "tool_use_id": "one",
                    "content": [
                        {"type": "thinking", "thinking": "private"},
                        {"type": "text", "text": "exit=0"},
                    ],
                }
            ]
        )
        self.assertEqual(value[0]["content"], [{"type": "text", "text": "exit=0"}])

    def test_native_projection_skips_internal_records_and_malformed_lines(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "session.jsonl"
            p.write_text(
                'not-json\n{"type":"progress","data":"private"}\n'
                '{"message":{"role":"assistant","content":[{"type":"thinking","thinking":"private"},{"type":"text","text":"visible"}]}}\n'
            )
            self.assertEqual(
                project(p),
                [
                    {
                        "role": "assistant",
                        "content": [{"type": "text", "text": "visible"}],
                    }
                ],
            )

    def test_state_pack_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root)
            (p / "link").symlink_to("/etc/passwd")
            with self.assertRaises(ValueError):
                pack(p)
