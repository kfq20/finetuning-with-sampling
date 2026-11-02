"""Full-episode rewrite invariants, independent of actual paid inference."""

import unittest
from append_rewrite.terminus.episode import aggregate_scores, generation_history
from append_rewrite.terminus.protocol import public_messages


class EpisodeProtocol(unittest.TestCase):
    def test_full_reference_only_privileged_and_prefix_not_mutated(self):
        history = [
            {"role": "user", "content": "task"},
            {"role": "assistant", "content": "student first action"},
            {"role": "user", "content": "actual new terminal result"},
        ]
        reference = "expert action1; expert obs1; expert action2; expert final obs"
        wire = generation_history(history, reference)
        self.assertIn(reference, wire[0]["content"])
        self.assertEqual(wire[1:], history[1:])
        self.assertEqual(history[0]["content"], "task")
        self.assertEqual(public_messages(history), history)
        with self.assertRaises(ValueError):
            public_messages(wire)

    def test_no_reference_same_public_history(self):
        history = [{"role": "user", "content": "task"}]
        self.assertEqual(generation_history(history, None), history)

    def test_episode_ranking_weights_all_action_tokens(self):
        result = aggregate_scores(
            [
                {"token_count": 1, "sum_logprob": -1},
                {"token_count": 9, "sum_logprob": -18},
            ]
        )
        self.assertAlmostEqual(result["mean_logprob"], -1.9)
        self.assertEqual(result["action_tokens"], 10)
        self.assertFalse(result["observations_scored"])
        self.assertFalse(result["extra_expert_reference_in_score"])

    def test_empty_episode_not_admitted(self):
        with self.assertRaises(ValueError):
            aggregate_scores([])


if __name__ == "__main__":
    unittest.main()
