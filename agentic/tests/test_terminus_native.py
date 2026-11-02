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
    def test_native_batch_feedback_and_confirmed_completion(self):
        from harbor.agents.terminus_2.tmux_session import TmuxSession
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
                    cmd = command.replace("tmux ", f"tmux -L {socket} ")
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
                if history:
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
            agent._session = TmuxSession(
                session_name="test",
                environment=env,
                logging_path=root / "pane.log",
                local_asciinema_recording_path=None,
                remote_asciinema_recording_path=None,
            )
            try:
                await agent._session.start()
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
