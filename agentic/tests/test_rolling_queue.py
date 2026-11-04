import importlib.util
from pathlib import Path
import tempfile
import unittest

p=Path(__file__).resolve().parents[1]/'experiments/cli-gym-scale-20261104/rolling.py'
spec=importlib.util.spec_from_file_location('rolling_campaign',p)
rolling=importlib.util.module_from_spec(spec);spec.loader.exec_module(rolling)


class RollingTests(unittest.TestCase):
    def test_refill_is_independent_of_unfinished_previous_batch(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'units/old_tail').mkdir(parents=True)
            plan={'units':[{'unit_id':'old_tail','spec_path':'old'}]}
            rolling.merge(plan,[{'unit_id':f'new{i}','spec_path':str(i)} for i in range(8)])
            self.assertEqual(rolling.pending(plan,root),8)
            (root/'units/new0').mkdir()
            self.assertEqual(rolling.pending(plan,root),7)
            self.assertTrue((root/'units/old_tail').exists())

    def test_republication_deduplicates_and_rejects_drift(self):
        plan={'units':[]};row={'unit_id':'one','spec_path':'frozen'}
        rolling.merge(plan,[row]);rolling.merge(plan,[row]);self.assertEqual(len(plan['units']),1)
        with self.assertRaises(ValueError):rolling.merge(plan,[{'unit_id':'one','spec_path':'changed'}])
