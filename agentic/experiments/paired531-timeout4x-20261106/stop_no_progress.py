"""Finite, user-authorized stop of TWO verified no-progress sandboxes only."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import time

ROOT = Path('/mnt/ecs-tb4/evaluations/qwen38-paired531-timeout4x-retry1-20261106-a1')
TARGETS = {
    'base': ('build-pov-ray__kzQGGtq', 'sbx-bfd30f1b-f9b0-4ae7-95dd-dc7b755fb07e', 'c-6aed4d49-00cfc4c1-0cfc63592506'),
    'method': ('build-pov-ray__wmi2imf', 'sbx-0307ecde-8661-49f7-96dd-ac46356440d0', 'c-6aed4d49-00cfc4c1-f631cb6c8992'),
}


def write(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def list_resources(Sandbox):
    pager = Sandbox.list(limit=100)
    items = []
    while pager.has_next:
        items.extend(pager.next_items())
    return items


def main():
    from dotenv import dotenv_values
    from e2b import Sandbox

    os.umask(0o077)
    out = ROOT / 'support/operator-stop-build-pov-ray-20261106'
    assert not (out / 'stop-intent.json').exists(), 'Do not repeat an issued stop'
    out.mkdir(parents=True, exist_ok=True)
    secret = dotenv_values('/mnt/ecs-tb4/cli-gym-scale-20261104/support/private/sandbox.env', interpolate=False)
    os.environ.update({k: secret[k] for k in ['E2B_API_KEY', 'E2B_API_URL', 'E2B_DOMAIN']})
    listed = list_resources(Sandbox)
    processes = {}
    for name in ['base', 'method', 'expert']:
        launch = json.loads((ROOT / name / 'launch.json').read_text())
        stat = Path(f'/proc/{launch["pid"]}/stat').read_text().split()
        assert stat[21] == launch['start_ticks'] and stat[2] != 'Z'
        processes[name] = launch
    verified = []
    for arm, (trial, sid, instance) in TARGETS.items():
        path = ROOT / arm / 'jobs/timeout4x-retry1' / trial
        assert not (path / 'result.json').exists(), 'Task already ended; re-audit'
        matches = [x for x in listed if (x.metadata or {}).get('session_id') == trial + '__env']
        assert len(matches) == 1
        found = matches[0]
        assert found.sandbox_id == sid
        assert found.metadata['instanceID'] == instance
        assert found.metadata['environment_name'] == 'build-pov-ray'
        raw = (path / 'agent/trajectory.json').read_bytes()
        assert instance.encode() in raw
        target = out / arm
        target.mkdir()
        (target / 'trajectory-before-stop.json').write_bytes(raw)
        shutil.copyfile(path / 'trial.log', target / 'trial-before-stop.log')
        turns = sorted((path / 'native-generation').glob('turn-*'))
        last = turns[-1]
        pending = None
        if (last / 'intent.json').exists() and not (last / 'decision.json').exists():
            pending = json.loads((last / 'intent.json').read_text())['request_id']
        verified.append({'arm': arm, 'trial': trial, 'sandbox_id': sid,
                         'instance_id': instance, 'session_id': trial + '__env',
                         'trajectory_sha256': hashlib.sha256(raw).hexdigest(),
                         'pending_model_request_id_at_stop': pending,
                         'disposition': 'operator_stopped_no_progress',
                         'eligible_for_auto_retry': False})
    intent = {'at': time.time(), 'reason': 'User requested stopping verified repetitive build-pov-ray trials only',
              'targets': verified, 'shared_processes_before': processes,
              'source_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    write(out / 'stop-intent.json', intent)
    # Persist provenance before either targeted resource is removed. Raw Harbor
    # exceptions remain untouched and must not be counted as valid model0.
    index = ROOT / 'operator_stops.json'
    original = json.loads(index.read_text()) if index.exists() else {}
    for item in verified:
        assert item['trial'] not in original
        original[item['trial']] = item
    temporary = ROOT / 'operator_stops.json.pending'
    write(temporary, original)
    temporary.replace(index)
    receipts = []
    for item in verified:
        result = Sandbox.kill(item['sandbox_id'])
        receipts.append({'trial': item['trial'], 'sandbox_id': item['sandbox_id'],
                         'kill_returned': result, 'at': time.time()})
        write(out / 'kill-receipts.json', receipts)
    after = list_resources(Sandbox)
    ids = {x.sandbox_id for x in after}
    assert all(item['sandbox_id'] not in ids for item in verified)
    for arm, launch in processes.items():
        stat = Path(f'/proc/{launch["pid"]}/stat').read_text().split()
        assert stat[21] == launch['start_ticks'] and stat[2] != 'Z'
    write(out / 'postcheck.json', {'at': time.time(), 'targets_absent': True,
          'all_three_harbor_process_identities_unchanged': True,
          'resources_before': len(listed), 'resources_after': len(after),
          'only_explicit_kill_ids': [x['sandbox_id'] for x in verified]})
    print(json.dumps({'stopped': receipts, 'shared_harbor_unchanged': True}))


if __name__ == '__main__':
    main()
