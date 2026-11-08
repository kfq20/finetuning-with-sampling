"""Direct admission skips calibration, never final scoring or non-CLI controls."""
import asyncio
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from append_rewrite.terminus import production


class DirectAdmissionTests(unittest.TestCase):
    def run_unit(self, kind, mode):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            spec = root / 'spec.json'
            spec.write_text(json.dumps({'unit_id': 'test', 'source': {'kind': kind},
                                        'preflight_mode': mode}))
            episode = AsyncMock(return_value={'expert_admitted': False})
            with patch.object(production, 'controls', side_effect=RuntimeError('original gate')) as controls, \
                    patch.object(production, 'episode', episode):
                args = SimpleNamespace(spec=spec, output=root / 'unit')
                try:
                    asyncio.run(production.unit(args))
                    error = None
                except (ValueError, RuntimeError) as exc:
                    error = str(exc)
                receipt = root / 'unit/controls/receipt.json'
                return error, controls.call_count, episode.call_count, json.loads(receipt.read_text()) if receipt.exists() else None

    def test_cli_skips_calibration_without_forging_pass(self):
        error, controls, episodes, receipt = self.run_unit('cli-gym', 'cli-build-only')
        self.assertIsNone(error)
        self.assertEqual((controls, episodes), (0, 1))
        self.assertFalse(receipt['calibration_performed'])
        self.assertNotIn('passed', receipt)

    def test_swe_cannot_use_cli_override(self):
        error, controls, episodes, _ = self.run_unit('swe-gym', 'cli-build-only')
        self.assertIn('limited to CLI', error)
        self.assertEqual((controls, episodes), (0, 0))

    def test_default_retains_original_controls(self):
        error, controls, episodes, _ = self.run_unit('cli-gym', None)
        self.assertEqual(error, 'original gate')
        self.assertEqual((controls, episodes), (1, 0))


if __name__ == '__main__':
    unittest.main()
