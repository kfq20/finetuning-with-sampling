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
