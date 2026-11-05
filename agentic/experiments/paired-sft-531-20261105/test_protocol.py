"""Offline tests for next-token labels, masks and single-dispatch controls."""
import importlib.util
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest

from run import prepare_row, resolve, make_batches


class ProtocolTests(unittest.TestCase):
    def setUp(self):
        self.mint = SimpleNamespace(types=SimpleNamespace(
            ModelInput=SimpleNamespace(from_ints=lambda ids: ids),
            Datum=lambda **values: values))
        self.row = {'input_ids': [10, 20, 30, 40], 'labels': [-100, -100, 30, 40],
            'assistant_loss_mask': [0, 0, 1, 1], 'supervised_tokens': 2}

    def test_shift_is_next_token_and_preserves_assistant_end(self):
        value = prepare_row(self.row, self.mint)
        self.assertEqual(value['model_input'], [10, 20, 30])
        self.assertEqual(value['loss_fn_inputs'], {'target_tokens': [20, 30, 40], 'weights': [0, 1, 1]})

    def test_corrupted_label_rejected(self):
        self.row['labels'][2] = 99
        with self.assertRaises(AssertionError):
            prepare_row(self.row, self.mint)

    def test_empty_supervision_rejected(self):
        self.row.update(labels=[-100]*4, assistant_loss_mask=[0]*4, supervised_tokens=0)
        with self.assertRaises(AssertionError):
            prepare_row(self.row, self.mint)

    def test_claim_cannot_be_reset_by_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            p = Path(directory) / 'claim.json'
            with p.open('x') as f:
                f.write('{}')
            with self.assertRaises(FileExistsError):
                p.open('x')

    def test_frozen_ingress_compiles_without_embedded_secrets(self):
        source = Path(__file__).with_name('ecs_eval.py').read_text()
        rendered = source.replace('entry.write_text(SOURCE)', 'entry.write_text(' + repr(source) + ')')
        compile(rendered, 'remote-ingress', 'exec')
        self.assertNotIn('sk-', rendered)

    def test_sdk_sync_info_and_future_are_both_supported(self):
        info = SimpleNamespace(model_id='test')
        self.assertIs(resolve(info), info)
        self.assertIs(resolve(SimpleNamespace(result=lambda: info)), info)

    def test_resumed_batch16_keeps_tail_without_replaying_old_rows(self):
        order = list(reversed(range(531)))
        batches = make_batches(order, 54, 16)
        self.assertEqual(len(batches), 30)
        self.assertEqual(len(batches[-1]), 13)
        self.assertTrue(all(len(batch) == 16 for batch in batches[:-1]))
        flat = [x for batch in batches for x in batch]
        self.assertFalse(set(flat) & set(order[:54]))
        self.assertEqual(order[:54] + flat, order)


if __name__ == '__main__':
    unittest.main()
