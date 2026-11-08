import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

from append_rewrite.terminus.lifecycle import identity, retire_failed_workers


class LifecycleTests(unittest.TestCase):
    def test_process_disappearing_during_identity_read_is_not_a_failure(self):
        with patch.object(Path, 'read_text', side_effect=ProcessLookupError):
            self.assertIsNone(identity(123))

    def test_process_disappearing_during_cmdline_read_is_not_a_failure(self):
        stat = '123 (python) S ' + ' '.join(['0'] * 20)
        with patch.object(Path, 'read_text', return_value=stat), \
             patch.object(Path, 'read_bytes', side_effect=ProcessLookupError):
            self.assertIsNone(identity(123))

    def test_permission_errors_still_propagate(self):
        with patch.object(Path, 'read_text', side_effect=PermissionError):
            with self.assertRaises(PermissionError):
                identity(123)

    def test_exit_between_identity_check_and_signal_preserves_evidence(self):
        if not Path('/proc/self/stat').exists():self.skipTest('Linux process test')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run=root/'run';out=run/'units/u';out.mkdir(parents=True)
            spec=root/'spec.json';spec.write_text('{"unit_id":"u"}')
            (out/'status.json').write_text('{"phase":"hold"}')
            base=out/'student';base.mkdir()
            for name in ['error.json','context.json','public-messages.json']:(base/name).write_text('{}')
            worker=subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)',
                '-m','append_rewrite.terminus.production','unit','--output',str(out),'--spec',str(spec)])
            try:
                time.sleep(.05)
                with patch('append_rewrite.terminus.lifecycle.os.kill', side_effect=ProcessLookupError):
                    self.assertEqual(retire_failed_workers(run,[],root/'evidence',grace_sec=0),[])
                record=json.loads(next((root/'evidence').glob('*.json')).read_text())
                self.assertFalse(record['signalled'])
                self.assertTrue(record['exited_before_signal'])
                self.assertEqual((out/'status.json').read_text(),'{"phase":"hold"}')
            finally:
                if worker.poll() is None:worker.terminate();worker.wait()

    def test_live_episode_preserved_then_closed_failure_retires_once(self):
        if not Path('/proc/self/stat').exists():self.skipTest('Linux process test')
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);run=root/'run';out=run/'units/u';out.mkdir(parents=True)
            spec=root/'spec.json';spec.write_text('{"unit_id":"u"}')
            status=out/'status.json';status.write_text('{"phase":"student_8_candidates"}')
            base=out/'student';base.mkdir()
            for name in ['error.json','context.json','public-messages.json']:(base/name).write_text('{}')
            argv=[sys.executable,'-c','import time;time.sleep(60)','-m','append_rewrite.terminus.production','unit','--output',str(out),'--spec',str(spec)]
            worker=subprocess.Popen(argv)
            try:
                time.sleep(.05)
                self.assertEqual(retire_failed_workers(run,[],root/'evidence',grace_sec=0),[])
                self.assertIsNone(worker.poll())
                status.write_text('{"phase":"hold"}')
                old={p.name:p.read_bytes() for p in base.iterdir()}
                self.assertEqual(retire_failed_workers(run,[],root/'evidence',grace_sec=0),['u'])
                worker.wait(timeout=5)
                self.assertEqual(retire_failed_workers(run,[],root/'evidence',grace_sec=0),[])
                self.assertEqual(old,{p.name:p.read_bytes() for p in base.iterdir()})
                record=json.loads(next((root/'evidence').glob('*.json')).read_text());self.assertTrue(record['signalled'])
            finally:
                if worker.poll() is None:worker.terminate();worker.wait()
