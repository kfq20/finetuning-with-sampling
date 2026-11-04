import asyncio
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from append_rewrite.terminus.production import batch, external_worker_alive


class CoordinatorHandoff(unittest.IsolatedAsyncioTestCase):
    async def test_adopted_and_completed_claims_never_spawn_again(self):
        if not Path('/proc/self/stat').exists():
            self.skipTest('Linux process adoption test')
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            output = root / 'run'
            units = output / 'units'
            units.mkdir(parents=True)
            items = []
            for key in ['already_done', 'adopted']:
                (units / key).mkdir()
                (units / key / 'status.json').write_text('{"phase":"completed"}')
                spec = root / (key + '.json'); spec.write_text('{}')
                items.append({'unit_id': key, 'lane': 'same', 'spec_path': str(spec)})
            plan = root / 'plan.json'; plan.write_text(json.dumps({'units': items}))
            worker = subprocess.Popen([sys.executable, '-c', 'import time;time.sleep(.3)'])
            try:
                proc = Path('/proc') / str(worker.pid)
                adoption = root / 'adoption.json'
                adoption.write_text(json.dumps({'workers': [{
                    'unit_id': 'adopted', 'pid': worker.pid,
                    'start_ticks': proc.joinpath('stat').read_text().split(') ')[1].split()[19],
                    'cmdline_sha256': hashlib.sha256(proc.joinpath('cmdline').read_bytes()).hexdigest(),
                }]}))
                args = SimpleNamespace(plan=plan, output=output, workers=8,
                                       adopt_workers=adoption, discovery_summary=None)
                with patch('asyncio.create_subprocess_exec', side_effect=AssertionError('claim replay')):
                    await batch(args)
                self.assertTrue((output / 'coordinator-finished.json').exists())
                self.assertEqual(json.loads((output / 'coordinator.json').read_text())['queue_policy'], 'shared')
            finally:
                worker.wait()

    async def test_shared_queue_dispatches_unclaimed_inputs_once(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d); output = root / 'run'; (output / 'specs').mkdir(parents=True)
            items = []
            for i in range(9):
                spec = root / f'{i}.json'; spec.write_text('{"fixed":true}')
                # A former coordinator may already have frozen queued specs.
                (output / 'specs' / f'u{i}.json').write_bytes(spec.read_bytes())
                items.append({'unit_id': f'u{i}', 'lane': 'one_old_lane', 'spec_path': str(spec)})
            plan = root / 'plan.json'; plan.write_text(json.dumps({'units': items}))
            args = SimpleNamespace(plan=plan, output=output, workers=8, adopt_workers=None,
                                   discovery_summary=None, teacher_config=root, fleet_config=root,
                                   tokenizer=root, sandbox_credentials=root, runtime_assets=root)
            called = []
            async def spawn(*argv, **kwargs):
                dest = Path(argv[argv.index('--output') + 1]); dest.mkdir(parents=True)
                called.append(dest.name)
                async def wait():
                    await asyncio.sleep(.01)
                    (dest / 'status.json').write_text('{"phase":"completed"}')
                return SimpleNamespace(wait=wait)
            with patch('asyncio.create_subprocess_exec', side_effect=spawn):
                await batch(args)
            self.assertEqual(sorted(called), [f'u{i}' for i in range(9)])


class IdentityGuard(unittest.TestCase):
    def test_live_pid_with_changed_command_hash_rejected(self):
        proc = Path('/proc') / str(os.getpid())
        if not proc.exists():
            self.skipTest('Linux process identity test')
        worker = {'pid': os.getpid(), 'start_ticks': proc.joinpath('stat').read_text().split(') ')[1].split()[19],
                  'cmdline_sha256': 'invalid'}
        with self.assertRaises(ValueError):
            external_worker_alive(worker)
