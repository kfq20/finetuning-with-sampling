"""Eight candidates, public likelihood only, selected action returned to harness."""

import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

from append_rewrite.terminus.blockwise import BlockwiseLLM, select, cached_proposal


class Renderer:
    chat_template = "fixture"
    identity = "fixture"

    def encode(self, text, add_special_tokens=False):
        return list(text.encode())

    def apply_chat_template(self, messages, **kwargs):
        return json.dumps(messages) + "\nASSISTANT:"


class Ranking(unittest.TestCase):
    def test_cached_candidate_requires_identical_conditioning_and_normal_stop(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            tok = Renderer()
            wire = "referenced history"
            ids = tok.encode(wire)
            (p / "request.json").write_text(json.dumps({"input_ids": ids}))
            result = {
                "text": "action",
                "meta_info": {
                    "prompt_tokens": len(ids),
                    "finish_reason": {"type": "stop"},
                },
            }
            (p / "response.json").write_text(json.dumps(result))
            self.assertEqual(cached_proposal(p, wire, tok), result)
            with self.assertRaises(ValueError):
                cached_proposal(p, wire + "changed", tok)
            result["meta_info"]["finish_reason"] = {"type": "length"}
            (p / "response.json").write_text(json.dumps(result))
            with self.assertRaises(ValueError):
                cached_proposal(p, wire, tok)

    def test_no_progress_or_verifier_score_added(self):
        reading = {"status": "scored", "raw": "cat", "score": {"mean_logprob": -0.1}}
        repair = {"status": "scored", "raw": "repair", "score": {"mean_logprob": -1}}
        self.assertIs(select([repair, reading]), reading)


@unittest.skipUnless(importlib.util.find_spec("harbor"), "requires native SDK")
class ExactScoreReuse(unittest.TestCase):
    def run_pool(self, *, enabled=True, distinct=False, fail=False, calls=1,
                 first_turn=False):
        class Client:
            config = {"exact_score_reuse": enabled}
            generated = 0
            scored = 0

            def generate(self, wire, tokenizer, *, journal):
                self.generated += 1
                index = int(journal.name.split("-")[-1])
                raw = '{"commands":[],"task_complete":true}'
                if distinct:
                    raw += " " * index  # Same action, different exact token input.
                return {"text": raw, "meta_info": {
                    "prompt_tokens": 10, "completion_tokens": 3, "id": str(index),
                }}

            def score(self, rendered, *, journal):
                self.scored += 1
                if fail:
                    raise ValueError("invalid score")
                return {"mean_logprob": -1.0, "token_count": 3}

        with tempfile.TemporaryDirectory() as d:
            b = BlockwiseLLM.__new__(BlockwiseLLM)
            b.client, b.tokenizer = Client(), Renderer()
            b.reference, b.proposals = "FULL_EXPERT_TRACE", 8
            b.root, b.model_name, b.decisions = Path(d), "fixture", []
            b.turn = 0 if first_turn else 1
            for _ in range(calls):
                if fail:
                    with self.assertRaisesRegex(RuntimeError, "Incomplete candidate"):
                        asyncio.run(b.call("task"))
                else:
                    asyncio.run(b.call("task"))
            if not fail:
                for decision in b.decisions:
                    self.assertEqual(decision["candidate_count"], 8)
                    self.assertEqual(decision["selected_index"], 0)
                if enabled and not distinct:
                    self.assertEqual(len(list(b.root.glob('turn-*/reused-score-*.json'))),
                                     calls * 7)
                    self.assertEqual(sum(c["scoring_input_tokens"] > 0
                                         for c in b.decisions[0]["candidates"]), 1)
            return b.client.generated, b.client.scored, len(b.decisions)

    def test_exact_inputs_share_one_score_only_within_each_call(self):
        self.assertEqual(self.run_pool(calls=2), (16, 2, 2))
        self.assertEqual(self.run_pool(first_turn=True), (8, 1, 1))

    def test_whitespace_differences_and_disabled_reuse_score_all_candidates(self):
        self.assertEqual(self.run_pool(distinct=True), (8, 8, 1))
        self.assertEqual(self.run_pool(enabled=False), (8, 8, 1))

    def test_shared_score_failure_does_not_retry_or_select_action(self):
        self.assertEqual(self.run_pool(fail=True), (8, 1, 0))


@unittest.skipUnless(importlib.util.find_spec("harbor"), "requires native SDK")
class BlockwiseProtocol(unittest.TestCase):
    def test_eight_same_prefix_ranked_with_no_reference_and_no_tools(self):
        class Client:
            config = {}

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


@unittest.skipUnless(importlib.util.find_spec("harbor"), "requires native SDK")
class PlainNoReferenceBaseline(unittest.TestCase):
    def test_no_reference_no_candidates_no_score(self):
        from append_rewrite.terminus.episode import EpisodeLLM

        class Client:
            calls = 0

            def generate(self, wire, tokenizer, **kwargs):
                assert "expert_reference" not in wire
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
                raise AssertionError("Plain baseline cannot use logprob scoring")

        with tempfile.TemporaryDirectory() as d:
            b = EpisodeLLM.__new__(EpisodeLLM)
            b.client = Client()
            b.tokenizer = Renderer()
            b.reference = None
            b.root = Path(d)
            b.model_name = "fixture"
            b.decisions = []
            asyncio.run(b.call("actual task"))
            self.assertEqual(b.client.calls, 1)
            self.assertEqual(len(b.decisions), 1)
