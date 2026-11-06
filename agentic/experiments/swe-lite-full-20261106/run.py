"""Finite full SWE-Lite evaluation: independent task gates and three model queues."""
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
import copy
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import threading


PILOT = Path('/mnt/ecs-tb4/evaluations/qwen38-swe-lite-dev6-20261106-a2')
SDK = '/mnt/ecs-tb4/cli-gym-scale-20261104/support/sdk/bin/python'
LAUNCHER = '/mnt/ecs-tb4/evaluations/qwen38-tb21-base-20261104/oracle-launcher-v2.py'
CRANE = '/mnt/ecs-tb4/relayforge_scenario_deepseek_aliyun_20261028_v1/bin/crane'
REGISTRY = 'acr-rf-sg-registry.ap-southeast-8.cr.aliyuncs.com'
ARMS = ('base', 'method', 'expert')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix('.pending')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.replace(path)


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod


def ordered(rows):
    groups = {}
    for row in sorted(rows, key=lambda r: r['instance_id']):
        groups.setdefault(row['repo'], []).append(row)
    return [group[i] for i in range(max(map(len, groups.values())))
            for group in groups.values() if i < len(group)]


def valid(row):
    reward = (row.get('verifier_result') or {}).get('rewards', {}).get('reward')
    return bool(row.get('finished_at') and not row.get('exception_info') and reward in (0, 1))


