import unittest
from types import SimpleNamespace

from append_rewrite.terminus.docker_world import judge_tests


class FrozenTests(unittest.TestCase):
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
