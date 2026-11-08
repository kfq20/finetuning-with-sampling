import unittest
from unittest.mock import patch
from append_rewrite.terminus.suffix_score import (
    NativeFullStreamClient, NativeSuffixStreamClient, score_slot,
)


class ScoreCapacityTests(unittest.TestCase):
    def test_candidate_slice_is_explicit_and_keeps_exact_rendered_input(self):
        rendered = object()
        for config, full in [({}, True), ({'candidate_logprob_slice': False}, True),
                             ({'candidate_logprob_slice': True}, False)]:
            client = object.__new__(NativeFullStreamClient)
            client.config = config
            with patch.object(NativeSuffixStreamClient, 'score', return_value={'ok': True}) as score:
                self.assertEqual(client.score(rendered, journal='fixture', timeout=19), {'ok': True})
                score.assert_called_once_with(rendered, journal='fixture', timeout=19,
                                              full_input=full)

    def test_candidate_slice_rejects_ambiguous_config(self):
        for setting in ['false', 0, None]:
            client = object.__new__(NativeFullStreamClient)
            client.config = {'candidate_logprob_slice': setting}
            with patch.object(NativeSuffixStreamClient, 'score') as score:
                with self.assertRaises(ValueError):
                    client.score(None, journal='fixture')
                score.assert_not_called()

    def test_explicit_capacity_and_legacy_default(self):
        for setting,expected in [({},2),({'APPEND_REWRITE_SCORE_CAPACITY':'4'},4)]:
            with patch.dict('os.environ',setting,clear=True),patch('append_rewrite.terminus.suffix_score.file_slot') as slot:
                score_slot();slot.assert_called_once_with(None,expected)

    def test_nonpositive_capacity_rejected(self):
        with patch.dict('os.environ',{'APPEND_REWRITE_SCORE_CAPACITY':'0'},clear=True):
            with self.assertRaises(ValueError):score_slot()
