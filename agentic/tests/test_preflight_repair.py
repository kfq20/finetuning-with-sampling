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
