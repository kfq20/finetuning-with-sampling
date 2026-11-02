"""Meaningful local boundaries; no model, cloud or credentials required."""

from pathlib import Path
import tempfile
import unittest
from append_rewrite.collect import observable, project
from append_rewrite.sandbox import archive_manifest, capture, command, pack
import io
import tarfile
from types import SimpleNamespace


class Boundaries(unittest.TestCase):
    def test_capture_executes_shell_and_preserves_file_modes(self):
        b = io.BytesIO()
        with tarfile.open(fileobj=b, mode="w:gz") as t:
            m = tarfile.TarInfo("app/project/a.py")
            m.size = 3
            m.mode = 0o750
            t.addfile(m, io.BytesIO(b"abc"))
        commands = []

        def run(text, **kw):
            commands.append(text)
            return SimpleNamespace(exit_code=0)

        sb = SimpleNamespace(
            commands=SimpleNamespace(run=run),
            files=SimpleNamespace(read=lambda *a, **kw: b.getvalue()),
        )
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "capture.tgz"
            meta = capture(sb, ["/app/project"], p)
            self.assertTrue(commands[0].startswith("tar czf"))
            self.assertEqual(meta["files"]["app/project/a.py"]["mode"], 0o750)
            self.assertEqual(meta["files"], archive_manifest(p))

    def test_failed_shell_is_observation_but_transport_error_is_not(self):
        class CommandExitException(Exception):
            exit_code = 1
            stdout = "test failed"
            stderr = ""

        def fail(*args, **kwargs):
            raise CommandExitException()

        sb = SimpleNamespace(commands=SimpleNamespace(run=fail))
        self.assertEqual(command(sb, "false").exit_code, 1)

        def timeout(*args, **kwargs):
            raise TimeoutError()

        sb.commands.run = timeout
        with self.assertRaises(TimeoutError):
            command(sb, "test")

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

    def test_durable_job_reconnect_does_not_repeat_submission(self):
        from append_rewrite.fleet import Fleet
        from http.client import IncompleteRead
        from unittest.mock import patch
        import time

        client = object.__new__(Fleet)
        client.config = {"model_id": "owned-model"}
        routes = []

        def request(route, body=None):
            routes.append(route)
            if body is not None:
                return {"job_id": "one"}
            if len(routes) == 2:
                raise IncompleteRead(b"")
            return {
                "status": "completed",
                "results": [{"status": "completed", "response": {"choices": []}}],
            }

        client.request = request
        with (
            tempfile.TemporaryDirectory() as root,
            patch("append_rewrite.fleet.time.sleep"),
        ):
            journal = Path(root) / "request"
            result = client.chat([], journal=journal, deadline=time.time() + 60)
            self.assertEqual(result, {"choices": []})
            self.assertEqual(routes.count("/control/jobs"), 1)
            self.assertTrue((journal / "accepted.json").is_file())
            with self.assertRaises(FileExistsError):
                client.chat([], journal=journal, deadline=time.time() + 60)
            self.assertEqual(routes.count("/control/jobs"), 1)

    def test_restore_uses_published_destination_not_public_folder_guess(self):
        from append_rewrite.state import plan
        from append_rewrite.collect import sha
        import json

        with tempfile.TemporaryDirectory() as root:
            task = Path(root) / "task"
            public = task / "environment/public"
            public.mkdir(parents=True)
            f = public / "input.db"
            f.write_bytes(b"checkpoint")
            f.chmod(0o640)
            (task / "runtime-binding.json").write_text(
                json.dumps(
                    {
                        "restore_manifests": {
                            "/app/project": {
                                "input.db": {"sha256": sha(f), "mode": 0o640}
                            }
                        }
                    }
                )
            )
            mapped = plan(task, Path(root) / "missing-native.jsonl")
            self.assertEqual(mapped, {"project/input.db": f})
            f.write_bytes(b"future-state")
            with self.assertRaisesRegex(ValueError, "checkpoint_source_missing"):
                plan(task, Path(root) / "missing-native.jsonl")

    def test_sse_requires_done_and_joins_real_tool_fragments(self):
        from append_rewrite.fleet import assemble_stream, FleetError

        events = [
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {
                                    "index": 0,
                                    "id": "tool1",
                                    "function": {
                                        "name": "execute",
                                        "arguments": '{"command":',
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
            {
                "choices": [
                    {
                        "delta": {
                            "tool_calls": [
                                {"index": 0, "function": {"arguments": '"ls"}'}}
                            ]
                        },
                        "finish_reason": "tool_calls",
                    }
                ]
            },
        ]
        with self.assertRaisesRegex(FleetError, "IncompleteSSE"):
            assemble_stream(events)
        response = assemble_stream(events + [None])
        call = response["choices"][0]["message"]["tool_calls"][0]
        self.assertEqual(call["function"]["arguments"], '{"command":"ls"}')
        self.assertEqual(call["function"]["name"], "execute")

    def test_state_pack_rejects_symlinks(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root)
            (p / "link").symlink_to("/etc/passwd")
            with self.assertRaises(ValueError):
                pack(p)
