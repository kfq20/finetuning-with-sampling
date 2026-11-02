"""Opt-in native Harbor+real isolated tmux integration; zero provider requests."""

import asyncio
import json
import os
from pathlib import Path
import tempfile
import unittest
import uuid


@unittest.skipUnless(
    os.environ.get("REWRITE_NATIVE_TM​​UX_TEST".replace("\u200b", "")) == "1",
    "requires pinned Harbor and Linux tmux",
)
class NativeTerminus(unittest.TestCase):
    def test_backend_usage_and_no_native_paid_retry(self):
        from types import SimpleNamespace
        from harbor.llms.chat import Chat
        from append_rewrite.terminus.backend import FleetLLM
        from append_rewrite.terminus.runtime import make_agent

        async def exercise(root):
            calls = []

            def response(*args, **kwargs):
                calls.append(kwargs)
                return {
                    "choices": [
                        {"finish_reason": "stop", "message": {"content": "fixture"}}
                    ],
                    "usage": {
                        "prompt_tokens": 12,
                        "completion_tokens": 3,
                        "prompt_tokens_details": {"cached_tokens": 4},
                    },
                }

            b = FleetLLM.__new__(FleetLLM)
            b.fleet = SimpleNamespace(chat=response)
            b.requests, b.deadline, b.max_output_tokens = 0, 9999999999, 128000
            b.root, b.model_name = root, "fixture"
            got = await b.call("task")
            self.assertEqual(got.usage.cache_tokens, 4)
            self.assertEqual(got.usage.prompt_tokens, 12)
            self.assertEqual(len(calls), 1)

            class Broken:
                calls = 0

                async def call(self, **kwargs):
                    self.calls += 1
                    raise RuntimeError("Ambiguous provider failure")

            broken = Broken()
            agent = make_agent(root / "agent", "fixture", backend=broken)
            with self.assertRaises(RuntimeError):
                await agent._query_llm(Chat(agent._llm), "task")
            self.assertEqual(broken.calls, 1)

        with tempfile.TemporaryDirectory(
            dir=os.environ.get("REWRITE_TEST_ROOT")
        ) as directory:
            asyncio.run(exercise(Path(directory)))

    def test_native_batch_feedback_and_confirmed_completion(self):
        from harbor.llms.base import LLMResponse
        from harbor.models.agent.context import AgentContext
        from harbor.environments.base import ExecResult
        from append_rewrite.terminus.runtime import make_agent

        async def exercise(root):
            socket = "rewrite-test-" + uuid.uuid4().hex
            marker = root / "result.txt"

            class Environment:
                default_user = None

                async def exec(self, command, **kwargs):
                    cmd = command.replace("tmux ", f"tmux -L {socket} ").replace(
                        "/logs/agent", str(root / "terminal-logs")
                    )
                    proc = await asyncio.create_subprocess_shell(
                        cmd,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    out, err = await proc.communicate()
                    return ExecResult(
                        stdout=out.decode(),
                        stderr=err.decode(),
                        return_code=proc.returncode,
                    )

            class Backend:
                n = 0

                def get_model_context_limit(self):
                    return 1000000

                def get_model_output_limit(self):
                    return 128000

                async def call(self, prompt, message_history=None, **kwargs):
                    self.n += 1
                    assert "<expert_reference>" in prompt
                    assert all(
                        "<expert_reference>" not in m["content"]
                        for m in (message_history or [])
                    )
                    commands = (
                        [
                            {
                                "keystrokes": f"printf 'NATIVE_OK\\n' > {marker}; cat {marker}\n",
                                "duration": 0.3,
                            }
                        ]
                        if self.n == 1
                        else []
                    )
                    return LLMResponse(
                        content=json.dumps(
                            {
                                "analysis": "fixture",
                                "plan": "fixture",
                                "commands": commands,
                                "task_complete": self.n > 1,
                            }
                        )
                    )

            boundaries = []

            async def before(agent, history, prompt):
                if len(history) == 2:
                    self.assertIn("NATIVE_OK", prompt)
                boundaries.append(
                    agent.capture_boundary(
                        history,
                        prompt,
                        {"state_id": socket, "scopes": ["live-terminal"]},
                    )
                )

            b, env = Backend(), Environment()
            agent = make_agent(
                root / "agent",
                "fixture-native",
                backend=b,
                reference="fixture reference",
                before_model=before,
            )
            try:
                await agent.setup(env)
                ctx = AgentContext()
                await asyncio.wait_for(
                    agent.run("Write result.txt and verify it", env, ctx), 30
                )
                self.assertEqual(marker.read_text(), "NATIVE_OK\n")
                self.assertEqual(b.n, 3)
                self.assertEqual(len(boundaries), 3)
                self.assertEqual(len(agent._chat.messages), 6)
                self.assertTrue(agent._pending_completion)
            finally:
                await env.exec("tmux kill-server")

        with tempfile.TemporaryDirectory(
            prefix="native-test-", dir=os.environ.get("REWRITE_TEST_ROOT")
        ) as directory:
            asyncio.run(exercise(Path(directory)))
