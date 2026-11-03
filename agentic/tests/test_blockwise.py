"""Eight candidates, public likelihood only, selected action returned to harness."""

import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from append_rewrite.terminus.blockwise import BlockwiseLLM, select


class Renderer:
    chat_template = "fixture"
    identity = "fixture"

    def encode(self, text, add_special_tokens=False):
        return list(text.encode())

    def apply_chat_template(self, messages, **kwargs):
        return json.dumps(messages) + "\nASSISTANT:"


class Ranking(unittest.TestCase):
    def test_no_progress_or_verifier_score_added(self):
        reading = {"status": "scored", "raw": "cat", "score": {"mean_logprob": -0.1}}
        repair = {"status": "scored", "raw": "repair", "score": {"mean_logprob": -1}}
        self.assertIs(select([repair, reading]), reading)


@unittest.skipUnless(importlib.util.find_spec("harbor"), "requires native SDK")
class BlockwiseProtocol(unittest.TestCase):
    def test_eight_same_prefix_ranked_with_no_reference_and_no_tools(self):
        class Client:
            def generate(self, wire, tokenizer, *, journal):
                assert "FULL_EXPERT_TRACE" in wire
                index = int(journal.name.split("-")[-1])
                return {
                    "text": json.dumps(
                        {
                            "commands": [
                                {"keystrokes": f"echo {index}\n", "duration": 0.1}
                            ],
                            "task_complete": False,
                        }
                    ),
                    "meta_info": {
                        "prompt_tokens": 100,
                        "completion_tokens": 10,
                        "id": str(index),
                    },
                }

            def score(self, rendered, *, journal):
                assert "FULL_EXPERT_TRACE" not in rendered.text
                return {
                    "mean_logprob": -10 + int(journal.name.split("-")[-1]),
                    "token_count": 10,
                    "sum_logprob": -20,
                }

        with tempfile.TemporaryDirectory() as d:
            b = BlockwiseLLM.__new__(BlockwiseLLM)
            b.client = Client()
            b.tokenizer = Renderer()
            b.reference = "FULL_EXPERT_TRACE"
            b.proposals = 8
            b.root = Path(d)
            b.model_name = "fixture"
            b.decisions = []
            b.turn = 0
            response = asyncio.run(b.call("task"))
            self.assertIn("echo 7", response.content)
            self.assertEqual(len(b.decisions[0]["candidates"]), 8)
            self.assertEqual(b.decisions[0]["selected_index"], 7)
            self.assertEqual(b.decisions[0]["intermediate_verifier_calls"], 0)


@unittest.skipUnless(importlib.util.find_spec("harbor"), "requires native SDK")
class DirectReferenceBaseline(unittest.TestCase):
    def test_one_generation_no_online_scoring_or_selection(self):
        from append_rewrite.terminus.episode import EpisodeLLM

        class Client:
            calls = 0

            def generate(self, wire, tokenizer, **kwargs):
                assert "FULL_EXPERT_TRACE" in wire
                self.calls += 1
                return {
                    "text": '{"commands":[],"task_complete":true}',
                    "meta_info": {
                        "prompt_tokens": 100,
                        "completion_tokens": 10,
                        "id": "fixture",
                    },
                }

            def score(self, *args, **kwargs):
                raise AssertionError("Direct rollout must not perform online scoring")

        with tempfile.TemporaryDirectory() as d:
            b = EpisodeLLM.__new__(EpisodeLLM)
            b.client = Client()
            b.tokenizer = Renderer()
            b.reference = "FULL_EXPERT_TRACE"
            b.root = Path(d)
            b.model_name = "fixture"
            b.decisions = []
            result = asyncio.run(b.call("actual task"))
            self.assertEqual(b.client.calls, 1)
            self.assertEqual(len(b.decisions), 1)
            self.assertEqual(result.content, '{"commands":[],"task_complete":true}')
