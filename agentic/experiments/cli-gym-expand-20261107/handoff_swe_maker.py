"""One finite no-model maker handoff, only at a verified idle queue boundary."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import time


def main(root, support, runtime, old, episode_timeout_sec):
    helpers = runpy.run_path(str(runtime / 'agentic/experiments/cli-gym-expand-20261107/switch_teacher.py'))
    verify, identity, write = (helpers[k] for k in ['verify', 'identity', 'write'])
    assert not (support / 'handoff.json').exists()
    assert (root / 'new-source-swegym/full-prepared-v2').as_posix() in old['argv']
    verify(old)
    end = time.monotonic() + 1200
    stopped = False
    try:
        while time.monotonic() < end:
            verify(old)
            p = root / 'new-source-swegym/full-prepared-v2/progress.json'
            phase = json.loads(p.read_text()).get('phase')
            if phase in ('queue_full', 'storage_hold') and time.time() - p.stat().st_mtime < 20:
                os.kill(old['pid'], signal.SIGSTOP)
                stopped = True
                verify(old)
                proc = Path('/proc') / str(old['pid'])
                children = (proc / 'task' / str(old['pid']) / 'children').read_text().strip()
                # Linux x86_64 clock_nanosleep: the published hold is actually idle.
                syscall = (proc / 'syscall').read_text().split()[0]
                if not children and syscall == '230':
                    break
                os.kill(old['pid'], signal.SIGCONT)
                stopped = False
            write(support / 'progress.json', {'phase': 'waiting_for_idle_maker', 'old_pid': old['pid'], 'at': time.time(), 'new_model_requests': 0})
            time.sleep(5)
        else:
            raise TimeoutError('Maker stayed busy; no second maker launched')
        proc = Path('/proc') / str(old['pid'])
        env = dict(x.decode().split('=', 1) for x in (proc / 'environ').read_bytes().split(b'\0') if x)
        prepared = root / 'new-source-swegym/full-prepared-v2'
        hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for folder in prepared.iterdir()
                  if folder.is_dir() for p in folder.rglob('*') if p.is_file()}
        write(support / 'original-package-hashes.json', hashes)
        write(support / 'before.json', {'old': old, 'idle_children': children, 'idle_syscall': syscall})
        os.kill(old['pid'], signal.SIGTERM)
        os.kill(old['pid'], signal.SIGCONT)
        stopped = False
        until = time.monotonic() + 15
        while time.monotonic() < until:
            try:
                if identity(old['pid'])['state'] == 'Z':
                    break
            except FileNotFoundError:
                break
            time.sleep(.1)
        else:
            raise RuntimeError('Old maker did not exit; no replacement launched')
        argv = old['argv'].copy()
        argv[1] = str(runtime / 'agentic/experiments/cli-gym-expand-20261107/prepare_swegym.py')
        argv += ['--episode-timeout-sec', str(episode_timeout_sec)]
        env.update(PYTHONPATH=str(runtime / 'agentic/src'), PYTHONDONTWRITEBYTECODE='1')
        with (support / 'maker.log').open('xb') as log:
            child = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        new = {**identity(child.pid), 'argv': argv, 'started_at': time.time()}
        write(support / 'maker-launch.json', new)
        changes = [p for p, checksum in hashes.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest() != checksum]
        report = {'at': time.time(), 'old_maker_exited': True, 'new_maker': new,
                  'original_package_files': len(hashes), 'original_package_changes': changes,
                  'new_episode_timeout_sec': episode_timeout_sec, 'model_workers_signalled': 0,
                  'model_replays': 0, 'only_future_packages_changed': True}
        write(support / 'handoff.json', report)
        assert not changes
        write(root / 'new-source-swegym/active_maker_selection.json', {
            'runtime': str(runtime), 'launch': str(support / 'maker-launch.json'),
            'handoff': str(support / 'handoff.json'), 'episode_timeout_sec': episode_timeout_sec})
        print(json.dumps(report), flush=True)
    finally:
        if stopped:
            verify(old)
            os.kill(old['pid'], signal.SIGCONT)
