import json
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

from append_rewrite.terminus.lifecycle import retire_failed_workers


class LifecycleTests(unittest.TestCase):
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
