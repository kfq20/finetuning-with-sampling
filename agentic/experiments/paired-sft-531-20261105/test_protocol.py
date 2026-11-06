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

class EpochContinuationTests(unittest.TestCase):
    def test_two_epochs_keep_both_three_row_tails(self):
        from run import epoch_schedule
        order, schedule = epoch_schedule(531, 2, 42, 16)
        self.assertEqual(len(order), 1062)
        self.assertEqual(len(schedule), 68)
        for epoch in [1, 2]:
            batches = [item['indices'] for item in schedule if item['epoch'] == epoch]
            self.assertEqual(len(batches), 34)
            self.assertEqual(len(batches[-1]), 3)
            self.assertEqual(sorted(i for batch in batches for i in batch), list(range(531)))

    def test_resume_after_epoch_one_dispatches_only_epoch_two(self):
        from run import epoch_schedule
        order, full = epoch_schedule(531, 2, 42, 16)
        resumed_order, resumed = epoch_schedule(531, 2, 42, 16, offset=531)
        self.assertEqual(resumed_order, order)
        self.assertEqual(resumed, full[34:])
        self.assertEqual({item['epoch'] for item in resumed}, {2})
        self.assertEqual(len(resumed), 34)

    def test_epoch_one_matches_original_shuffle_and_batching(self):
        import random
        from run import epoch_schedule
        expected = list(range(531))
        random.Random(42).shuffle(expected)
        order, schedule = epoch_schedule(531, 1, 42, 16)
        self.assertEqual(order, expected)
        self.assertEqual([x['indices'] for x in schedule], make_batches(expected, 0, 16))

    def test_already_complete_resume_cannot_retrain(self):
        from run import epoch_schedule
        with self.assertRaises(AssertionError):
            epoch_schedule(531, 2, 42, 16, offset=1062)

class EpochTrainingIntegration(unittest.TestCase):
    def test_resume_restores_optimizer_and_exports_global_step_without_deploying(self):
        import json
        import sys
        from unittest.mock import patch
        import serving
        from run import train, sha

        calls = []
        future = lambda value: SimpleNamespace(result=lambda: value)
        class Client:
            model_id = 'fixture-model'
            def get_info(self):
                return {'base_model': 'fixture'}
            def load_state_with_optimizer(self, path):
                calls.append(('restore', path))
                return future({})
            def forward_backward(self, datums, loss_fn):
                calls.append(('forward', len(datums)))
                return future(SimpleNamespace(loss_fn_outputs=[{'logprobs': [-.1]*3} for _ in datums], metrics={}))
            def optim_step(self, params):
                calls.append(('optim', None))
                return future({})
            def save_state(self, name):
                calls.append(('state', name))
                return future(SimpleNamespace(path='tinker://fixture/' + name))
            def save_weights_for_sampler(self, name):
                return future(SimpleNamespace(path='tinker://fixture/' + name))
        client = Client()
        mint = SimpleNamespace(__version__='fixture', __tinker_version__='fixture',
            ServiceClient=lambda **kw: SimpleNamespace(holder=SimpleNamespace(_session_id='fixture-session'),
                create_lora_training_client=lambda **kw: client),
            types=SimpleNamespace(ModelInput=SimpleNamespace(from_ints=lambda ids: ids),
                Datum=lambda **kw: kw, AdamParams=lambda **kw: kw))
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            dataset=root/'data.jsonl'
            row={'input_ids':[10,20,30,40], 'labels':[-100,-100,30,40],
                 'assistant_loss_mask':[0,0,1,1], 'supervised_tokens':2,
                 'provenance':{'input_identity':'fixture'}}
            dataset.write_text(''.join(json.dumps(row)+'\n' for _ in range(4)))
            plan={'experiment':'fixture','base_url':'https://example.invalid/train','model':'fixture',
                'datasets':{'method':{'path':str(dataset),'sha256':sha(dataset)}},
                'training':{'rows':4,'num_epochs':2,'seed':42,'batch_size':2,'max_length':4,'save_every':100},
                'resume':{'method':{'state_path':'tinker://prior','completed_examples':4,
                                    'completed_optimizer_updates':2,'batch_size':2}},
                'lora':{},'optimizer':{},'deploy_after_training':False}
            (root/'plan.json').write_text(json.dumps(plan))
            with patch.dict(sys.modules,{'mint':mint}), patch('httpx.delete',return_value=SimpleNamespace(status_code=200)), patch.object(serving,'deploy_and_evaluate',side_effect=AssertionError('No serving mutation')):
                train(root,'method',plan,'fixture-token','unused-fleet-key')
            self.assertFalse((root/'method/error.json').exists())
            result=json.loads((root/'method/training-complete.json').read_text())
            self.assertEqual(result['total_optimizer_updates'],4)
            self.assertEqual(result['previous_optimizer_updates'],2)
            self.assertEqual(result['examples_trained_total'],8)
            self.assertEqual(result['epochs_completed'],2)
            self.assertEqual(calls[0],('restore','tinker://prior'))
            self.assertEqual([name for name,_ in calls],['restore','forward','optim','forward','optim','state'])
            self.assertTrue(calls[-1][1].endswith('step0004-state'))
            self.assertEqual([p.name for p in sorted((root/'method/steps').iterdir())],['0003','0004'])
