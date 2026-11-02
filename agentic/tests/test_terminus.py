"""Public raw-text boundaries and privileged-conditioning separation."""

import asyncio
import json
from types import SimpleNamespace
import unittest
from append_rewrite.terminus.protocol import (
    checkpoint,
    scoring_input,
    sft_preview,
    action,
    verify_checkpoint,
)
from append_rewrite.terminus.runtime import ReferenceLLM

RAW = json.dumps(
    {
        "analysis": "fixture",
        "plan": "write then inspect",
        "commands": [{"keystrokes": "echo hello\n", "duration": 0.1}],
        "task_complete": False,
    }
)


class TerminusProtocol(unittest.TestCase):
    def parent(self):
        return checkpoint(
            [],
            "public task",
            {"state_id": "actual-id", "scopes": ["files", "live-tmux"]},
        )

    def test_raw_action_scoring(self):
        h, a = scoring_input(self.parent(), RAW)
        self.assertEqual(h, [{"role": "user", "content": "public task"}])
        self.assertEqual(a, RAW)
        self.assertEqual(len(action(a)["commands"]), 1)

    def test_drift_and_missing_state_fail(self):
        p = self.parent()
        p["pending_prompt"] = "wrong"
        with self.assertRaises(ValueError):
            verify_checkpoint(p)
        with self.assertRaises(ValueError):
            checkpoint([], "task", {})

    def test_no_partial_batch_checkpoint(self):
        with self.assertRaises(ValueError):
            checkpoint(
                [{"role": "user", "content": "task"}],
                "next",
                {"state_id": "x", "scopes": ["files"]},
            )

    def test_no_privileged_public_input(self):
        with self.assertRaises(ValueError):
            checkpoint(
                [],
                "<expert_reference>answer</expert_reference>",
                {"state_id": "x", "scopes": ["files"]},
            )

    def test_no_hidden_or_tools_projection(self):
        for m in (
            {"role": "assistant", "content": RAW, "reasoning_content": "hidden"},
            {"role": "tool", "content": "fake"},
        ):
            with self.assertRaises(ValueError):
                checkpoint([m], "next", {"state_id": "x", "scopes": ["files"]})

    def test_whole_batch_sft_mask(self):
        h = [
            {"role": "user", "content": "task"},
            {"role": "assistant", "content": RAW},
            {"role": "user", "content": "actual terminal output"},
            {"role": "assistant", "content": RAW},
        ]
        v = sft_preview(h, 1, 2)
        self.assertEqual(v["assistant_loss_by_message"], [False, False, False, True])
        self.assertEqual(v["messages"][-1]["content"], RAW)
        self.assertFalse(v["training_admitted"])

    def test_native_prose_and_fences_preserve_raw_scoring(self):
        for raw in ("Visible status note.\n" + RAW, "```json\n" + RAW + "\n```"):
            self.assertEqual(action(raw), action(RAW))
            _, scored = scoring_input(self.parent(), raw)
            self.assertEqual(scored, raw)
        with self.assertRaises(ValueError):
            action("<think>hidden</think>" + RAW)

    def test_invalid_actions_rejected(self):
        for raw in (
            '{"commands":[],"commands":[]}',
            '{"commands":[{"keystrokes":"x","duration":NaN}]}',
            '{"commands":[],"task_complete":1}',
        ):
            with self.assertRaises(ValueError):
                action(raw)

    def test_reference_is_wire_only(self):
        class Backend:
            async def call(self, **kwargs):
                self.kwargs = kwargs
                kwargs["message_history"].clear()
                return SimpleNamespace(response_id="privileged-chain")

        b = Backend()
        h = [{"role": "user", "content": "old"}, {"role": "assistant", "content": RAW}]
        result = asyncio.run(
            ReferenceLLM(b, "expert answer").call(
                "next", h, previous_response_id="old-chain"
            )
        )
        self.assertEqual(len(h), 2)
        self.assertIn("<expert_reference>", b.kwargs["prompt"])
        self.assertNotIn("previous_response_id", b.kwargs)
        self.assertIsNone(result.response_id)
