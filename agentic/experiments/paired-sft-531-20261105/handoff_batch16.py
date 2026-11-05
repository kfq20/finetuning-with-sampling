"""Finish exact pending batch1 updates, checkpoint, retire only our old owner.

The old worker has no drain hook. Hold its verified process only at a submitted
backward with NO optimizer intent, finish that one update through its next
documented sequence number, then save optimizer state. Never resume that worker
after consuming its sequence; its immutable code and original evidence remain.
"""
import concurrent.futures
import hashlib
import json
import math
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time

import httpx

from run import sha, write


def owner_matches(pid, launch):
    cmd = subprocess.check_output(['ps', '-p', str(pid), '-o', 'command='], text=True).strip()
    assert all(str(x) in cmd for x in launch['command'][1:]), 'Old owner identity changed'
    started = subprocess.check_output(['ps', '-p', str(pid), '-o', 'lstart='],
        text=True, env={**os.environ, 'LC_ALL': 'C'}).strip()
    assert abs(time.mktime(time.strptime(started, '%a %b %d %H:%M:%S %Y'))-launch['started_at']) < 10


def boundary(old):
    result = {}
    for arm in ['method', 'expert']:
        folder = old / arm
        status = json.loads((folder / 'status.json').read_text())
        if status['stage'] != 'forward_backward':
            return None
        step = status['step']
        current = folder / 'steps' / f'{step:04d}'
        if not (current / 'intent.json').exists() or (current / 'optimizer-intent.json').exists():
            return None
        if time.time() - (current/'intent.json').stat().st_mtime < 5:
            return None
        if len(list((folder / 'steps').glob('*/optimizer.json'))) != step-1:
            return None
        result[arm] = {'pending_step': step, 'current_intent': json.loads((current / 'intent.json').read_text()),
            'intent_sha256': sha(current / 'intent.json'),
            'identity': json.loads((folder / 'identity.json').read_text())}
    return result


