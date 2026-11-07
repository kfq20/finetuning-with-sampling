import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
from append_rewrite.terminus.provider_gate import record_outage


class AdmissionGate(unittest.TestCase):
    def test_outage_is_preserved_and_auth_does_not_auto_recover(self):
        with tempfile.TemporaryDirectory() as d, patch.dict(os.environ, {'APPEND_REWRITE_PROVIDER_GATE': d}):
            for status in [401, 403]:
                record_outage('teacher', HTTPError('https://example', status, '', {}, None), 'original')
                self.assertFalse((Path(d) / 'teacher-outage.json').exists())
            record_outage('teacher', HTTPError('https://example', 502, '', {}, None), 'first')
            path = Path(d) / 'teacher-outage.json'
            original = path.read_bytes()
            record_outage('teacher', HTTPError('https://example', 429, '', {}, None), 'second')
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse(json.loads(original)['benchmark_retry'])

