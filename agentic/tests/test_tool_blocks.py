"""Boundary, state divergence, observation provenance and loss-mask regressions."""

from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from append_rewrite.tool_blocks.trace import Trace, BoundaryError, digest
from append_rewrite.tool_blocks.state import (
    DirectoryRuntime,
    DirectorySession,
    FILE_SCOPE,
)
from append_rewrite.tool_blocks.engine import (
    Checkpoint,
    Score,
    Verdict,
    evaluate_action,
    generate_candidate,
    select_candidate,
)
from append_rewrite.tool_blocks.sft import window_preview
from append_rewrite.tool_blocks.cli import call, demo


def result(key, value="observed", error=False):
    return {
        "role": "user",
        "content": [
            {
                "type": "tool_result",
                "tool_use_id": key,
                "content": value,
                "is_error": error,
            }
        ],
    }


class BoundaryTests(unittest.TestCase):
    def test_parallel_batch_waits_for_every_observation_and_preserves_order(self):
        messages = [
            {"role": "user", "content": "Inspect both"},
            {"role": "assistant", "content": "Inspecting"},
            *call("a", "Read", file_path="a"),
            *call("b", "Read", file_path="b"),
            result("b", "B"),
            result("a", "A"),
            {"role": "assistant", "content": "Done"},
        ]
        trace = Trace.create(messages)
        blocks = trace.interactions()
        self.assertEqual(
            (blocks[0].start, blocks[0].end, blocks[0].call_ids), (1, 6, ("a", "b"))
        )
        self.assertEqual(blocks[1].kind, "assistant_reply")
        with self.assertRaises(BoundaryError):
            trace.prefix(5)
        with self.assertRaises(BoundaryError):
            trace.prefix(2)
        self.assertEqual(len(trace.prefix(6).messages), 6)
        self.assertEqual(trace.messages[4]["content"][0]["content"], "B")

    def test_missing_foreign_duplicate_and_early_results_are_rejected(self):
        cases = [
            call("a", "Read", file_path="a"),
            call("a", "Read", file_path="a") + [result("b")],
            [result("a")],
            call("a", "Read", file_path="a") + [result("a"), result("a")],
            call("a", "Read", file_path="a")
            + [{"role": "assistant", "content": "advance"}],
        ]
        for messages in cases:
            with self.subTest(messages=messages), self.assertRaises(BoundaryError):
                Trace.create(messages)

    def test_private_and_fragmented_tool_inputs_are_not_silently_accepted(self):
        for content in [
            [{"type": "thinking", "thinking": "private"}],
            [{"type": "tool_use", "id": "a", "name": "Bash", "input": '{"command":'}],
        ]:
            with self.subTest(content=content), self.assertRaises(BoundaryError):
                Trace.create([{"role": "assistant", "content": content}])

    def test_history_is_immutable_to_caller_mutations(self):
        messages = [{"role": "user", "content": "original"}]
        trace = Trace.create(messages)
        messages[0]["content"] = "changed"
        observed = trace.messages
        observed[0]["content"] = "also changed"
        self.assertEqual(trace.messages[0]["content"], "original")


class FixedScorer:
    def __init__(self, mean=-1):
        self.mean, self.calls = mean, []

    def score(self, history, action):
        self.calls.append((history, action))
        return Score(
            "fixture-student",
            "fixture-scoring",
            Trace.create(history).sha256,
            digest(action),
            self.mean * 10,
            10,
            True,
        )


class Expected:
    def check(self, session, trace):
        path = session.root / "result.txt"
        return Verdict(
            path.exists() and path.read_text() == "correct",
            "fixture-exact-result",
            "checked",
        )


class BranchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.project = root / "project"
        self.project.mkdir(mode=0o700)
        (self.project / "seed.txt").write_text("initial")
        (self.project / "seed.txt").chmod(0o750)
        (self.project / "empty").mkdir(mode=0o700)
        self.runtime = DirectoryRuntime(root / "runtime")
        self.trace = Trace.create(
            [{"role": "user", "content": "Write the result, then inspect it"}]
        )
        self.parent = Checkpoint.capture(
            self.trace,
            DirectorySession(self.project, self.runtime.store, "root"),
            (FILE_SCOPE,),
        )

    def tearDown(self):
        self.tmp.cleanup()

    def evaluate(self, text, key="write", scorer=None, runtime=None):
        return evaluate_action(
            self.parent,
            call(key, "Write", file_path="result.txt", content=text),
            runtime or self.runtime,
            scorer or FixedScorer(),
            Expected(),
        )

    def test_changed_actions_get_different_real_observations_in_isolated_branches(self):
        a = self.evaluate("wrong", "a")
        b = self.evaluate("correct", "b")
        for candidate, expected in [(a, "wrong"), (b, "correct")]:
            child = evaluate_action(
                candidate.child,
                call("own-read", "Read", file_path="result.txt"),
                self.runtime,
                FixedScorer(),
                Expected(),
            )
            self.assertEqual(child.execution.results[0]["content"], expected)
            self.assertEqual(
                child.child.parent_checkpoint_id, candidate.child.checkpoint_id
            )
        self.assertFalse((self.project / "result.txt").exists())
        self.assertNotEqual(a.child.state.sha256, b.child.state.sha256)
        self.assertFalse(a.eligible)
        self.assertTrue(b.eligible)

    def test_snapshot_restores_permissions_empty_directories_and_rejects_missing_scopes(
        self,
    ):
        restored = self.runtime.fork(self.parent.state, "probe")
        self.assertEqual((restored.root / "seed.txt").stat().st_mode & 0o777, 0o750)
        self.assertTrue((restored.root / "empty").is_dir())
        with self.assertRaises(BoundaryError):
            replace(self.parent, required_scopes=(FILE_SCOPE, "database")).validate()

    def test_high_likelihood_semantically_wrong_candidate_cannot_win(self):
        wrong = self.evaluate("wrong", "wrong", FixedScorer(-0.01))
        correct = self.evaluate("correct", "correct", FixedScorer(-2))
        self.assertIs(select_candidate([wrong, correct]), correct)

    def test_foreign_receipt_is_hold_and_not_a_semantic_zero(self):
        base = self.runtime

        class ForeignRuntime:
            def fork(self, state, branch_id):
                session = base.fork(state, branch_id)
                execute = session.execute
                session.execute = lambda calls: replace(
                    execute(calls), branch_id="copied-expert-run"
                )
                return session

        outcome = self.evaluate("correct", runtime=ForeignRuntime())
        self.assertEqual(outcome.status, "execution_hold")
        self.assertFalse(outcome.eligible)
        self.assertIsNone(outcome.verdict)

    def test_proposal_cannot_supply_expert_observations(self):
        outcome = evaluate_action(
            self.parent,
            call("a", "Write", file_path="result.txt", content="correct")
            + [result("a", "teacher success")],
            self.runtime,
            FixedScorer(),
            Expected(),
        )
        self.assertEqual(outcome.status, "execution_hold")
        self.assertFalse(any((self.runtime.root / "branches").iterdir()))

    def test_same_prefix_but_wrong_actual_fork_state_is_rejected(self):
        base = self.runtime

        class DirtyRuntime:
            def fork(self, state, branch_id):
                session = base.fork(state, branch_id)
                (session.root / "unexpected.txt").write_text("drift")
                return session

        outcome = self.evaluate("correct", runtime=DirtyRuntime())
        self.assertEqual(outcome.status, "execution_hold")
        self.assertIn("exact pinned state", outcome.error_code)

    def test_reference_is_generator_only_and_sft_masks_old_history_and_observations(
        self,
    ):
        parent_read = evaluate_action(
            self.parent,
            call("read-seed", "Read", file_path="seed.txt"),
            self.runtime,
            FixedScorer(),
            Expected(),
        ).child
        observed = []

        class Generator:
            def propose(self, history, reference):
                observed.append(reference)
                self_reference = "<expert_reference>fixture answer</expert_reference>"
                assert reference == self_reference and self_reference not in json.dumps(
                    history
                )
                return call(
                    "new-write", "Write", file_path="result.txt", content="correct"
                )

        scorer = FixedScorer()
        candidate = generate_candidate(
            parent_read,
            Generator(),
            self.runtime,
            scorer,
            Expected(),
            "<expert_reference>fixture answer</expert_reference>",
        )
        self.assertTrue(candidate.eligible)
        self.assertEqual(len(observed), 1)
        self.assertNotIn("expert_reference", json.dumps(scorer.calls))
        self.assertNotIn("new-write", json.dumps(scorer.calls[0][0]))
        preview = window_preview(candidate.child.trace, 1, 2)
        self.assertEqual(
            preview["assistant_loss_by_message"], [False, False, False, True, False]
        )
        self.assertFalse(preview["training_admitted"])

    def test_scorer_using_reference_or_other_history_cannot_be_ranked(self):
        class WrongCondition(FixedScorer):
            def score(self, history, action):
                return replace(
                    super().score(history, action),
                    history_sha256="different-conditioned-history",
                )

        outcome = self.evaluate("correct", scorer=WrongCondition())
        self.assertEqual(outcome.status, "execution_hold")

    def test_raw_reference_in_history_is_not_silently_exported(self):
        trace = Trace.create(
            [
                {
                    "role": "user",
                    "content": "<expert_reference>answer</expert_reference>",
                },
                {"role": "assistant", "content": "done"},
            ]
        )
        with self.assertRaises(BoundaryError):
            window_preview(trace, 0, 1)

    def test_prior_tool_id_cannot_be_replayed_and_different_checkpoints_cannot_be_ranked(
        self,
    ):
        a = self.evaluate("correct", "same")
        repeated = evaluate_action(
            a.child,
            call("same", "Read", file_path="result.txt"),
            self.runtime,
            FixedScorer(),
            Expected(),
        )
        self.assertEqual(repeated.status, "execution_hold")
        b = evaluate_action(
            a.child,
            call("next", "Read", file_path="result.txt"),
            self.runtime,
            FixedScorer(),
            Expected(),
        )
        with self.assertRaises(BoundaryError):
            select_candidate([a, b])

    def test_checkpoint_roundtrip_and_lineage_tampering(self):
        candidate = self.evaluate("correct")
        restored = Checkpoint.from_record(
            json.loads(json.dumps(candidate.child.record()))
        )
        self.assertEqual(restored.checkpoint_id, candidate.child.checkpoint_id)
        self.assertEqual(restored.trace.messages, candidate.child.trace.messages)
        edited = candidate.child.record()
        edited["parent_checkpoint_id"] = "wrong-parent"
        with self.assertRaises(BoundaryError):
            Checkpoint.from_record(edited)

    def test_parallel_actual_reads_share_one_block_and_return_own_values(self):
        calls = call("one", "Read", file_path="seed.txt") + call(
            "two", "Read", file_path="seed.txt"
        )
        candidate = evaluate_action(
            self.parent, calls, self.runtime, FixedScorer(), Expected()
        )
        self.assertEqual(candidate.status, "evaluated")
        self.assertEqual(
            candidate.child.trace.interactions()[-1].call_ids, ("one", "two")
        )
        self.assertEqual(
            [r["content"] for r in candidate.execution.results], ["initial", "initial"]
        )

    def test_tool_failure_is_real_observation_not_infrastructure_failure(self):
        candidate = evaluate_action(
            self.parent,
            call("missing", "Read", file_path="missing.txt"),
            self.runtime,
            FixedScorer(),
            Expected(),
        )
        self.assertEqual(candidate.status, "evaluated")
        self.assertTrue(candidate.execution.results[0]["is_error"])
        self.assertFalse(candidate.eligible)

    def test_cleanup_failure_is_hold_not_accepted_branch(self):
        base = self.runtime

        class BrokenCleanup:
            def fork(self, state, branch_id):
                session = base.fork(state, branch_id)

                def fail_close():
                    raise OSError()

                session.close = fail_close
                return session

        candidate = self.evaluate("correct", runtime=BrokenCleanup())
        self.assertEqual(candidate.status, "execution_hold")
        self.assertTrue(candidate.error_type.startswith("CleanupError"))

    def test_runtime_identity_cannot_change_during_a_candidate(self):
        base = self.runtime

        class SwitchingRuntime:
            def fork(self, state, branch_id):
                session = base.fork(state, branch_id)
                snapshot, execute = session.snapshot, session.execute
                switched = [False]

                def current_state():
                    value = snapshot()
                    return (
                        replace(value, environment_id="another-runtime")
                        if switched[0]
                        else value
                    )

                def run_calls(calls):
                    value = execute(calls)
                    switched[0] = True
                    return replace(value, after=current_state())

                session.snapshot = current_state
                session.execute = run_calls
                return session

        candidate = self.evaluate("correct", runtime=SwitchingRuntime())
        self.assertEqual(candidate.status, "execution_hold")
        self.assertIn("runtime environment identity", candidate.error_code)

    def test_corrupted_snapshot_blob_prevents_execution(self):
        blob = next((self.runtime.store.root / "blobs").iterdir())
        blob.write_bytes(b"corruption")
        outcome = self.evaluate("correct")
        self.assertEqual(outcome.status, "execution_hold")
        self.assertFalse((self.project / "result.txt").exists())

    def test_terminal_reply_has_no_fabricated_tool_result_and_needs_a_new_user_to_continue(
        self,
    ):
        ready = self.evaluate("correct")
        final = evaluate_action(
            ready.child,
            [{"role": "assistant", "content": "Done"}],
            self.runtime,
            FixedScorer(),
            Expected(),
        )
        self.assertTrue(final.eligible)
        self.assertIsNone(final.execution)
        self.assertEqual(final.child.trace.interactions()[-1].kind, "assistant_reply")
        repeated = evaluate_action(
            final.child,
            call("extra", "Read", file_path="result.txt"),
            self.runtime,
            FixedScorer(),
            Expected(),
        )
        self.assertEqual(repeated.status, "execution_hold")

    def test_generator_failure_does_not_fork_or_retry(self):
        class FailedGenerator:
            def propose(self, history, reference):
                raise TimeoutError()

        outcome = generate_candidate(
            self.parent, FailedGenerator(), self.runtime, FixedScorer(), Expected()
        )
        self.assertEqual(outcome.status, "generation_hold")
        self.assertFalse(any((self.runtime.root / "branches").iterdir()))

    def test_path_escape_never_executes(self):
        outcome = evaluate_action(
            self.parent,
            call("escape", "Write", file_path="../outside", content="oops"),
            self.runtime,
            FixedScorer(),
            Expected(),
        )
        self.assertEqual(outcome.status, "execution_hold")
        self.assertFalse((self.runtime.root / "branches/outside").exists())

    def test_executable_demo_rejects_wrong_branch_and_keeps_preview_unadmitted(self):
        output = Path(self.tmp.name) / "demo"
        summary = demo(output)
        self.assertTrue(summary["wrong_candidate_had_higher_fixture_score"])
        self.assertTrue(summary["wrong_candidate_rejected"])
        self.assertTrue(summary["parent_unchanged"])
        self.assertEqual(summary["own_read_observation"], "42\n")
        preview = json.loads((output / "sft-preview.json").read_text())
        self.assertEqual(
            preview["assistant_loss_by_message"], [False, True, False, True, False]
        )
        self.assertEqual(preview["target_interactions"], 2)
