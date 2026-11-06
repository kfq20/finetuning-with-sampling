"""One zero-inference startup repair; reuse frozen tasks and original controls."""
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import time

import toml
import tomllib


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec); spec.loader.exec_module(value)
    return value


def build_runtime(root):
    """Bundle existing public system binaries with their own loader; no host install."""
    binary = Path('/usr/bin/tmux')
    raw = subprocess.check_output(['ldd', str(binary)], text=True)
    libs = sorted(set(re.findall(r'(/[^\s()]+)', raw)))
    loader = next(p for p in libs if 'ld-linux' in p)
    files = {'tmux.real': binary, 'ld-linux-x86-64.so.2': Path(loader)}
    files.update({'lib/' + Path(p).name: Path(p) for p in libs})
    wrapper = (b'#!/bin/sh\nexport TERMINFO=/opt/swe-runtime/terminfo\n'
               b'exec /opt/swe-runtime/ld-linux-x86-64.so.2 '
               b'--library-path /opt/swe-runtime/lib /opt/swe-runtime/tmux.real "$@"\n')
    data = io.BytesIO()
    manifest = {}
    with tarfile.open(fileobj=data, mode='w:gz') as archive:
        for name, path in files.items():
            payload = path.read_bytes(); info = tarfile.TarInfo(name)
            info.mode, info.size = 0o755, len(payload)
            archive.addfile(info, io.BytesIO(payload))
            manifest[name] = hashlib.sha256(payload).hexdigest()
        for name in ('x/xterm', 'x/xterm-256color', 's/screen', 's/screen-256color', 't/tmux', 't/tmux-256color'):
            source = Path('/lib/terminfo') / name
            if not source.exists():
                source = Path('/usr/share/terminfo') / name
            if source.exists():
                payload = source.read_bytes(); info = tarfile.TarInfo('terminfo/' + name)
                info.mode, info.size = 0o644, len(payload)
                archive.addfile(info, io.BytesIO(payload))
        info = tarfile.TarInfo('bin/tmux'); info.mode, info.size = 0o755, len(wrapper)
        archive.addfile(info, io.BytesIO(wrapper))
    target = root / 'offline-runtime.tar.gz'; target.write_bytes(data.getvalue())
    (root / 'offline-runtime-source.json').write_text(json.dumps({
        'host_os': Path('/etc/os-release').read_text(), 'binaries_sha256': manifest,
        'archive_sha256': hashlib.sha256(data.getvalue()).hexdigest(),
        'source': 'Existing Ubuntu system packages, separately loaded; no global changes'}, indent=2))
    return target


