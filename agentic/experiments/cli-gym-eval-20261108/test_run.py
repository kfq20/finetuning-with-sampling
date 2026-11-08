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
    def test_native_format_recovery_does_not_abort_completed_evaluation(self):
        from harbor.agents.terminus_2.terminus_json_plain_parser import TerminusJSONPlainParser
        from append_rewrite.terminus.production import private_path_audit
        history = [{'role': 'user', 'content': 'task'},
                   {'role': 'assistant', 'content': 'not valid JSON'},
                   {'role': 'user', 'content': 'parser error feedback'},
                   {'role': 'assistant', 'content': '{"analysis":"done","plan":"finish","commands":[],"task_complete":true}'}]
        self.assertEqual(private_path_audit(history, native_parser=TerminusJSONPlainParser()), ([], [1]))
        with self.assertRaises(ValueError):
            private_path_audit(history)  # Strict production/SFT policy is unchanged.

    def test_private_paths_remain_rejected_after_native_parsing(self):
        from harbor.agents.terminus_2.terminus_json_plain_parser import TerminusJSONPlainParser
        from append_rewrite.terminus.production import private_path_audit
        message = json.dumps({'analysis': 'test', 'plan': 'read',
                              'commands': [{'keystrokes': 'cat /tests/secret\n', 'duration': 1}]})
        hits, errors = private_path_audit([{'role': 'assistant', 'content': message}],
                                        native_parser=TerminusJSONPlainParser())
        self.assertEqual(hits, [1])

    def test_recovery_rejects_changed_original_result(self):
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            original = root / 'trials/row-0001/result.json'
            original.parent.mkdir(parents=True)
            original.write_text('{"valid":false,"row_index":1}')
            recovered = root / 'recovered.json'
            recovered.write_text('{"valid":true,"row_index":1,"normal_native_completion":true}')
            index = {'1': {'path': str(recovered), 'sha256': module.hashlib.sha256(recovered.read_bytes()).hexdigest(),
                           'original_result_sha256': module.hashlib.sha256(original.read_bytes()).hexdigest()}}
            (root / 'recovery-selection.json').write_text(json.dumps(index))
            self.assertTrue(module.effective_result(root, 1)['valid'])
            original.write_text('{}')
            with self.assertRaises(AssertionError):
                module.effective_result(root, 1)

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
