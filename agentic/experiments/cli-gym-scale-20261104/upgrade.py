"""One authorized, exact-identity4->8 scheduler handoff; no task/model replay."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

ROOT = Path('/mnt/ecs-tb4/cli-gym-scale-20261104')
SOURCE = ROOT / 'frozen-concurrency-710c9c5'
COMMIT = '710c9c5'


def dump(path, value):
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(value, indent=2) + '\n')
    temp.replace(path)


def identity(pid):
    proc = Path('/proc') / str(pid)
    try:
        fields = (proc / 'stat').read_text().split(') ')[1].split()
        command = (proc / 'cmdline').read_bytes()
        return {'pid': pid, 'start_ticks': fields[19], 'state': fields[0],
                'cmdline_sha256': hashlib.sha256(command).hexdigest()}
    except FileNotFoundError:
        return None


def same(record):
    now = identity(record['pid'])
    return now and now['start_ticks'] == record['start_ticks'] and now['state'] != 'Z'


def send(record, sig):
    assert same(record), 'Controller identity changed'
    os.kill(record['pid'], sig)


def main():
    r = ROOT
    assert json.loads((r / 'concurrency-tests.json').read_text())['returncode'] == 0
    assert not (r / 'USER_STOP.json').exists()
    progress = json.loads((r / 'campaign-progress.json').read_text())
    assert progress['phase'] == 'wave_running'
    w = Path(progress['wave']); run = w / 'run'
    assert not (run / 'STOP_PROVIDER').exists()
    assert not (run / 'coordinator-finished.json').exists()
    current = json.loads((r / 'campaign-selection.json').read_text())
    assert current['source_commit'] == 'd899220'
    handoff = r / 'concurrency-upgrade-20261104'
    handoff.mkdir(mode=0o700, exist_ok=False)
    campaign = json.loads((r / 'campaign-launch.json').read_text())
    coordinator = json.loads((w / 'production-launch.json').read_text())
    campaign = identity(campaign['pid']) if same(campaign) else None
    coordinator = identity(coordinator['pid']) if same(coordinator) else None
    assert campaign and coordinator
    send(campaign, signal.SIGSTOP)
    send(coordinator, signal.SIGSTOP)
    # Only scheduling parents are stopped. Independent unit processes keep running.
    workers = []
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():
            continue
        try:
            argv = (p / 'cmdline').read_bytes().split(b'\0')
            if b'append_rewrite.terminus.production' not in argv or b'unit' not in argv or b'--output' not in argv:
                continue
            dest = Path(argv[argv.index(b'--output') + 1].decode())
            if dest.parent != run / 'units':
                continue
            record = identity(int(p.name))
            if record and record['state'] != 'Z':
                record.update(unit_id=dest.name, source_commit='d899220')
                workers.append(record)
        except (FileNotFoundError, ValueError):
            continue
    assert len(workers) <= 4
    for worker in workers:
        dest = run / 'units' / worker['unit_id']
        for _ in range(50):
            if dest.exists() or not same(worker):
                break
            time.sleep(.1)
        assert dest.exists(), 'Existing worker has not established its exclusive claim'
    claims = sorted(x.name for x in (run / 'units').iterdir())
    existing = {}
    for p in (run / 'units').glob('*/student/receipt.json'):
        existing[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    for p in (run / 'units').glob('*/student/train.jsonl'):
        existing[str(p)] = hashlib.sha256(p.read_bytes()).hexdigest()
    before = {'campaign': campaign, 'coordinator': coordinator, 'claims': claims,
              'existing_result_hashes': existing, 'workers': workers, 'checked_at': time.time()}
    dump(handoff / 'before.json', before)
    dump(handoff / 'adopt-workers.json', {'workers': workers})
    originals = {}
    for label, path in {'campaign-selection': r / 'campaign-selection.json',
                        'campaign-launch': r / 'campaign-launch.json',
                        'campaign-progress': r / 'campaign-progress.json',
                        'wave-selection': w / 'active_runtime_selection.json',
                        'coordinator-launch': w / 'production-launch.json',
                        'coordinator-state': run / 'coordinator.json'}.items():
        raw = path.read_bytes(); target = handoff / (label + '-before.json'); target.write_bytes(raw)
        originals[str(path)] = {'archive': str(target), 'sha256': hashlib.sha256(raw).hexdigest()}
    dump(handoff / 'originals.json', originals)
    for owner in [campaign, coordinator]:
        send(owner, signal.SIGTERM)
        if same(owner):
            send(owner, signal.SIGCONT)  # Deliver pending default SIGTERM; never signal units.
    for _ in range(100):
        if not same(campaign) and not same(coordinator):
            break
        time.sleep(.1)
    assert not same(campaign) and not same(coordinator)
    env = {**os.environ, 'PYTHONPATH': str(SOURCE / 'agentic/src'), 'PYTHONDONTWRITEBYTECODE': '1',
           'DOCKER_HOST': 'unix:///mnt/ecs-tb4/cli-gym-pilot-20261104/runtime/docker.sock',
           'DOCKER_API_VERSION': '1.44', 'DOCKER_CONFIG': str(r / 'docker-config'),
           'APPEND_REWRITE_STUDENT_POOL': str(w / 'student-pool'),
           'APPEND_REWRITE_SCORE_POOL': str(w / 'score-pool'), 'APPEND_REWRITE_STUDENT_CAPACITY': '8'}
    py = str(r / 'support/sdk/bin/python')

    def launch(argv, log_name, receipt):
        with (handoff / log_name).open('xb') as log:
            p = subprocess.Popen(argv, env=env, cwd=SOURCE, stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        rec = {**identity(p.pid), 'source_commit': COMMIT, 'source_root': str(SOURCE),
               'argv': argv, 'launched_at': time.time(), 'log': str(handoff / log_name),
               'automatic_retry': False}
        dump(receipt, rec)
        return rec

    selection = json.loads((w / 'active_runtime_selection.json').read_text())
    selection.update(source_root=str(SOURCE), source_commit=COMMIT, worker_capacity=8,
                     student_target=8, queue_policy='shared', score_prefill_concurrency=2,
                     handoff=str(handoff), adopted_workers=workers)
    dump(w / 'active_runtime_selection.json', selection)
    argv = [py, '-m', 'append_rewrite.terminus.production', 'batch', '--plan', str(w / 'prepared/plan.json'),
            '--discovery-summary', str(w / 'prepared/complete.json'), '--output', str(run),
            '--workers', '8', '--adopt-workers', str(handoff / 'adopt-workers.json')]
    for key, path in {'teacher-config': r / 'support/private/terminus-deepseek.json',
                      'fleet-config': r / 'support/private/fleet.json',
                      'tokenizer': r / 'support/tokenizers/qwen38-27b-1d4bf0f',
                      'sandbox-credentials': r / 'support/private/sandbox.env',
                      'runtime-assets': r / 'support/runtime-assets/tmux-linux-x86_64-v1'}.items():
        argv += ['--' + key, str(path)]
    new_coordinator = launch(argv, 'coordinator.log', w / 'production-launch.json')
    current.update(source_commit=COMMIT, source_root=str(SOURCE), worker_capacity=8,
                   student_target=8, queue_policy='shared', score_prefill_concurrency=2,
                   handoff=str(handoff), resume_current_wave=str(w),
                   source_binding_sha256=hashlib.sha256((r / 'concurrency-source-binding.json').read_bytes()).hexdigest())
    dump(r / 'campaign-selection.json', current)
    new_campaign = launch([py, str(SOURCE / 'agentic/experiments/cli-gym-scale-20261104/campaign.py'),
                           '--root', str(r), '--source-commit', COMMIT, '--workers', '8', '--resume'],
                          'campaign.log', r / 'campaign-launch.json')
    dump(r / 'concurrency-upgrade-selection.json', {
        'source_root': str(SOURCE), 'source_commit': COMMIT, 'handoff': str(handoff),
        'worker_capacity': 8, 'student_capacity': 8, 'score_capacity': 2, 'candidates_per_block': 8,
        'new_coordinator': new_coordinator, 'new_campaign': new_campaign,
        'old_model_attempts_replayed': 0, 'old_claims': claims, 'adopted_workers': workers})
    for path, checksum in existing.items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest() == checksum
    print(json.dumps({'handoff': str(handoff), 'adopted_workers': len(workers),
                      'old_claims_preserved': len(claims), 'new_coordinator_pid': new_coordinator['pid'],
                      'new_campaign_pid': new_campaign['pid'], 'worker_capacity': 8}))


if __name__ == '__main__':
    main()
