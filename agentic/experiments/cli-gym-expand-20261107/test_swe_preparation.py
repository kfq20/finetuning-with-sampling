"""Source preparation must parallelize without replaying completed/failed rows."""
import json
from pathlib import Path
import runpy
import tempfile
import threading
from types import SimpleNamespace
import unittest
from unittest.mock import patch


class SWEPreparationTests(unittest.TestCase):
    def test_parallel_preparation_and_no_repeat_of_held_or_completed(self):
        module = runpy.run_path(str(Path(__file__).with_name('prepare_swegym.py')))
        main, row_sha = module['main'], module['row_sha']
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            output = root / 'prepared'
            rows = [{'instance_id': name, 'repo': 'pydantic/pydantic',
                     'FAIL_TO_PASS': ['test.py::x'], 'PASS_TO_PASS': []} for name in ['a', 'b']]
            (root / 'rows.json').write_text(json.dumps(rows))
            (root / 'scope.json').write_text(json.dumps({'revision': 'frozen',
                'tasks': {r['instance_id']: row_sha(r) for r in rows}}))
            (root / 'acquisition-plan.json').write_text('{"units":[]}')
            (root / 'acquisition-progress.json').write_text('{"valid_by_source":{"swe-gym":0}}')
            args = SimpleNamespace(root=root, rows=root/'rows.json', scope=root/'scope.json',
                output=output, assets=root/'assets', workers=2, episode_timeout_sec=6000)
            barrier, lock = threading.Barrier(2), threading.Lock()
            state = {'active': 0, 'maximum': 0, 'calls': []}
            def prepare(row, revision, destination, assets, *, episode_timeout_sec, repair_pytest_snail=False):
                self.assertEqual(episode_timeout_sec, 6000)
                (destination / row['instance_id']).mkdir()
                with lock:
                    state['active'] += 1
                    state['maximum'] = max(state['maximum'], state['active'])
                    state['calls'].append(row['instance_id'])
                barrier.wait(timeout=3)
                with lock:
                    state['active'] -= 1
                if row['instance_id'] == 'b':
                    raise ValueError('Unpaid verifier hold')
                return {'unit_id': 'swegym-a', 'lane': 'shared', 'spec_path': 'frozen-spec'}
            with patch.dict(main.__globals__, prepare=prepare), patch('shutil.disk_usage',
                    return_value=SimpleNamespace(free=100 * 1024**3)):
                main(args)
                main(args)
            self.assertEqual(state['maximum'], 2)
            self.assertCountEqual(state['calls'], ['a', 'b'])
            final = json.loads((output / 'complete.json').read_text())
            self.assertEqual(final['ready'], 1)
            self.assertEqual(len(final['held']), 1)

    def test_bad_capacity_fails_before_materializing_rows(self):
        main = runpy.run_path(str(Path(__file__).with_name('prepare_swegym.py')))['main']
        with self.assertRaises(ValueError):
            main(SimpleNamespace(workers=0, episode_timeout_sec=6000))


if __name__ == '__main__':
    unittest.main()
