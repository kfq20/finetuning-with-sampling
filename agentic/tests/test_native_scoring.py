import unittest
from append_rewrite.terminus.scoring import RenderedCandidate, analyze_native


class NativeInputScores(unittest.TestCase):
    def rendered(self):
        return RenderedCandidate(
            "prefix answer",
            (1, 2, 3, 4),
            2,
            "a" * 64,
            "b" * 64,
            "pinned-tokenizer",
            "c" * 64,
        )

    def response(self):
        return {
            "meta_info": {
                "id": "fixture",
                "prompt_tokens": 4,
                "completion_tokens": 0,
                "input_token_logprobs": [
                    [None, 1, "p"],
                    [-10, 2, "refix"],
                    [-0.2, 3, " an"],
                    [-0.3, 4, "swer"],
                ],
            }
        }

    def test_scores_only_exact_candidate_positions(self):
        v = analyze_native(self.response(), self.rendered())
        self.assertAlmostEqual(v["sum_logprob"], -0.5)
        self.assertEqual(v["token_count"], 2)
        self.assertEqual(v["request_id"], "fixture")
        self.assertFalse(v["generation_template_alignment_verified"])

    def test_null_inside_candidate_rejected(self):
        r = self.response()
        r["meta_info"]["input_token_logprobs"][2][0] = None
        with self.assertRaises(ValueError):
            analyze_native(r, self.rendered())

    def test_wrong_input_ids_rejected(self):
        r = self.response()
        r["meta_info"]["input_token_logprobs"][2][1] = 99
        with self.assertRaises(ValueError):
            analyze_native(r, self.rendered())

    def test_partial_coverage_and_generated_tokens_rejected(self):
        for key, value in (("prompt_tokens", 3), ("completion_tokens", 1)):
            r = self.response()
            r["meta_info"][key] = value
            with self.assertRaises(ValueError):
                analyze_native(r, self.rendered())

    def test_nonfinite_and_positive_scores_rejected(self):
        for value in (float("nan"), float("inf"), 0.1, True):
            r = self.response()
            r["meta_info"]["input_token_logprobs"][3][0] = value
            with self.assertRaises(ValueError):
                analyze_native(r, self.rendered())
