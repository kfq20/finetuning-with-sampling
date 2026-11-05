"""Fleet adapter loading and exact-scope ECS evaluation handoff."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import time

import httpx

from run import write


def public(value):
    if isinstance(value, dict):
        return {k: ('<redacted>' if any(x in k.lower() for x in
            ['key', 'secret', 'token', 'artifact_url', 'lora_path', 'download_url']) else public(v))
            for k, v in value.items()}
    if isinstance(value, list):
        return [public(x) for x in value]
    if isinstance(value, str) and ('sig=' in value or 'X-Amz-' in value):
        return '<signed URL redacted>'
    return value


def deploy_and_evaluate(root, arm, plan, key, checkpoint):
    out = root / arm
    out.mkdir(exist_ok=True)
    task = plan['fleet']['tasks'][arm]
    payload = {'task_id': task, 'source': 'lora' if checkpoint else 'base',
        'base_model': plan['model'], 'priority': 0,
        'placement': {'cluster_id': plan['fleet']['cluster_id']}, 'name': task}
    if checkpoint:
        payload['model_url'] = checkpoint
    write(out / 'deployment-plan.json', payload)
    with httpx.Client(base_url=plan['fleet']['base_url'], headers={'x-api-key': key}, timeout=60) as client:
        with (out / 'deployment-intent.json').open('x') as f:
            json.dump({'at': time.time(), 'task_id': task}, f)
        response = client.post('/api/fleet/v1/deployments', json=payload)
        write(out / 'deployment-response.json', {'http_status': response.status_code, 'body': public(response.json())})
        response.raise_for_status()
        while True:
            if (root / 'STOP').exists():
                raise RuntimeError('Operator STOP before further inference/evaluation')
            response = client.get('/api/fleet/v1/deployments/' + task)
            response.raise_for_status()
            status = response.json()
            write(out / 'deployment-status.json', public(status))
            if status['state'] in ['serving', 'succeeded']:
                break
            if status['state'] in ['failed', 'cancelled', 'released']:
                raise RuntimeError('Fleet deployment ended: ' + status['state'])
            time.sleep(10)
        assert status['base_model'] == plan['model']
        assert status['cluster_id'] == plan['fleet']['cluster_id']
        assert status['model_id'] == task and status.get('mounted_at')
        request = {'model': task, 'input_ids': plan['smoke_prompt_ids'],
            'sampling_params': {'max_new_tokens': 16, 'temperature': 0}, 'stream': False}
        response = client.post('/d/' + task + '/generate', json=request)
        response.raise_for_status()
        value = response.json()
        write(out / 'deployment-inference.json', value)
        assert value['meta_info']['finish_reason']['type'] == 'stop' and value['text']
    # Stream the private endpoint configuration through SSH stdin, not argv.
    original_ingress = (root / 'runtime' / 'ecs_eval.py').read_text()
    ingress = original_ingress.replace('entry.write_text(SOURCE)', 'entry.write_text(' + repr(original_ingress) + ')')
    outer = '''import sys,pathlib,subprocess,os,shlex
sys.path.insert(0,'src')
from relayforge.asset_org.ecs_sync import _resolve_remote
remote,password=_resolve_remote(pathlib.Path('.secrets/ecs_remote.env'))
data=sys.stdin.read()
p=subprocess.run(['sshpass','-e','ssh','-o','ConnectTimeout=20',remote,
 'python3 -c '+shlex.quote(CODE)],input=data,text=True,capture_output=True,
 env={**os.environ,'SSHPASS':password},timeout=180)
print(p.stdout);print(p.stderr,file=sys.stderr)
raise SystemExit(p.returncode)
'''.replace('CODE', repr(ingress))
    handoff = {'arm': arm, 'plan': plan, 'fleet_key': key,
        'task_id': task, 'checkpoint': checkpoint,
        'ingress_sha256': hashlib.sha256(ingress.encode()).hexdigest()}
    result = subprocess.run(['ssh', 'mindlab', 'cd /vePFS-Mindverse/user/intern/fanqi/relayforge && python3 -c '
        + __import__('shlex').quote(outer)], input=json.dumps(handoff), text=True,
        capture_output=True, timeout=210)
    write(out / 'evaluation-handoff.json', {'exit_code': result.returncode,
        'stdout': result.stdout.replace(key, '<redacted>'),
        'stderr': result.stderr.replace(key, '<redacted>'), 'at': time.time()})
    if result.returncode:
        raise RuntimeError('ECS evaluation handoff failed; inspect receipt, do not resubmit')
