"""One-shot, identity-checked rolling teacher-route handoff on ECS.

Run only after the selected route probe passes. Freeze this operator before use.
Existing paid unit processes are adopted, never signalled or replayed.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time


def read(path):
    return json.loads(path.read_text())


def write(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2) + '\n')
    tmp.replace(path)


def identity(pid):
    p = Path('/proc') / str(pid)
    fields = (p / 'stat').read_text().split(') ')[1].split()
    command = (p / 'cmdline').read_bytes()
    return {'pid': pid, 'start_ticks': fields[19],
            'cmdline_sha256': hashlib.sha256(command).hexdigest(),
            'state': fields[0], 'ppid': int(fields[1])}


def verify(receipt):
    actual = identity(receipt['pid'])
    assert actual['start_ticks'] == receipt['start_ticks']
    assert actual['state'] != 'Z'
    argv = (Path('/proc') / str(receipt['pid']) / 'cmdline').read_bytes().split(b'\0')[:-1]
    assert [a.decode() for a in argv] == receipt['argv']
    return actual


def main(root, support_dir=None):
    x = support_dir or root / 'support/mint-im-switch-20261107'
    assert x.resolve().is_relative_to((root / 'support').resolve())
    request = read(x / 'handoff-request.json') if (x / 'handoff-request.json').exists() else {}
    runtime = Path(request.get('runtime', x / 'runtime'))
    binding = Path(request.get('runtime_binding', x / 'runtime-binding.json'))
    assert read(Path(request.get('probe_result', x / 'probe-result.json')))['passed']
    assert not (root / 'production/STOP_PROVIDER').exists()
    assert not (x / 'handoff.json').exists(), 'One-shot operator; inspect prior evidence'
    for rel, digest in read(binding)['files'].items():
        assert hashlib.sha256((runtime / rel).read_bytes()).hexdigest() == digest
    coordinator = read(root / 'coordinator-launch.json')
    producer = read(root / 'acquisition-env-repairs-launch.json')
    owners = [producer, coordinator]
    for owner in owners:
        verify(owner)
    envs = []
    for owner in owners:
        raw = (Path('/proc') / str(owner['pid']) / 'environ').read_bytes()
        envs.append(dict(v.decode().split('=', 1) for v in raw.split(b'\0') if v))
    stopped = []
    try:
        for owner in owners:
            verify(owner)
            os.kill(owner['pid'], signal.SIGSTOP)
            stopped.append(owner)
        workers = []
        for p in Path('/proc').iterdir():
            if not p.name.isdigit():
                continue
            try:
                actual = identity(int(p.name))
                if actual['ppid'] != coordinator['pid'] or actual['state'] == 'Z':
                    continue
                argv = (p / 'cmdline').read_bytes().decode().strip('\0').split('\0')
                assert argv[1:4] == ['-m', 'append_rewrite.terminus.production', 'unit']
                output = Path(argv[argv.index('--output') + 1])
                assert output.parent == root / 'production/units'
                workers.append({**actual, 'unit_id': output.name, 'output': str(output)})
            except FileNotFoundError:
                continue
        # A second handoff must retain still-live workers adopted by the first
        # coordinator too; their PPID is1, not the current coordinator PID.
        old_argv = coordinator['argv']
        if '--adopt-workers' in old_argv:
            previous = read(Path(old_argv[old_argv.index('--adopt-workers') + 1]))['workers']
            for worker in previous:
                try:
                    actual = identity(worker['pid'])
                except FileNotFoundError:
                    continue
                if actual['start_ticks'] != worker['start_ticks'] or actual['state'] == 'Z':
                    continue
                assert actual['cmdline_sha256'] == worker['cmdline_sha256']
                if worker['pid'] not in {w['pid'] for w in workers}:
                    workers.append(worker)
        assert len(workers) <= 16
        write(x / 'adopt-workers.json', {'workers': workers})
        write(x / 'before.json', {'coordinator': coordinator, 'producer': producer,
                                 'workers': workers, 'selection': read(root / 'active_runtime_selection.json')})
        for owner in owners:
            verify(owner)
            os.kill(owner['pid'], signal.SIGTERM)
            os.kill(owner['pid'], signal.SIGCONT)
        for owner in owners:
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                try:
                    if identity(owner['pid'])['state'] == 'Z':
                        break
                except FileNotFoundError:
                    break
                time.sleep(.1)
            else:
                raise RuntimeError('Old owner did not exit; no duplicate launched')
        stopped.clear()
        for worker in workers:
            try:
                now = identity(worker['pid'])
                assert now['start_ticks'] == worker['start_ticks']
                assert now['cmdline_sha256'] == worker['cmdline_sha256']
            except FileNotFoundError:
                pass  # Normal completion during handoff; adoption accounts for it.
        def launch(argv, env, logname):
            with (x / logname).open('xb') as log:
                p = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL,
                                     stdout=log, stderr=log, start_new_session=True)
            return {**identity(p.pid), 'argv': argv, 'started_at': time.time()}
        argv = coordinator['argv'].copy()
        argv[argv.index('--teacher-config') + 1] = str(request.get('teacher_config', x / 'teacher-private.json'))
        if 'fleet_config' in request:
            argv[argv.index('--fleet-config') + 1] = request['fleet_config']
        if '--adopt-workers' in argv:
            argv[argv.index('--adopt-workers') + 1] = str(x / 'adopt-workers.json')
        else:
            argv += ['--adopt-workers', str(x / 'adopt-workers.json')]
        env = dict(envs[1], PYTHONPATH=str(runtime / 'agentic/src'), PYTHONDONTWRITEBYTECODE='1')
        new = launch(argv, env, 'coordinator.log')
        new['source_root'] = str(runtime)
        new['base_source_commit'], new['teacher_patch_commit'] = '3fbaa08', '43b16ee'
        new['additional_patch_commits'] = request.get('additional_patch_commits', [])
        write(root / 'coordinator-launch.json', new)
        handoff = {'old_producer_exited': True, 'old_coordinator_exited': True,
                   'retained_preparation_launch': str(root / 'pool-mirror-preparation-launch.json'),
                   'old': str(x / 'before.json'), 'new_coordinator': new,
                   'automatic_paid_retry': False, 'adopted_worker_count': len(workers)}
        write(x / 'handoff.json', handoff)
        write(root / 'producer-handoff-selection.json', {
            'path': str(x / 'handoff.json'),
            'sha256': hashlib.sha256((x / 'handoff.json').read_bytes()).hexdigest()})
        new_producer = launch(producer['argv'], envs[0], 'producer.log')
        new_producer['source_commit'] = producer['source_commit']
        write(root / 'acquisition-env-repairs-launch.json', new_producer)
        selection = read(root / 'active_runtime_selection.json')
        selection.update(coordinator_source_commit=request.get('source_identity', '3fbaa08+teacher-43b16ee'),
                         coordinator_handoff=str(x / 'handoff.json'))
        if not request:
            selection.update(teacher_route_policy=str(x / 'policy.json'),
                             teacher_route_handoff=str(x / 'handoff.json'))
        write(root / 'active_runtime_selection.json', selection)
        print(json.dumps({'coordinator_pid': new['pid'], 'producer_pid': new_producer['pid'],
                          'adopted_workers': len(workers), 'worker_capacity': 16}))
    finally:
        for owner in stopped:
            try:
                verify(owner)
                os.kill(owner['pid'], signal.SIGCONT)
            except (FileNotFoundError, AssertionError):
                pass


if __name__ == '__main__':
    main(Path(sys.argv[1]), Path(sys.argv[2]) if len(sys.argv) > 2 else None)
