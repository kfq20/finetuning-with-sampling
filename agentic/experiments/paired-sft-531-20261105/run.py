"""Paired full-episode SFT; frozen inputs, write-ahead updates, no paid replay.

Run from an immutable copy. Credential JSON arrives on stdin, never argv.
Each arm owns a separate training session; a failed arm does not stop the other.
Fleet and evaluation are delegated to the adjacent serving module.
"""
import concurrent.futures
import dataclasses
import hashlib
import json
import logging
import math
import os
from pathlib import Path
import random
import sys
import time
from datetime import datetime, timezone

logging.disable(logging.CRITICAL)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    tmp = path.with_suffix(path.suffix + '.new')
    tmp.write_text(json.dumps(value, indent=2, default=str) + '\n')
    tmp.replace(path)


def serial(value):
    if hasattr(value, 'model_dump'):
        return serial(value.model_dump(mode='json'))
    if dataclasses.is_dataclass(value):
        return {f.name: serial(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, dict):
        return {k: serial(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [serial(v) for v in value]
    return value


def resolve(value):
    """SDK get_info is synchronous; training/checkpoint calls return futures."""
    return value.result() if hasattr(value, 'result') else value


def prepare_row(row, mint):
    ids, mask = row['input_ids'], row['assistant_loss_mask']
    assert len(ids) == len(mask) == len(row['labels'])
    assert all(x in (0, 1) for x in mask) and mask[0] == 0
    assert all(y == (x if w else -100) for x, w, y in zip(ids, mask, row['labels']))
    assert 0 < sum(mask) == row['supervised_tokens']
    return mint.types.Datum(
        model_input=mint.types.ModelInput.from_ints(ids[:-1]),
        loss_fn_inputs={'target_tokens': ids[1:], 'weights': mask[1:]})


def make_batches(order, offset, size):
    assert isinstance(size, int) and size > 0 and 0 <= offset < len(order)
    batches = [order[i:i+size] for i in range(offset, len(order), size)]
    assert [item for batch in batches for item in batch] == order[offset:]
    return batches


def train(root, arm, plan, token, fleet_key):
    import httpx
    import mint
    from serving import deploy_and_evaluate

    out = root / arm
    out.mkdir(exist_ok=True)
    service = None
    def event(stage, **values):
        row = {'at': datetime.now(timezone.utc).isoformat(), 'stage': stage, **values}
        with (out / 'events.jsonl').open('a') as f:
            f.write(json.dumps(row, default=str) + '\n')
        write(out / 'status.json', row)
        print(json.dumps({'arm': arm, **row}), flush=True)
    try:
        with (out / 'claim.json').open('x') as f:
            json.dump({'plan_sha256': sha(root / 'plan.json'), 'at': time.time()}, f)
        dataset = Path(plan['datasets'][arm]['path'])
        assert sha(dataset) == plan['datasets'][arm]['sha256']
        rows = [json.loads(line) for line in dataset.open()]
        assert len(rows) == plan['training']['rows']
        order = list(range(len(rows)))
        random.Random(plan['training']['seed']).shuffle(order)
        write(out / 'order.json', order)
        resume = plan.get('resume', {}).get(arm)
        offset = resume['completed_examples'] if resume else 0
        batch_size = plan['training']['batch_size']
        batches = make_batches(order, offset, batch_size)
        assert sorted([i for batch in batches for i in batch] + order[:offset]) == list(range(len(order)))
        write(out / 'batch-order.json', {'batch_size': batch_size, 'previous_examples': offset,
            'previous_rows': order[:offset], 'batches': batches, 'dropped_rows': []})
        service = mint.ServiceClient(api_key=token, base_url=plan['base_url'],
            timeout=120, max_retries=0, http_client=httpx.AsyncClient(timeout=120),
            user_metadata={'experiment': plan['experiment'], 'arm': arm})
        event('creating_adapter', session_id=service.holder._session_id)
        client = service.create_lora_training_client(base_model=plan['model'], **plan['lora'])
        write(out / 'identity.json', {'session_id': service.holder._session_id,
            'model_id': client.model_id, 'credential_sha256': hashlib.sha256(token.encode()).hexdigest(),
            'mint_version': mint.__version__, 'tinker_version': mint.__tinker_version__})
        write(out / 'model-info.json', serial(resolve(client.get_info())))
        if resume:
            restored = resolve(client.load_state_with_optimizer(resume['state_path']))
            write(out / 'optimizer-state-restored.json', {'source': resume, 'response': serial(restored)})
            event('optimizer_state_restored', previous_examples=offset, batch_size=batch_size)
        adam = mint.types.AdamParams(**plan['optimizer'])
        event('training_started', updates=len(batches), model_id=client.model_id,
              batch_size=batch_size, previous_examples=offset, target_examples=len(order))
        processed = offset
        for step, indices in enumerate(batches, 1):
            if (root / 'STOP').exists():
                raise RuntimeError('Operator STOP: no further updates dispatched')
            batch = [rows[index] for index in indices]
            assert all(len(row['input_ids']) <= plan['training']['max_length'] for row in batch)
            datums = [prepare_row(row, mint) for row in batch]
            step_root = out / 'steps' / f'{step:04d}'
            step_root.mkdir(parents=True, exist_ok=False)
            write(step_root / 'intent.json', {'rows': indices,
                'source_identities': [row['provenance']['input_identity'] for row in batch],
                'actual_batch_size': len(batch),
                'sequence_tokens': sum(len(row['input_ids']) for row in batch),
                'supervised_tokens': sum(sum(row['assistant_loss_mask']) for row in batch),
                'automatic_replay': False})
            start = time.monotonic()
            event('forward_backward', step=step, rows=indices, actual_batch_size=len(batch),
                  completed_examples=processed)
            result = client.forward_backward(datums, loss_fn='cross_entropy').result()
            assert len(result.loss_fn_outputs) == len(batch)
            numerator = denominator = 0
            for output, row in zip(result.loss_fn_outputs, batch):
                lp = output['logprobs']
                lp = lp.data if hasattr(lp, 'data') else lp
                weights = row['assistant_loss_mask'][1:]
                assert len(lp) == len(weights)
                numerator -= sum(float(x) * w for x, w in zip(lp, weights))
                denominator += sum(weights)
            nll = numerator / denominator
            assert math.isfinite(nll)
            write(step_root / 'forward.json', {'mean_nll': nll, 'metrics': serial(result.metrics),
                'seconds': time.monotonic() - start})
            write(step_root / 'optimizer-intent.json', {'step': step, 'automatic_replay': False})
            started = time.monotonic()
            optim = client.optim_step(adam).result()
            write(step_root / 'optimizer.json', {'response': serial(optim), 'seconds': time.monotonic()-started})
            processed += len(batch)
            event('update_completed', step=step, rows=indices, mean_nll=nll,
                  actual_batch_size=len(batch), completed_examples=processed,
                  target_examples=len(order), seconds=time.monotonic()-start)
            if step % plan['training']['save_every'] == 0 or step == len(batches):
                name = f"{plan['experiment']}-{arm}-step{step:04d}"
                state = client.save_state(name + '-state').result()
                write(out / f'checkpoint-{step:04d}.json', serial(state))
                event('checkpoint_saved', step=step, state_path=state.path)
        sampler = client.save_weights_for_sampler(name + '-sampler').result()
        assert processed == len(order)
        write(out / 'training-complete.json', {'optimizer_updates': len(batches),
            'previous_optimizer_updates': offset, 'examples_trained_total': processed,
            'batch_size': batch_size, 'previous_batch_size': 1 if resume else None,
            'state_path': state.path, 'sampler_path': sampler.path, 'arm': arm,
            'dataset_sha256': sha(dataset), 'completed_at': time.time()})
        event('training_completed', optimizer_updates=len(batches), completed_examples=processed, state_path=state.path)
        deploy_and_evaluate(root, arm, plan, fleet_key, state.path)
        event('evaluation_launched')
    except Exception as error:
        # Do not export request bodies, credentials, or unredacted server URLs.
        message = str(error).replace(token, '<redacted>').replace(fleet_key, '<redacted>')[:1000]
        event('error', error_type=type(error).__name__, message=message, automatic_replay=False)
        write(out / 'error.json', {'error_type': type(error).__name__, 'message': message,
            'automatic_replay': False, 'at': time.time()})
    finally:
        if service is not None:
            try:
                response = httpx.delete(plan['base_url'] + '/api/v1/mint/sessions/' + service.holder._session_id,
                    headers={'X-API-Key': token, 'Authorization': 'Bearer ' + token}, timeout=40)
                write(out / 'cleanup.json', {'http_status': response.status_code,
                    'session_id': service.holder._session_id, 'checkpoint_deletion_requested': False})
            except Exception as error:
                write(out / 'cleanup.json', {'error_type': type(error).__name__})


def main():
    os.umask(0o077)
    root = Path(sys.argv[1]).resolve()
    plan = json.loads((root / 'plan.json').read_text())
    for name, digest in plan['runtime_sha256'].items():
        assert sha(root / 'runtime' / name) == digest
    assert not any((root / arm / 'claim.json').exists() for arm in ['method', 'expert'])
    credentials = json.loads(sys.stdin.readline())
    from serving import deploy_and_evaluate
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        jobs = [pool.submit(train, root, arm, plan, credentials['token'], credentials['fleet_key'])
                for arm in ['method', 'expert']]
        if plan.get('evaluate_base', True):
            jobs.append(pool.submit(deploy_and_evaluate, root, 'base', plan, credentials['fleet_key'], None))
        for job in jobs:
            try:
                job.result()
            except Exception as error:
                write(root / 'controller-error.json', {'error_type': type(error).__name__,
                    'message': str(error).replace(credentials['token'], '<redacted>').replace(credentials['fleet_key'], '<redacted>')[:1000]})


if __name__ == '__main__':
    main()
