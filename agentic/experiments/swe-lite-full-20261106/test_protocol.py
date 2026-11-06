import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('full_swe', Path(__file__).parent / 'run.py')
run = importlib.util.module_from_spec(spec); spec.loader.exec_module(run)


class FullProtocolTest(unittest.TestCase):
    def test_repository_round_robin_does_not_select_by_outcome(self):
        rows = [{'repo': repo, 'instance_id': repo + str(i)} for repo in ('a', 'b') for i in range(3)]
        self.assertEqual([x['instance_id'] for x in run.ordered(rows)], ['a0', 'b0', 'a1', 'b1', 'a2', 'b2'])
        self.assertEqual(run.ordered(rows), run.ordered(list(reversed(rows))))

    def test_errors_are_not_valid_zeros(self):
        row = {'finished_at': 'now', 'verifier_result': {'rewards': {'reward': 0}}}
        self.assertTrue(run.valid(row))
        row['exception_info'] = {'exception_type': 'AgentTimeoutError'}
        self.assertFalse(run.valid(row))
        row['exception_info'] = None
        row['verifier_result']['rewards']['reward'] = .99
        self.assertFalse(run.valid(row))

    def test_failed_gate_does_not_block_other_task_or_replay(self):
        class Fake(run.Campaign):
            def __init__(self, root):
                self.root = root; self.plan = {'split': 'test', 'cohort': 2}
            def check_deployment(self, arm):
                pass
            def gate(self, row):
                if row['instance_id'] == 'a':
                    raise AssertionError('Failed original/gold control')
                return {'task': row['instance_id']}
            def sample(self, arm, receipt):
                run.dump(self.root / arm / receipt['task'] / 'receipt.json', {'valid': True, 'resolved': 1})
                return {'valid': True}
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            run.dump(root / 'source-files.json', {})
            run.dump(root / 'source/rows.json', [{'repo': 'x', 'instance_id': 'a'}, {'repo': 'x', 'instance_id': 'b'}])
            Fake(root).run()
            summary = json.loads((root / 'finished.json').read_text())
            self.assertEqual(summary['preflight_held'], 1)
            self.assertEqual([summary['arms'][a]['resolved'] for a in run.ARMS], [1, 1, 1])
            with self.assertRaises(AssertionError):
                Fake(root).run()


if __name__ == '__main__':
    unittest.main()
