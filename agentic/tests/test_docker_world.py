import unittest
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

from append_rewrite.terminus.docker_world import DockerWorld, judge_tests


class FrozenTests(unittest.TestCase):
    def test_commit_display_warning_does_not_poison_snapshot_identity(self):
        world = object.__new__(DockerWorld)
        world.sandbox_id = "owned-container"
        immutable = "sha256:" + "a" * 64
        with tempfile.TemporaryDirectory() as d, patch(
            "append_rewrite.terminus.docker_world.checked",
            side_effect=[b"Flag deprecated\n" + immutable.encode(),
                         json.dumps([{"Id": immutable}]).encode()],
        ):
            path = Path(d) / "snapshot.json"
            self.assertEqual(world.snapshot(path)["image_id"], immutable)
            self.assertEqual(json.loads(path.read_text())["image_id"], immutable)

    def test_all_targets_and_negative_canary_required(self):
        canary = SimpleNamespace(exit_code=1, stdout="1 failed")
        good = "tests/a.py::test_a PASSED [ 50%]\ntests/b.py::test_b PASSED [100%]\n"
        wanted = ["tests/a.py::test_a", "tests/b.py::test_b"]
        self.assertTrue(judge_tests(good, wanted, canary)[0])
        self.assertFalse(
            judge_tests(
                good.replace("test_b PASSED", "test_b SKIPPED"), wanted, canary
            )[0]
        )
        self.assertFalse(judge_tests(good.splitlines()[0], wanted, canary)[0])
        self.assertFalse(
            judge_tests(
                good, wanted, SimpleNamespace(exit_code=0, stdout="all passed")
            )[0]
        )
