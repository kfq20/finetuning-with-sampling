from datetime import datetime, timezone
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('eval_archive', Path(__file__).parent / 'archive_evaluations.py')
worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)


class TerminalEvalScopeTest(unittest.TestCase):
    def test_closed_partial_stream_eligible_active_recent_open_excluded(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); now = __import__('time').time()
            for name, closed, age in [('old', True, 3600), ('active', False, 3600), ('recent', True, 30), ('opened', True, 3600)]:
                trial = root / 'jobs/job' / name; generation = trial / 'native-generation/turn-0001'; generation.mkdir(parents=True)
                (trial / 'result.json').write_text(json.dumps({'task_name': name, 'finished_at':
                    datetime.fromtimestamp(now-age, timezone.utc).isoformat() if closed else None}))
                p = generation / 'wire.jsonl'; p.write_bytes(b'x' * 150000)
                __import__('os').utime(p, (now-3600, now-3600))
            opened = str(root / 'jobs/job/opened/native-generation/turn-0001/wire.jsonl')
            items, protected = worker.candidates([root], {opened}, lambda p:'hash', now)
            self.assertEqual(len(items), 1)
            self.assertIn('/old/', '/' + items[0]['relative'])
            self.assertFalse((root / 'jobs/job/old/native-generation/turn-0001/decision.json').exists())
            self.assertTrue(protected)


if __name__ == '__main__':
    unittest.main()
