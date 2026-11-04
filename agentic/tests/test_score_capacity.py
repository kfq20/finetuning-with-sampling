import unittest
from unittest.mock import patch
from append_rewrite.terminus.suffix_score import score_slot


class ScoreCapacityTests(unittest.TestCase):
    def test_explicit_capacity_and_legacy_default(self):
        for setting,expected in [({},2),({'APPEND_REWRITE_SCORE_CAPACITY':'4'},4)]:
            with patch.dict('os.environ',setting,clear=True),patch('append_rewrite.terminus.suffix_score.file_slot') as slot:
                score_slot();slot.assert_called_once_with(None,expected)

    def test_nonpositive_capacity_rejected(self):
        with patch.dict('os.environ',{'APPEND_REWRITE_SCORE_CAPACITY':'0'},clear=True):
            with self.assertRaises(ValueError):score_slot()
