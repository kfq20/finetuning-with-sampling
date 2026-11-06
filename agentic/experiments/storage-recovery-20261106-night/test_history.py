import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('history_archive', Path(__file__).parent / 'archive_history.py')
worker = importlib.util.module_from_spec(spec); spec.loader.exec_module(worker)
PRIMITIVE = Path(__file__).parent.parent / 'swe-lite-full-20261106/archive_closed.py'


class HistoryScopeTest(unittest.TestCase):
    def test_only_large_unique_api_journals_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'closed'; audit = Path(tmp) / 'audit'
            audit.mkdir(); shutil.copyfile(PRIMITIVE, audit / 'archive_closed.py')
            student = root / 'run/units/sample/student'; student.mkdir(parents=True)
            (root / 'complete.json').write_text('{"finished_at":1}')
            (student / 'receipt.json').write_text('{"normal_completed":true}')
            generation = student / 'generation'; generation.mkdir()
            body = b'{"input_ids":[1,2,3]}\n' * 8000
            (generation / 'request.json').write_bytes(body)
            (generation / 'response.json').write_bytes(body)
            (student / 'trajectory.json').write_bytes(body)
            (student / 'train.jsonl').write_bytes(body)
            linked = generation / 'wire.jsonl'; linked.write_bytes(body)
            (generation / 'small.json').write_text('untouched')
            (generation / 'wire-second-link').hardlink_to(linked)
            previous = worker.ROOT
            try:
                worker.ROOT = root; worker.main(audit)
            finally:
                worker.ROOT = previous
            self.assertFalse((generation / 'request.json').exists())
            self.assertTrue((generation / 'request.json.gz').exists())
            self.assertEqual((student / 'trajectory.json').read_bytes(), body)
            self.assertEqual((student / 'train.jsonl').read_bytes(), body)
            self.assertEqual(linked.read_bytes(), body)


if __name__ == '__main__':
    unittest.main()
