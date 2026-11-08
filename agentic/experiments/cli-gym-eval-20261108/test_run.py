"""Evaluation reports valid zero separately and cannot replay an existing trial."""
import asyncio
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, patch

spec = importlib.util.spec_from_file_location('cli_eval', Path(__file__).with_name('run.py'))
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class EvaluationTests(unittest.TestCase):
    def check_trial(self, scores, existing=False):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            path = root / 'spec.json'
            path.write_text('{}')
            item = {'row_index': 1, 'spec_path': str(path),
                    'spec_sha256': module.hashlib.sha256(path.read_bytes()).hexdigest()}
            out = root / 'trials/row-0001'
            if existing:
                out.mkdir(parents=True)
            async def episode(*args, **kwargs):
                self.assertEqual(args[3], 'evaluation')
                self.assertIn('backend', kwargs)
                args[2].mkdir(parents=True)
                return {'score': {'reward': scores[0]}, 'fresh_score': {'reward': scores[1]},
                        'executed_interactions': 3}
            fake = AsyncMock(side_effect=episode)
            with patch.object(module, 'episode', fake), \
                 patch.object(module, 'CancellableQwenLLM'), patch.object(module, 'PinnedTokenizer'):
                asyncio.run(module.trial(root, item, {'tokenizer': '/frozen',
                    'runtime_assets': '/assets', 'model': 'base'}))
            result = out / 'result.json'
            return fake.call_count, json.loads(result.read_text()) if result.exists() else None

    def test_normal_zero_is_valid(self):
        calls, result = self.check_trial((0, 0))
        self.assertEqual(calls, 1)
        self.assertTrue(result['valid'])
        self.assertEqual(result['binary_score'], 0)

    def test_inconsistent_grades_are_unknown(self):
        _, result = self.check_trial((0, 1))
        self.assertFalse(result['valid'])
        self.assertIsNone(result['binary_score'])

    def test_existing_attempt_is_not_replayed(self):
        calls, result = self.check_trial((1, 1), existing=True)
        self.assertEqual(calls, 0)
        self.assertIsNone(result)


if __name__ == '__main__':
    unittest.main()
