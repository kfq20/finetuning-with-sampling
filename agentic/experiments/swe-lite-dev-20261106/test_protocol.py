import importlib.util
from pathlib import Path
import unittest


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, Path(__file__).parent / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class ProtocolTest(unittest.TestCase):
    def test_selection_uses_only_repo_and_identifier(self):
        run = load('pilot', 'run.py')
        rows = [{'repo': repo, 'instance_id': repo + str(i), 'patch': 'irrelevant'}
                for repo in run.REPOS for i in range(3)]
        a = run.selected(rows)
        b = run.selected(list(reversed(rows)))
        self.assertEqual([r['instance_id'] for r in a], [r['instance_id'] for r in b])
        self.assertEqual(len(a), 6)

    def test_missing_tests_are_infrastructure_unknown(self):
        grade = load('grade', 'grade.py')
        with self.assertRaises(RuntimeError):
            grade.classify({'a': 'PASSED'}, ['a', 'b'])

    def test_partial_does_not_pass(self):
        grade = load('grade', 'grade.py')
        self.assertEqual(grade.classify({'a': 'PASSED', 'b': 'FAILED'}, ['a', 'b']), 0)
        self.assertEqual(grade.classify({'a': 'PASSED', 'b': 'PASSED'}, ['a', 'b']), 1)

    def test_canonical_id_survives_trial_name_truncation(self):
        run = load('pilot', 'run.py')
        import tempfile, json
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for i in range(6):
                task = root / 'prepared-tasks' / ('long-task-name-' + str(i))
                task.mkdir(parents=True)
                (task / 'instruction.md').write_text('Task')
                for agent, score in [('nop', 0), ('oracle', 1)]:
                    trial = root / 'controls' / ('control-' + agent) / ('truncated__' + str(i))
                    trial.mkdir(parents=True)
                    (trial / 'result.json').write_text(json.dumps({
                        'task_name': task.name, 'finished_at': 'now', 'exception_info': None,
                        'verifier_result': {'rewards': {'reward': score}}}))
            run.verify_controls(root)
            self.assertEqual(len(json.loads((root / 'admission.json').read_text())['tasks']), 6)
            damaged = root / 'controls/control-oracle/truncated__0/result.json'
            row = json.loads(damaged.read_text())
            row['verifier_result']['rewards']['reward'] = 0
            damaged.write_text(json.dumps(row))
            run.verify_controls(root)
            receipt = json.loads((root / 'admission.json').read_text())
            self.assertEqual(len(receipt['tasks']), 5)
            self.assertEqual(len(receipt['held_tasks']), 1)
            self.assertEqual(receipt['replacement_tasks'], 0)

    def test_raw_reward_does_not_override_exception(self):
        run = load('pilot', 'run.py')
        r = {'finished_at': 'now', 'exception_info': {'exception_type': 'AgentTimeoutError'},
             'verifier_result': {'rewards': {'reward': 0}}}
        self.assertFalse(run.valid(r))
        r['exception_info'] = None
        self.assertTrue(run.valid(r))


if __name__ == '__main__':
    unittest.main()
