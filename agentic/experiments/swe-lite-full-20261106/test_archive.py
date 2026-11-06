import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location('closed_journals', Path(__file__).parent / 'archive_closed.py')
archive = importlib.util.module_from_spec(spec); spec.loader.exec_module(archive)


class ArchiveTest(unittest.TestCase):
    def test_exact_bytes_and_provenance_are_recoverable(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'request.json'
            original = b'{"input_ids":[1,2,3],"role":"user"}\n' * 1000
            source.write_bytes(original)
            self.assertGreater(archive.archive(source, root / 'ledger.jsonl', root, 'terminal-sha'), 0)
            self.assertFalse(source.exists())
            self.assertEqual(gzip.decompress((root / 'request.json.gz').read_bytes()), original)
            receipt = json.loads((root / 'ledger.jsonl').read_text())
            self.assertEqual(receipt['source_sha256'], hashlib.sha256(original).hexdigest())
            self.assertTrue(receipt['verified_full_decompression'])

    def test_conflicting_archive_keeps_original(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); source = root / 'request.json'; source.write_bytes(b'original')
            (root / 'request.json.gz').write_bytes(gzip.compress(b'different'))
            with self.assertRaises(AssertionError):
                archive.archive(source, root / 'ledger.jsonl', root, 'terminal-sha')
            self.assertEqual(source.read_bytes(), b'original')


if __name__ == '__main__':
    unittest.main()
