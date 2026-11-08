"""The capacity handoff preserves inherited pools and mixed legacy ownership."""
from contextlib import ExitStack
import fcntl
from pathlib import Path
import runpy
import tempfile
import unittest

from append_rewrite.terminus.suffix_score import file_slot


class ScoreHandoffTests(unittest.TestCase):
    def test_eight_slots_coexist_with_four_legacy_owners(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as owners:
            for _ in range(4):
                owners.enter_context(file_slot(directory, 4))
            for _ in range(4):
                owners.enter_context(file_slot(directory, 8))
            for index in range(8):
                with (Path(directory) / f'score-{index}.lock').open('a+') as probe:
                    with self.assertRaises(BlockingIOError):
                        fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
        # The allocator's context exit, rather than a stale PID lease, releases.

    def test_explicit_capacity_preserves_inherited_pool(self):
        helper = runpy.run_path(str(Path(__file__).resolve().parents[1] /
            'experiments/cli-gym-expand-20261107/switch_teacher.py'))['scoring_environment']
        original = {'APPEND_REWRITE_SCORE_POOL': '/owned/pool',
                    'APPEND_REWRITE_SCORE_CAPACITY': '4',
                    'APPEND_REWRITE_SCORE_FIFO': '1'}
        self.assertEqual(helper(original, {}), original)
        self.assertEqual(helper(original, {'score_capacity': 8}),
                         {**original, 'APPEND_REWRITE_SCORE_CAPACITY': '8'})
        self.assertEqual(original['APPEND_REWRITE_SCORE_CAPACITY'], '4')
        for value in [0, -1, True, '8', None]:
            with self.assertRaises(ValueError):
                helper(original, {'score_capacity': value})
