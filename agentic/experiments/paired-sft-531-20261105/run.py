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


def prepare_row(row, mint):
    ids, mask = row['input_ids'], row['assistant_loss_mask']
    assert len(ids) == len(mask) == len(row['labels'])
    assert all(x in (0, 1) for x in mask) and mask[0] == 0
    assert all(y == (x if w else -100) for x, w, y in zip(ids, mask, row['labels']))
    assert 0 < sum(mask) == row['supervised_tokens']
    return mint.types.Datum(
        model_input=mint.types.ModelInput.from_ints(ids[:-1]),
        loss_fn_inputs={'target_tokens': ids[1:], 'weights': mask[1:]})


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
        service = mint.ServiceClient(api_key=token, base_url=plan['base_url'],
            timeout=120, max_retries=0, http_client=httpx.AsyncClient(timeout=120),
            user_metadata={'experiment': plan['experiment'], 'arm': arm})
        event('creating_adapter', session_id=service.holder._session_id)
        client = service.create_lora_training_client(base_model=plan['model'], **plan['lora'])
        write(out / 'identity.json', {'session_id': service.holder._session_id,
            'model_id': client.model_id, 'credential_sha256': hashlib.sha256(token.encode()).hexdigest(),
            'mint_version': mint.__version__, 'tinker_version': mint.__tinker_version__})
        write(out / 'model-info.json', serial(client.get_info().result()))
        adam = mint.types.AdamParams(**plan['optimizer'])
        event('training_started', updates=len(order), model_id=client.model_id)
        for step, index in enumerate(order, 1):
            if (root / 'STOP').exists():
                raise RuntimeError('Operator STOP: no further updates dispatched')
            row = rows[index]
            assert len(row['input_ids']) <= plan['training']['max_length']
            datum = prepare_row(row, mint)
            step_root = out / 'steps' / f'{step:04d}'
            step_root.mkdir(parents=True, exist_ok=False)
            write(step_root / 'intent.json', {'row': index, 'source_identity': row['provenance']['input_identity'],
                'sequence_tokens': len(row['input_ids']), 'supervised_tokens': sum(row['assistant_loss_mask']),
                'automatic_replay': False})
            start = time.monotonic()
            event('forward_backward', step=step, row=index)
            result = client.forward_backward([datum], loss_fn='cross_entropy').result()
            lp = result.loss_fn_outputs[0]['logprobs']
            lp = lp.data if hasattr(lp, 'data') else lp
            weights = row['assistant_loss_mask'][1:]
            assert len(lp) == len(weights)
            nll = -sum(float(x) * w for x, w in zip(lp, weights)) / sum(weights)
            assert math.isfinite(nll)
            write(step_root / 'forward.json', {'mean_nll': nll, 'metrics': serial(result.metrics),
                'seconds': time.monotonic() - start})
            write(step_root / 'optimizer-intent.json', {'step': step, 'automatic_replay': False})
            started = time.monotonic()
            optim = client.optim_step(adam).result()
            write(step_root / 'optimizer.json', {'response': serial(optim), 'seconds': time.monotonic()-started})
            event('update_completed', step=step, row=index, mean_nll=nll, seconds=time.monotonic()-start)
            if step % plan['training']['save_every'] == 0 or step == len(order):
                name = f"{plan['experiment']}-{arm}-step{step:04d}"
                state = client.save_state(name + '-state').result()
                write(out / f'checkpoint-{step:04d}.json', serial(state))
                event('checkpoint_saved', step=step, state_path=state.path)
        sampler = client.save_weights_for_sampler(name + '-sampler').result()
        write(out / 'training-complete.json', {'optimizer_updates': len(order),
            'state_path': state.path, 'sampler_path': sampler.path, 'arm': arm,
            'dataset_sha256': sha(dataset), 'completed_at': time.time()})
        event('training_completed', optimizer_updates=len(order), state_path=state.path)
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
        jobs.append(pool.submit(deploy_and_evaluate, root, 'base', plan, credentials['fleet_key'], None))
        for job in jobs:
            try:
                job.result()
            except Exception as error:
                write(root / 'controller-error.json', {'error_type': type(error).__name__,
                    'message': str(error).replace(credentials['token'], '<redacted>').replace(credentials['fleet_key'], '<redacted>')[:1000]})


if __name__ == '__main__':
    main()