class Campaign:
    def __init__(self, root):
        self.root = root
        self.plan = json.loads((root / 'plan.json').read_text())
        self.pilot = load('pilot', root / 'runtime/source/agentic/experiments/swe-lite-dev-20261106/run.py')
        self.models = json.loads((root / 'models.json').read_text())
        self.env = {**os.environ, 'DOCKER_CONFIG': str(root / 'private/registry-auth')}
        self.template_locks = {}
        self.template_guard = threading.Lock()

    def crane(self, *args):
        result = subprocess.run([CRANE, *args], env=self.env, capture_output=True, text=True, timeout=1200)
        if result.returncode:
            # Do not expose credentials or signed storage URLs in status receipts.
            raise RuntimeError('Registry operation failed: ' + args[0])
        return result.stdout.strip()

    def invoke(self, cfg, location):
        location.mkdir(parents=True, exist_ok=True)
        path = location / 'config.json'
        assert not path.exists(), 'Never repeat an existing job'
        dump(path, cfg)
        with (location / 'harbor.log').open('x') as log:
            child = subprocess.Popen([SDK, str(self.root / 'reference/launcher.py'), str(path)], stdout=log, stderr=log)
            dump(location / 'launch.json', {'pid': child.pid, 'at': time.time(),
                 'start_ticks': Path(f'/proc/{child.pid}/stat').read_text().split()[21]})
            code = child.wait()
        records = list(Path(cfg['jobs_dir'], cfg['job_name']).glob('*/result.json'))
        assert len(records) == 1, 'Single task did not produce one result'
        record = json.loads(records[0].read_text())
        return records[0], record, code

    def base_config(self, task, name, destination):
        cfg = json.loads((self.root / 'reference/base-config.json').read_text())
        cfg.update(job_name=name, jobs_dir=str(destination), tasks=[{'path': str(task)}],
                   n_concurrent_trials=1, n_attempts=1, retry={'max_retries': 0})
        cfg['agents'][0]['kwargs']['native_config'] = str(self.root / 'private/base.json')
        return cfg

    def storage_ready(self):
        while shutil.disk_usage(self.root).free < 2 * 1024**3:
            dump(self.root / 'storage-hold.json', {'at': time.time(), 'free_bytes': shutil.disk_usage(self.root).free,
                                                 'new_dispatch_paused': True})
            if (self.root / 'STOP').exists():
                raise RuntimeError('Dispatch stopped')
            time.sleep(30)
        if (self.root / 'STOP').exists():
            raise RuntimeError('Dispatch stopped')

    def gate(self, row):
        import toml
        import tomllib
        self.storage_ready()
        name = row['instance_id']; stage = self.root / 'gates' / name
        stage.mkdir(parents=True)
        task = self.root / 'dataset/tasks' / name
        image = row['image']
        digest = self.crane('digest', '--platform', 'linux/amd64', image)
        repository = image.rsplit(':', 1)[0]
        target = REGISTRY + '/mindlab/test:fanqi-swelite-full-1106-' + digest[7:31]
        self.crane('copy', '--platform', 'linux/amd64', repository + '@' + digest, target)
        assert self.crane('digest', target) == digest
        cfg = tomllib.loads((task / 'task.toml').read_text())
        mirrored = REGISTRY + '/mindlab/test@' + digest
        cfg['environment']['docker_image'] = mirrored
        cfg['environment']['env']['PATH'] = '/opt/swe-runtime/bin:' + cfg['environment']['env']['PATH']
        cfg['verifier']['timeout_sec'] = 1800
        (task / 'task.toml').write_text(toml.dumps(cfg))
        # Grading runs in the base Python; official eval activates its own pinned
        # testbed interpreter. No test source or required check is changed.
        (task / 'tests/test.sh').write_text('#!/bin/bash\nset -euo pipefail\nexport PYTHONPATH=/tests\n'
            '/opt/miniconda3/bin/python /tests/grade.py /tests /logs/verifier 1740\n')
        os.link(self.root / 'offline-runtime.tar.gz', task / 'environment/runtime.tar.gz')
        dump(task / 'environment/runtime.json', {'base_image': mirrored,
             'base_template_alias': 'swefull1106-' + digest[7:27],
             'archive_sha256': sha(self.root / 'offline-runtime.tar.gz')})
        dump(stage / 'image.json', {'source_image': image, 'digest': digest, 'mirrored_image': mirrored})
        proof = {}
        for agent, expected in [('install', None), ('nop', 0), ('oracle', 1)]:
            c = self.base_config(task, agent, stage / 'jobs')
            if agent == 'install':
                c['install_only'] = True
            else:
                c['agents'] = [{'name': agent}]
            if agent == 'install':
                with self.template_guard:
                    template_lock = self.template_locks.setdefault(digest, threading.Lock())
                with template_lock:
                    p, result, code = self.invoke(c, stage / agent)
            else:
                p, result, code = self.invoke(c, stage / agent)
            assert result['task_name'] == name and result.get('finished_at')
            assert not result.get('exception_info'), 'Environment/harness/control execution failed'
            if agent == 'install':
                assert (p.parent / 'offline-runtime.json').exists()
                assert not list(p.parent.glob('native-generation/turn-*/intent.json'))
            else:
                assert valid(result), 'Invalid grading result'
                assert result['verifier_result']['rewards']['reward'] == expected, 'NOP/gold control mismatch'
            proof[agent] = {'result_path': str(p), 'result_sha256': sha(p), 'returncode': code}
        receipt = {'at': time.time(), 'task': name, 'passed': True, 'controls': proof,
                   'task_path': str(task), 'files': {str(p.relative_to(task)): sha(p)
                                                for p in task.rglob('*') if p.is_file()}}
        dump(stage / 'admission.json', receipt)
        return receipt

    def check_deployment(self, arm):
        import httpx
        private = self.root / 'private' / (arm + '.json')
        assert sha(private) == self.models[arm]['private_config_sha256']
        config = json.loads(private.read_text())
        with httpx.Client(timeout=30, trust_env=False) as client:
            response = client.get(config['base_url'].rstrip('/') + '/api/fleet/v1/deployments/' + config['task_id'],
                                  headers={'x-api-key': config['api_key']})
            response.raise_for_status(); live = response.json()
        expected = self.models[arm]
        assert live['model_id'] == expected['model_id'] and live['source'] == expected['source']
        assert live['base_model'] == 'Qwen/Qwen3.8-27B' and live['state'] in ('serving', 'succeeded')
        assert live.get('checkpoint') == expected.get('checkpoint'), 'Selected checkpoint changed'

    def sample(self, arm, admission):
        self.storage_ready()
        name = admission['task']; task = Path(admission['task_path'])
        for relative, expected in admission['files'].items():
            assert sha(task / relative) == expected
        self.check_deployment(arm)
        location = self.root / arm / name
        assert not (location / 'claim.json').exists()
        dump(location / 'claim.json', {'at': time.time(), 'arm': arm, 'task': name,
             'admission_sha256': sha(self.root / 'gates' / name / 'admission.json'), 'automatic_retry': False})
        cfg = self.base_config(task, 'pass1', location / 'jobs')
        cfg['agents'] = copy.deepcopy(json.loads((self.root / 'reference' / (arm + '-config.json')).read_text())['agents'])
        cfg['agents'][0]['kwargs']['native_config'] = str(self.root / 'private' / (arm + '.json'))
        p, result, code = self.invoke(cfg, location)
        receipt = {'at': time.time(), 'arm': arm, 'task': name, 'result_path': str(p),
                   'result_sha256': sha(p), 'valid': valid(result),
                   'resolved': int(result['verifier_result']['rewards']['reward'] == 1) if valid(result) else None,
                   'exception_type': (result.get('exception_info') or {}).get('exception_type'), 'returncode': code}
        dump(location / 'receipt.json', receipt)
        return receipt

    def collect(self, gate_pending, model_pending):
        summary = {'at': time.time(), 'split': self.plan['split'], 'cohort': self.plan['cohort'],
                   'pending_gate_jobs': gate_pending, 'pending_model_jobs': model_pending, 'arms': {}}
        admitted = list((self.root / 'gates').glob('*/admission.json'))
        held = list((self.root / 'gates').glob('*/hold.json'))
        summary.update(admitted=len(admitted), preflight_held=len(held))
        for arm in ARMS:
            rows = [json.loads(p.read_text()) for p in (self.root / arm).glob('*/receipt.json')]
            summary['arms'][arm] = {'planned_max': self.plan['cohort'], 'ended': len(rows),
                'valid': sum(r['valid'] for r in rows), 'resolved': sum(r['resolved'] == 1 for r in rows),
                'errors_unknown': sum(not r['valid'] for r in rows),
                'claimed': len(list((self.root / arm).glob('*/claim.json'))),
                'pre_model_held': sum(not (p.parent / 'claim.json').exists() for p in (self.root / arm).glob('*/hold.json')),
                'claimed_without_result_holds': sum((p.parent / 'claim.json').exists() and not (p.parent / 'receipt.json').exists() for p in (self.root / arm).glob('*/hold.json'))}
        dump(self.root / 'progress.json', summary)
        return summary

    def run(self):
        with (self.root / 'controller.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.run_locked()

    def run_locked(self):
        assert not (self.root / 'controller-claim.json').exists(), 'No controller restart/replay'
        for relative, expected in json.loads((self.root / 'source-files.json').read_text()).items():
            assert sha(self.root / relative) == expected
        for arm in ARMS:
            self.check_deployment(arm)
        dump(self.root / 'controller-claim.json', {'at': time.time(), 'scope': self.plan['split'], 'automatic_paid_retry': False})
        rows = ordered(json.loads((self.root / 'source/rows.json').read_text()))
        with ThreadPoolExecutor(max_workers=4) as gates, \
             ThreadPoolExecutor(max_workers=4) as base, \
             ThreadPoolExecutor(max_workers=4) as method, \
             ThreadPoolExecutor(max_workers=4) as expert:
            pools = {'base': base, 'method': method, 'expert': expert}
            pending = {gates.submit(self.gate, row): ('gate', row['instance_id']) for row in rows}
            while pending:
                done, _ = wait(pending, timeout=15, return_when=FIRST_COMPLETED)
                for future in done:
                    kind, name = pending.pop(future)
                    try:
                        result = future.result()
                    except Exception as error:
                        path = self.root / ('gates' if kind == 'gate' else kind) / name / 'hold.json'
                        dump(path, {'at': time.time(), 'type': type(error).__name__,
                             'reason': str(error)[:180] if isinstance(error, AssertionError) else '',
                             'automatic_retry': False, 'valid_completion': False})
                        continue
                    if kind == 'gate':
                        for arm in ARMS:
                            pending[pools[arm].submit(self.sample, arm, result)] = (arm, name)
                self.collect(sum(k == 'gate' for k, _ in pending.values()),
                             sum(k != 'gate' for k, _ in pending.values()))
        dump(self.root / 'finished.json', self.collect(0, 0))


if __name__ == '__main__':
    try:
        Campaign(Path(sys.argv[1])).run()
    except BaseException as error:
        dump(Path(sys.argv[1]) / 'controller-hold.json', {'at': time.time(), 'type': type(error).__name__})
        raise
