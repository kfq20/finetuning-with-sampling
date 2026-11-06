import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('timeout4x', Path(__file__).with_name('run.py'))
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


class RetryProtocol(unittest.TestCase):
    def test_only_agent_deadline_changes_and_original_is_untouched(self):
        original = {'agent': {'timeout_sec': 900, 'other': 'retained'},
                    'verifier': {'timeout_sec': 1800},
                    'environment': {'build_timeout_sec': 600}}
        saved = copy.deepcopy(original)
        changed = run.extended(original)
        self.assertEqual(changed['agent']['timeout_sec'], 3600)
        changed['agent']['timeout_sec'] = 900
        self.assertEqual(changed, saved)
        self.assertEqual(original, saved)

    def test_only_agent_timeouts_are_eligible(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            for i in range(89):
                path = root / 'jobs/old' / f'task-{i}__id' / 'result.json'
                path.parent.mkdir(parents=True)
                exception = {'exception_type': 'AgentTimeoutError' if i == 0 else 'ReadError'} if i < 2 else None
                path.write_text(json.dumps({'finished_at': '2026-11-06T00:00:00Z',
                                            'exception_info': exception}))
            selected = run.timeout_selection(root)
            self.assertEqual(list(selected), ['task-0'])
            self.assertEqual(selected['task-0']['result_sha256'],
                             run.sha(Path(selected['task-0']['result_path'])))

    def test_incomplete_original_cohort_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(AssertionError):
                run.timeout_selection(Path(folder))

    def test_timeout_diagnostic_zero_does_not_become_valid_model_zero(self):
        row = {'finished_at': '2026-11-06T00:00:00Z',
               'exception_info': {'exception_type': 'AgentTimeoutError'},
               'verifier_result': {'rewards': {'reward': 0}}}
        self.assertFalse(run.valid(row))
        row['exception_info'] = None
        self.assertTrue(run.valid(row))
        row['verifier_result']['rewards']['reward'] = float('nan')
        self.assertFalse(run.valid(row))