def main(parent, root):
    os.umask(0o077)
    entry = Path(__file__).parent
    run = module('swe_pilot', entry / 'run.py')
    assert not (root / 'plan.json').exists(), 'Never restart a prepared repair'
    assert (parent / 'zero-inference-startup-hold.json').exists()
    assert not list(parent.glob('*/jobs/*/*/native-generation/turn-*/intent.json'))
    prior = json.loads((parent / 'admission.json').read_text())
    assert len(prior['tasks']) == 5
    runtime = build_runtime(root)
    shutil.copytree(parent / 'runtime', root / 'runtime', copy_function=os.link)
    shutil.copytree(parent / 'prepared-tasks', root / 'prepared-tasks')
    plan = json.loads((parent / 'plan.json').read_text())
    plan.update(parent_zero_inference_root=str(parent),
                environment_import_path='swe_runtime:PreparedSWEEnvironment',
                offline_runtime_sha256=run.sha(runtime))
    run.dump(root / 'plan.json', plan)
    for task in (root / 'prepared-tasks').iterdir():
        old_results = [(p, r) for p, r in run.trial_rows(parent / 'controls/control-nop')
                       if r['task_name'] == task.name]
        assert len(old_results) == 1
        alias = re.search(r'Creating template (tb21ali-v2-[a-f0-9]+)',
                          (old_results[0][0].parent / 'trial.log').read_text()).group(1)
        cfg = tomllib.loads((task / 'task.toml').read_text())
        old_cfg = copy.deepcopy(cfg)
        cfg['environment']['env']['PATH'] = '/opt/swe-runtime/bin:' + cfg['environment']['env']['PATH']
        (task / 'task.toml').write_text(toml.dumps(cfg))
        shutil.copyfile(runtime, task / 'environment/runtime.tar.gz')
        run.dump(task / 'environment/runtime.json', {
            'base_image': cfg['environment']['docker_image'], 'base_template_alias': alias,
            'archive_sha256': run.sha(runtime)})
        for relative, expected in prior['tasks'].get(task.name, {}).get('files', {}).items():
            if relative != 'task.toml':
                assert run.sha(task / relative) == expected
        compare = copy.deepcopy(cfg); compare['environment']['env']['PATH'] = old_cfg['environment']['env']['PATH']
        assert compare == old_cfg
    cfg = json.loads((run.PRIOR / 'base/full-config.json').read_text())
    cfg.update(job_name='runtime-install-only', jobs_dir=str(root / 'preflight'), install_only=True,
               tasks=[{'path': str(root / 'prepared-tasks' / t)} for t in prior['tasks']],
               n_concurrent_trials=3, n_attempts=1, retry={'max_retries': 0})
    cfg['environment']['import_path'] = plan['environment_import_path']
    cfg['agents'][0]['kwargs']['inference_profile'] = 'cancellable-legacy'
    assert run.invoke(root, cfg, 'runtime-install-only') == 0
    installs = run.trial_rows(root / 'preflight/runtime-install-only')
    assert len(installs) == 5
    assert all(r.get('finished_at') and not r.get('exception_info') for _, r in installs)
    assert all((p.parent / 'offline-runtime.json').exists() for p, _ in installs)
    assert not list(root.glob('preflight/*/*/native-generation/turn-*/intent.json'))
    # Actual NOP/gold check after adding the offline tool runtime; other exact
    # original grader/source controls stay explicitly bound and reused.
    first = root / 'prepared-tasks' / next(iter(prior['tasks']))
    checks = {}
    for agent, expected in [('nop', 0), ('oracle', 1)]:
        name = 'runtime-check-' + agent
        check = run.config(root, agent, [first], name)
        check['environment']['import_path'] = plan['environment_import_path']
        run.invoke(root, check, name)
        rows = run.trial_rows(root / 'controls' / name)
        assert len(rows) == 1 and run.valid(rows[0][1])
        assert rows[0][1]['verifier_result']['rewards']['reward'] == expected
        checks[agent] = {'result_path': str(rows[0][0]), 'sha256': run.sha(rows[0][0])}
    proof = {'at': time.time(), 'passed': True, 'no_model_requests': True,
             'actual_harness_installs': [{'task': r['task_name'], 'result_sha256': run.sha(p)}
                                        for p, r in installs], 'controls': checks}
    run.dump(root / 'runtime-preflight.json', proof)
    admission = copy.deepcopy(prior)
    admission.update(at=time.time(), parent_admission_sha256=run.sha(parent / 'admission.json'),
                     runtime_preflight_sha256=run.sha(root / 'runtime-preflight.json'))
    for name, evidence in admission['tasks'].items():
        task = root / 'prepared-tasks' / name
        evidence['files'] = {str(p.relative_to(task)): run.sha(p) for p in task.rglob('*') if p.is_file()}
    run.dump(root / 'admission.json', admission)
    assert not list(parent.glob('*/jobs/*/*/native-generation/turn-*/intent.json'))
    run.models(root)
    module('swe_analysis', entry / 'analyze.py').main(root)


if __name__ == '__main__':
    try:
        main(Path(sys.argv[1]), Path(sys.argv[2]))
    except BaseException as error:
        Path(sys.argv[2], 'hold.json').write_text(json.dumps({'at': time.time(),
            'error_type': type(error).__name__, 'message': str(error)[:300] if isinstance(error, AssertionError) else ''}))
        raise
