"""Generated-token scores must not be mistaken for teacher-forced scores."""

import unittest
from append_rewrite.logprob_probe import analyze_echo


class ForcedScores(unittest.TestCase):
    def test_echo_with_only_generated_scores_does_not_pass(self):
        response = {
            "choices": [
                {
                    "text": "Q:\n4x",
                    "logprobs": {
                        "tokens": ["x"],
                        "token_logprobs": [-0.2],
                        "text_offset": [4],
                    },
                }
            ],
            "usage": {"prompt_tokens": 3},
        }
        self.assertFalse(
            analyze_echo(response, "Q:\n", "4")["teacher_forced_target_score_available"]
        )

    def test_input_candidate_probabilities_are_recognized(self):
        response = {
            "choices": [
                {
                    "text": "Q:\n9x",
                    "logprobs": {
                        "tokens": ["Q", ":\n", "9", "x"],
                        "token_logprobs": [None, -0.1, -8.0, -0.2],
                        "text_offset": [0, 1, 3, 4],
                    },
                }
            ],
            "usage": {"prompt_tokens": 3},
        }
        value = analyze_echo(response, "Q:\n", "9")
        self.assertTrue(value["teacher_forced_target_score_available"])
        self.assertEqual(value["target_sum_logprob"], -8.0)

    def test_echo_text_alone_does_not_prove_input_scores(self):
        response = {
            "choices": [
                {
                    "text": "Q:\n9x",
                    "logprobs": {
                        "tokens": ["9"],
                        "token_logprobs": [-8.0],
                        "text_offset": [3],
                    },
                }
            ],
            "usage": {"prompt_tokens": 3},
        }
        self.assertFalse(
            analyze_echo(response, "Q:\n", "9")["teacher_forced_target_score_available"]
        )

    def test_unknown_negative_offset_is_not_a_prompt_position(self):
        response = {
            "choices": [
                {
                    "text": "Q:\n9x",
                    "logprobs": {
                        "tokens": ["x"],
                        "token_logprobs": [-0.2],
                        "text_offset": [-1],
                    },
                }
            ],
            "usage": {"prompt_tokens": 3},
        }
        value = analyze_echo(response, "Q:\n", "9")
        self.assertEqual(value["input_prefix_logprobs"], [])
        self.assertFalse(value["teacher_forced_target_score_available"])
