"""Selection and conditioning invariants with scripted native backend."""

import asyncio
import json
from pathlib import Path
import tempfile
import unittest
import importlib.util
from append_rewrite.terminus.native import NativeRewriteLLM


class Renderer:
    chat_template = "fixture-template"
    identity = "fixture-tokenizer"

    def encode(self, text, add_special_tokens=False):
        return list(text.encode())

    def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True):
        return json.dumps(messages) + "\nASSISTANT:"


@unittest.skipUnless(importlib.util.find_spec("harbor"), "requires pinned Harbor SDK")
class RewriteSelection(unittest.TestCase):
    def test_reference_generation_public_scoring_actual_selection(self):
        class Client:
            n = 0

            def generate(self, prompt, tokenizer, **kwargs):
                self.n += 1
                assert "<expert_reference>" in prompt
                raw = json.dumps(
                    {
                        "commands": [
                            {"keystrokes": f"echo {self.n}\n", "duration": 0.1}
                        ],
                        "task_complete": False,
                    }
                )
                return {
                    "text": raw,
                    "meta_info": {"prompt_tokens": 20, "completion_tokens": 10},
                }

            def score(self, rendered, **kwargs):
                assert "<expert_reference>" not in rendered.text
                return {"mean_logprob": -0.1 if "echo 2" in rendered.text else -1.0}

        with tempfile.TemporaryDirectory() as d:
            b = NativeRewriteLLM.__new__(NativeRewriteLLM)
            b.client = Client()
            b.tokenizer = Renderer()
            b.reference = "expert fixture"
            b.root = Path(d)
            b.proposals = 2
            b.turn = 0
            b.model_name = "fixture"
            b.decisions = []
            r = asyncio.run(b.call("public task"))
            self.assertIn("echo 2", r.content)
            record = json.loads((Path(d) / "turn-0001/decision.json").read_text())
            self.assertEqual(record["selected_index"], 1)
            self.assertEqual(len(record["candidates"]), 2)
            self.assertNotIn("<expert_reference>", json.dumps(record))
            self.assertEqual(
                r.usage.prompt_tokens, 40 + record["scoring_prefill_tokens"]
            )
