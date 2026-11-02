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


class UnitGates(unittest.IsolatedAsyncioTestCase):
    async def test_teacher_error_prevents_student_dispatch(self):
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        from append_rewrite.terminus import unit

        with tempfile.TemporaryDirectory() as temp:
            args = SimpleNamespace(
                **{
                    k: Path(temp) / k
                    for k in (
                        "output",
                        "source_protocol",
                        "teacher_config",
                        "sandbox_credentials",
                        "runtime_assets",
                        "tokenizer",
                        "fleet_config",
                    )
                }
            )
            with (
                patch.object(
                    unit.owned_mvp,
                    "run",
                    AsyncMock(side_effect=RuntimeError("teacher stopped")),
                ),
                patch.object(unit.episode, "run", AsyncMock()) as student,
            ):
                with self.assertRaises(RuntimeError):
                    await unit.run(args)
                student.assert_not_awaited()
            self.assertTrue((args.output / "status.json").exists())

    async def test_new_unit_cannot_reuse_existing_output(self):
        import tempfile
        from pathlib import Path
        from types import SimpleNamespace
        from unittest.mock import AsyncMock, patch
        from append_rewrite.terminus import unit

        with tempfile.TemporaryDirectory() as temp:
            with patch.object(unit.owned_mvp, "run", AsyncMock()) as teacher:
                with self.assertRaises(FileExistsError):
                    await unit.run(SimpleNamespace(output=Path(temp)))
                teacher.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