def main():
    os.umask(0o077)
    root = Path(sys.argv[1]).resolve()
    old = Path(json.loads((root / 'migration-plan.json').read_text())['old_root'])
    plan = json.loads((old / 'plan.json').read_text())
    assert plan['training']['batch_size'] == 1 and not plan.get('resume')
    for name, digest in plan['runtime_sha256'].items():
        assert sha(old/'runtime'/name) == digest, name
    token = json.loads(sys.stdin.readline())['token']
    assert hashlib.sha256(token.encode()).hexdigest() == json.loads((old/'launch.json').read_text())['credential_sha256']
    launch = json.loads((old/'launch.json').read_text())
    pid = launch['pid']
    with (root / 'handoff-claim.json').open('x') as f:
        json.dump({'at': time.time(), 'old_pid': pid}, f)
    client = httpx.Client(base_url=plan['base_url'], headers={'X-API-Key': token}, timeout=60)
    stop_heartbeat = threading.Event()
    sessions = [json.loads((old/a/'identity.json').read_text())['session_id'] for a in ['method','expert']]
    def heartbeat():
        while not stop_heartbeat.is_set():
            for session in sessions:
                try:
                    client.post('/api/v1/session_heartbeat', json={'session_id': session})
                except httpx.HTTPError:
                    pass
            stop_heartbeat.wait(15)
    threading.Thread(target=heartbeat, daemon=True).start()
    mutated = False
    held = False
    try:
        # Check authorization with a metadata read before holding any live work.
        for arm in ['method','expert']:
            model = json.loads((old/arm/'identity.json').read_text())['model_id']
            client.get('/api/v1/models/'+model+'/session_guard_state').raise_for_status()
        while True:
            owner_matches(pid, launch)
            if boundary(old) is None:
                time.sleep(.2)
                continue
            os.kill(pid, signal.SIGSTOP)
            held = True
            state = boundary(old)
            if state is not None:
                guards = {}
                for arm, record in state.items():
                    response = client.get('/api/v1/models/'+record['identity']['model_id']+'/session_guard_state')
                    response.raise_for_status()
                    guards[arm] = response.json()
                if all(2*x['pending_step']-1 <= guards[a]['next_expected_seq'] <= 2*x['pending_step']
                       for a,x in state.items()):
                    break
            os.kill(pid, signal.SIGCONT)
            held = False
            time.sleep(.2)
        write(root/'held-owner.json', {'at': time.time(), 'old_launch': launch, 'boundaries': state, 'guards': guards})
        def operation(arm, name, route, payload):
            nonlocal mutated
            out = root / arm
            out.mkdir(exist_ok=True)
            with (out/(name+'-intent.json')).open('x') as f:
                json.dump({'at': time.time(), 'payload': payload, 'automatic_replay': False}, f)
            mutated = True
            response = client.post(route, json=payload)
            write(out/(name+'-enqueue.json'), {'http_status': response.status_code, 'body': response.json()})
            response.raise_for_status()
            future = response.json()['request_id']
            while True:
                response = client.post('/api/v1/retrieve_future', json={'request_id': future})
                if response.status_code == 408:
                    time.sleep(2)
                    continue
                response.raise_for_status()
                value = response.json()
                if value.get('error') or value.get('type') in ['request_failed', 'failed']:
                    raise RuntimeError('Future failed; see preserved request_id '+future)
                write(out/(name+'-result.json'), value)
                return value
        def save_arm(arm):
            (root/arm).mkdir(exist_ok=True)
            record = state[arm]
            step = record['pending_step']
            model = record['identity']['model_id']
            # Scheduler advances the guard on completion, not on submission.
            # Keep the owner held while its already-submitted backward finishes;
            # do not race its unrecorded optimizer or submit a second backward.
            while True:
                response = client.get('/api/v1/models/'+model+'/session_guard_state')
                response.raise_for_status()
                guard = response.json()
                write(root/arm/'backward-drain-guard.json', guard)
                if guard['next_expected_seq'] == 2*step:
                    break
                assert guard['next_expected_seq'] == 2*step-1 and guard['status'] == 'active'
                time.sleep(2)
            optim = operation(arm, 'finish-pending-optimizer', '/api/v1/optim_step',
                {'model_id': model, 'seq_id': 2*step, 'adam_params': plan['optimizer'], 'type': 'optim_step'})
            grad = optim.get('metrics', {}).get('grad_norm')
            assert grad is not None and math.isfinite(grad)
            saved = operation(arm, 'save-boundary', '/api/v1/save_state',
                {'model_id': model, 'seq_id': 2*step+1,
                 'path': f'qwen38-paired531-{arm}-batch1-boundary-{step:04d}-20261105',
                 'checkpoint_level': 'optimizer', 'include_optimizer': True, 'type': 'save_state'})
            assert saved.get('path', '').startswith('tinker://')
            receipt = {'arm': arm, 'completed_examples': step, 'completed_batch1_updates': step,
                'state_path': saved['path'], 'old_model_id': model,
                'boundary_intent_sha256': record['intent_sha256'],
                'pending_backward_not_replayed': True, 'optimizer_completed_once': True,
                'optimizer_receipt_sha256': sha(root/arm/'finish-pending-optimizer-result.json'),
                'at': time.time()}
            write(root/arm/'handoff-complete.json', receipt)
            return receipt
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            completed = dict(zip(['method','expert'], pool.map(save_arm, ['method','expert'])))
        write(root/'handoff-complete.json', {'arms': completed, 'at': time.time()})
        owner_matches(pid, launch)
        os.kill(pid, signal.SIGKILL)  # Retire held owner; never run its now-consumed optimizer seq.
        stop_heartbeat.set()
        for arm, record in state.items():
            response = client.delete('/api/v1/mint/sessions/'+record['identity']['session_id'])
            write(root/arm/'old-session-cleanup.json', {'http_status': response.status_code,
                'checkpoint_deletion_requested': False, 'session_id': record['identity']['session_id']})
            response.raise_for_status()
        write(root/'old-owner-retired.json', {'pid': pid, 'at': time.time(), 'both_optimizer_checkpoints_saved': True})
        print(json.dumps({'handoff_complete': True, 'arms': completed}), flush=True)
    except Exception as error:
        write(root/'handoff-error.json', {'error_type': type(error).__name__,
            'message': str(error).replace(token, '<redacted>'), 'mutated': mutated, 'held': held, 'at': time.time()})
        if held and not mutated:
            os.kill(pid, signal.SIGCONT)
        raise


if __name__ == '__main__':
    main()
