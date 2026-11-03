import unittest
from append_rewrite.grading import parse_rewards
from append_rewrite.terminus.preflight_repair import repaired_spec


class ExactPreflight(unittest.TestCase):
    def test_original_reward_json_supported(self):
        self.assertEqual(parse_rewards({"reward.json": '{"reward":1}'}), 1)
        self.assertEqual(parse_rewards({"reward.txt": "0\n"}), 0)
        self.assertEqual(
            parse_rewards({"reward.txt": "1", "reward.json": '{"reward":1}'}), 1
        )
        self.assertIsNone(parse_rewards({}))

    def test_reward_conflict_invalid_and_nonfinite_hold(self):
        for channels in (
            {"reward.txt": "0", "reward.json": '{"reward":1}'},
            {"reward.json": '{"reward":true}'},
            {"reward.txt": "NaN"},
            {"reward.json": '{"reward":2}'},
        ):
            with self.assertRaises(ValueError):
                parse_rewards(channels)

    def test_legacy_overlay_preserves_image_geometry(self):
        original = {"identity": "x"}
        cad = repaired_spec(original, "legacy-cad")
        self.assertNotIn("/app/project", cad["restore_reset_paths"])
        self.assertEqual(
            repaired_spec(original, "legacy-science")["restore_reset_paths"],
            ["/app/project", "/app/submission"],
        )
        self.assertNotIn("restore_reset_paths", original)
        self.assertNotIn(
            "restore_reset_paths", repaired_spec(original, "foundry-chinook")
        )


class BoundControlReuse(unittest.TestCase):
    def test_changed_inputs_do_not_inherit_green(self):
        import tempfile
        from pathlib import Path
        import json
        from append_rewrite.collect import sha
        from append_rewrite.terminus.production import (
            control_binding,
            reuse_control_certificate,
        )

        spec = {
            "task_manifest": {"tests/test.sh": {"sha256": "a", "mode": 420}},
            "state_manifest": {},
            "template_id": "solver",
            "restore_reset_paths": ["/app/project"],
        }
        with tempfile.TemporaryDirectory() as root:
            p = Path(root) / "admission.json"
            p.write_text(
                json.dumps(
                    {
                        "passed": True,
                        "control_binding": control_binding(spec),
                        "legal": {"reward": 1, "exit_code": 0},
                        "initial": {"reward": 0, "exit_code": 0},
                    }
                )
            )
            spec["preflight_certificate"] = {"path": str(p), "sha256": sha(p)}
            self.assertTrue(reuse_control_certificate(spec)["passed"])
            changed = dict(spec, template_id="other-template")
            with self.assertRaises(ValueError):
                reuse_control_certificate(changed)


class PublishedFixtureBinding(unittest.TestCase):
    def test_only_batch_binding_changes(self):
        import tempfile
        import json
        from pathlib import Path
        from append_rewrite.collect import sha
        from append_rewrite.terminus.fixture_binding import event_binding

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            task = root / "task"
            (task / "tests/fixtures").mkdir(parents=True)
            (task / "instruction.md").write_text(
                "Preserve the published quota configuration."
            )
            (task / "tests/fixtures/netting-routes.json").write_text('{"quota":"old"}')
            wrapper = "batch='/tests/fixtures/netting-routes.json'\n"
            (task / "tests/grade.py").write_text(wrapper)
            published = root / "published.json"
            published.write_text('{"quota":"current"}')
            profile = root / "profile.json"
            profile.write_text(
                json.dumps(
                    {
                        "harbor_worker": {
                            "fresh_grader_argv": [
                                "python",
                                "grade.py",
                                "--batch",
                                str(published),
                            ]
                        }
                    }
                )
            )
            order = root / "order.json"
            order.write_text(
                json.dumps(
                    {"profile": {"uri": profile.as_uri(), "sha256": sha(profile)}}
                )
            )
            spec = {
                "source": {"kind": "foundry", "order_path": str(order)},
                "lane": "foundry-event",
                "task_path": str(task),
                "state_manifest": {
                    "work/netting-routes.json": {"sha256": sha(published)}
                },
            }
            output = root / "out"
            output.mkdir()
            updated = event_binding(spec, output)
            derived = Path(updated["task_path"])
            self.assertEqual((task / "tests/grade.py").read_text(), wrapper)
            self.assertEqual(
                (derived / "tests/fixtures/netting-routes.json").read_text(),
                '{"quota":"old"}',
            )
            self.assertEqual(
                (derived / "tests/published-netting-routes.json").read_bytes(),
                published.read_bytes(),
            )
            self.assertTrue(
                updated["verifier_revision"]["instruction_sha256_unchanged"]
            )
            self.assertFalse(updated["verifier_revision"]["scoring_rules_changed"])
            published.write_text('{"quota":"drifted"}')
            with self.assertRaises(ValueError):
                event_binding(spec, root / "other")
