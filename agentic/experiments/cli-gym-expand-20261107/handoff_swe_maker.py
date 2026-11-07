"""One no-model maker handoff at idle or a pre-validation image-download boundary.

Never stop an active verifier. A download may be deferred with its source row
preserved; existing packages and every paid model process remain untouched.
"""
import hashlib
import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import time


def main(root, support, runtime, old, episode_timeout_sec, *, workers=None, repair_pytest_snail=False):
    helpers = runpy.run_path(str(runtime / 'agentic/experiments/cli-gym-expand-20261107/switch_teacher.py'))
    verify, identity, write = (helpers[k] for k in ['verify', 'identity', 'write'])
    assert not (support / 'handoff.json').exists()
    prepared = root / 'new-source-swegym/full-prepared-v2'
    assert str(prepared) in old['argv']
    initially_held = verify(old)['state'] == 'T'
    end = time.monotonic() + 1200
    stopped, deferred, download = False, None, None
    try:
        while time.monotonic() < end:
            verify(old)
            proc = Path('/proc') / str(old['pid'])
            children = [pid for task in (proc / 'task').iterdir()
                        for pid in (task / 'children').read_text().split()]
            progress = json.loads((prepared / 'progress.json').read_text())
            candidate = None
            threads = int(next(line.split(':')[1] for line in (proc / 'status').read_text().splitlines() if line.startswith('Threads:')))
            if len(children) == 1 and threads == 1:
                child = Path('/proc') / children[0]
                argv = [x.decode() for x in (child / 'cmdline').read_bytes().split(b'\0') if x]
                if len(argv) == 3 and Path(argv[0]).name == 'docker' and argv[1] == 'pull':
                    candidate = {**identity(int(children[0])), 'argv': argv}
            idle = progress.get('phase') in ('queue_full', 'storage_hold') and not children
            if idle or candidate:
                os.kill(old['pid'], signal.SIGSTOP)
                stopped = True
                verify(old)
                now_children = [pid for task in (proc / 'task').iterdir()
                                for pid in (task / 'children').read_text().split()]
                if idle and not now_children and (proc / 'syscall').read_text().split()[0] == '230':
                    break
                if candidate and now_children == [str(candidate['pid'])]:
                    current = identity(candidate['pid'])
                    if current['start_ticks'] == candidate['start_ticks'] and current['cmdline_sha256'] == candidate['cmdline_sha256']:
                        matches = []
                        for folder in prepared.iterdir():
                            if not folder.is_dir() or {p.name for p in folder.iterdir()} != {'source-row.json'}:
                                continue
                            row = json.loads((folder / 'source-row.json').read_text())
                            expected = 'xingyaoww/sweb.eval.x86_64.' + row['instance_id'].replace('__', '_s_').lower()
                            if expected == candidate['argv'][2]:
                                matches.append(folder)
                        if len(matches) == 1:
                            download, deferred = candidate, matches[0].name
                            break
                if initially_held:
                    raise RuntimeError('Existing source hold is not an idle handoff boundary')
                os.kill(old['pid'], signal.SIGCONT)
                stopped = False
            write(support / 'progress.json', {'phase': 'waiting_for_safe_maker_boundary', 'old_pid': old['pid'], 'at': time.time(), 'new_model_requests': 0})
            time.sleep(3)
        else:
            raise TimeoutError('No idle/download boundary; no second maker launched')
        proc = Path('/proc') / str(old['pid'])
        env = dict(x.decode().split('=', 1) for x in (proc / 'environ').read_bytes().split(b'\0') if x)
        hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for folder in prepared.iterdir()
                  if folder.is_dir() for p in folder.rglob('*') if p.is_file()}
        write(support / 'original-package-hashes.json', hashes)
        old_progress = json.loads((prepared / 'progress.json').read_text())
        write(support / 'before.json', {'old': old, 'old_progress': old_progress,
              'deferred_unpaid_download': deferred, 'download': download})
        if download:
            current = identity(download['pid'])
            assert current['start_ticks'] == download['start_ticks']
            if current['state'] != 'Z':
                verify(download)
                os.kill(download['pid'], signal.SIGTERM)
        verify(old)
        os.kill(old['pid'], signal.SIGTERM)
        os.kill(old['pid'], signal.SIGCONT)
        stopped = False
        for owner in [old, *([download] if download else [])]:
            until = time.monotonic() + 15
            while time.monotonic() < until:
                try:
                    if identity(owner['pid'])['state'] == 'Z':
                        break
                except FileNotFoundError:
                    break
                time.sleep(.1)
            else:
                raise RuntimeError('Old owner remains alive; no replacement launched')
        if deferred:
            old_progress.setdefault('held', []).append({'task_id': deferred,
                'type': 'UnpaidDownloadDeferredForRuntimeHandoff',
                'message': str(support / 'before.json')})
            write(prepared / 'progress.json', old_progress)
        argv = old['argv'].copy()
        argv[1] = str(runtime / 'agentic/experiments/cli-gym-expand-20261107/prepare_swegym.py')
        options = {'--episode-timeout-sec': episode_timeout_sec}
        if workers is not None:
            options['--workers'] = workers
        for option, value in options.items():
            if option in argv:
                argv[argv.index(option) + 1] = str(value)
            else:
                argv += [option, str(value)]
        if repair_pytest_snail and '--repair-pytest-snail' not in argv:
            argv.append('--repair-pytest-snail')
        scratch = support / 'tmp'
        scratch.mkdir(exist_ok=True)
        env.update(PYTHONPATH=str(runtime / 'agentic/src'), PYTHONDONTWRITEBYTECODE='1', TMPDIR=str(scratch))
        with (support / 'maker.log').open('xb') as log:
            child = subprocess.Popen(argv, env=env, stdin=subprocess.DEVNULL, stdout=log, stderr=log, start_new_session=True)
        new = {**identity(child.pid), 'argv': argv, 'started_at': time.time()}
        write(support / 'maker-launch.json', new)
        changes = [p for p, checksum in hashes.items() if hashlib.sha256(Path(p).read_bytes()).hexdigest() != checksum]
        report = {'at': time.time(), 'old_maker_exited': True, 'new_maker': new,
                  'original_package_files': len(hashes), 'original_package_changes': changes,
                  'new_episode_timeout_sec': episode_timeout_sec, 'preparation_workers': workers,
                  'deferred_unpaid_download': deferred,
                  'model_workers_signalled': 0, 'model_replays': 0, 'only_future_packages_changed': True}
        write(support / 'handoff.json', report)
        assert not changes
        write(root / 'new-source-swegym/active_maker_selection.json', {
            'runtime': str(runtime), 'launch': str(support / 'maker-launch.json'),
            'handoff': str(support / 'handoff.json'), 'episode_timeout_sec': episode_timeout_sec})
        print(json.dumps(report), flush=True)
    finally:
        if stopped and not initially_held:
            verify(old)
            os.kill(old['pid'], signal.SIGCONT)
