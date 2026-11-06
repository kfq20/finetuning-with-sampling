"""One authorized retry of each original Fleet AgentTimeout; no other replay."""
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

ARMS = ('base', 'method', 'expert')
PRIOR = Path('/mnt/ecs-tb4/evaluations/qwen38-paired531-sft-20261105-a1')
PYTHON = '/mnt/ecs-tb4/cli-gym-scale-20261104/support/sdk/bin/python'
LAUNCHER = '/mnt/ecs-tb4/evaluations/qwen38-tb21-base-20261104/oracle-launcher-v2.py'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def dump(path, value):
    path.write_text(json.dumps(value, indent=2) + '\n')


def extended(original):
    value = json.loads(json.dumps(original))
    assert value['agent']['timeout_sec'] > 0
    value['agent']['timeout_sec'] *= 4
    return value


def timeout_selection(root):
    rows = {}
    results = list(root.glob('jobs/*/*/result.json'))
    assert len(results) == 89, 'Original cohort must be closed and have89 unique tasks'
    seen = set()
    for path in results:
        row = json.loads(path.read_text())
        task = path.parent.name.rsplit('__', 1)[0]
        assert task not in seen and row.get('finished_at'), 'Duplicate/unclosed original task'
        seen.add(task)
        if (row.get('exception_info') or {}).get('exception_type') == 'AgentTimeoutError':
            rows[task] = {'result_path': str(path), 'result_sha256': sha(path)}
    return rows


def prepare(root):
    import toml
    import tomllib

    os.umask(0o077)
    assert not (root / 'plan.json').exists(), 'Prepared root is immutable'
    plan = {'created_at': time.time(), 'source_commit': (root / 'runtime/commit.txt').read_text().strip(),
            'prior_root': str(PRIOR), 'arms': {}, 'retry_policy': 'One explicit recovery of original AgentTimeout only',
            'agent_timeout_factor': 4, 'verifier_setup_timeout_factor': 1,
            'thinking': False, 'temperature': .6, 'concurrency_per_arm': 4,
            'automatic_paid_retry': False, 'checkpoint_redeployment': False,
            'safety_changes': ['cancellable async HTTP', 'lossless delta journals', 'journals outside sandbox upload']}
    for arm in ARMS:
        old = PRIOR / arm
        selected = timeout_selection(old)
        assert selected, arm
        target = root / arm
        target.mkdir()
        original_cfg = json.loads((old / 'full-config.json').read_text())
        cfg = json.loads(json.dumps(original_cfg))
        options = cfg['agents'][0]['kwargs']
        assert options['temperature'] == .6 and options['interleaved_thinking'] is False
        assert options['max_turns'] is None
        private = Path(options['native_config'])
        assert private.stat().st_mode & 0o077 == 0
        shutil.copyfile(private, target / 'private.json')
        (target / 'private.json').chmod(0o600)
        public_private = json.loads(private.read_text())
        assert not public_private.get('native_endpoint'), 'Fleet only; no endpoint fallback'
        baseline_tasks = {Path(t['path']).name: Path(t['path']) for t in cfg['tasks']}
        files, changes, tasks = {}, [], []
        for name in sorted(selected):
            source = baseline_tasks[name]
            destination = target / 'tasks' / name
            destination.parent.mkdir(exist_ok=True)
            shutil.copytree(source, destination, copy_function=os.link)
            before = tomllib.loads((source / 'task.toml').read_text())
            after = extended(before)
            pending = destination / 'task.toml.new'
            pending.write_text(toml.dumps(after))
            pending.replace(destination / 'task.toml')
            assert tomllib.loads((destination / 'task.toml').read_text()) == after
            for path in source.rglob('*'):
                if path.is_file():
                    relative = path.relative_to(source)
                    if relative.as_posix() != 'task.toml':
                        assert sha(path) == sha(destination / relative)
                    files[str((destination / relative).relative_to(target))] = sha(destination / relative)
            changes.append({'task': name, 'before_sec': before['agent']['timeout_sec'],
                            'after_sec': after['agent']['timeout_sec']})
            tasks.append({'path': str(destination)})
        cfg.update(job_name='timeout4x-retry1', jobs_dir=str(target / 'jobs'),
                   tasks=tasks, n_attempts=1, n_concurrent_trials=4,
                   retry={'max_retries': 0}, timeout_multiplier=1.0)
        options.update(native_config=str(target / 'private.json'), inference_profile='cancellable-legacy')
        unchanged = lambda d: {k: v for k, v in d.items() if k not in {'native_config', 'inference_profile'}}
        assert unchanged(options) == unchanged(original_cfg['agents'][0]['kwargs'])
        assert cfg['agents'][0]['model_name'] == original_cfg['agents'][0]['model_name']
        dump(target / 'config.json', cfg)
        dump(target / 'selection.json', selected)
        dump(target / 'task-manifest.json', files)
        dump(target / 'timeout-changes.json', changes)
        plan['arms'][arm] = {'planned': len(selected), 'model': cfg['agents'][0]['model_name'],
            'config_sha256': sha(target / 'config.json'), 'selection_sha256': sha(target / 'selection.json'),
            'task_manifest_sha256': sha(target / 'task-manifest.json'),
            'prior_config_sha256': sha(old / 'full-config.json'),
            'prior_binding_sha256': sha(old / 'binding.json'),
            'checkpoint': json.loads((old / 'binding.json').read_text()).get('checkpoint')}
    dump(root / 'plan.json', plan)
    print(json.dumps({'prepared': str(root), 'arms': plan['arms']}))


def valid(row):
    reward = (row.get('verifier_result') or {}).get('rewards', {}).get('reward')
    return bool(row.get('finished_at') and not row.get('exception_info')
                and isinstance(reward, (int, float)) and math.isfinite(reward))


def collect(root):
    plan = json.loads((root / 'plan.json').read_text())
    summary = {'checked_at': time.time(), 'arms': {}}
    for arm in ARMS:
        rows = [json.loads(p.read_text()) for p in (root / arm).glob('jobs/*/*/result.json')]
        summary['arms'][arm] = {'planned': plan['arms'][arm]['planned'], 'ended': len(rows),
            'valid_completed': sum(valid(r) for r in rows),
            'full_success': sum(valid(r) and r['verifier_result']['rewards']['reward'] == 1 for r in rows),
            'errors_unknown': sum(not valid(r) for r in rows)}
    dump(root / 'progress.json', summary)
    return summary


def preflight(root):
    import asyncio
    import importlib.util
    import httpx
    from append_rewrite.terminus.native_stream import NativeStreamClient
    from append_rewrite.terminus.tokenizer import PinnedTokenizer
    from append_rewrite.terminus.benchmark_llm import split_thinking

    assert not (root / 'preflight.json').exists(), 'Preserve existing preflight evidence'
    suite = []
    source = root / 'runtime/source'
    for folder, pattern in [(source / 'agentic/tests', 'test_native_stream.py'),
                            (source / 'agentic/tests', 'test_benchmark_cancellation.py'),
                            (source / 'agentic/tests', 'test_benchmark.py'),
                            (source / 'agentic/tests', 'test_episode.py'),
                            (source / 'agentic/experiments/paired531-timeout4x-20261106', 'test_protocol.py')]:
        result = subprocess.run([PYTHON, '-m', 'unittest', 'discover', '-s', str(folder), '-p', pattern],
                                capture_output=True, text=True)
        suite.append({'pattern': pattern, 'returncode': result.returncode,
                      'output': result.stdout + result.stderr})
    assert all(r['returncode'] == 0 for r in suite), 'Offline test failure'
    original_tokenizer = Path('/mnt/ecs-tb4/evaluations/qwen38-tb21-base-20261104/runtime-v2/source/agentic/src/append_rewrite/terminus/tokenizer.py')
    spec = importlib.util.spec_from_file_location('prior_tokenizer', original_tokenizer)
    old = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(old)
    tokenizer_path = json.loads((root / 'base/config.json').read_text())['agents'][0]['kwargs']['tokenizer_path']
    tokenizer = PinnedTokenizer(tokenizer_path, enable_thinking=False)
    previous = old.PinnedTokenizer(tokenizer_path)
    histories = [[{'role': 'user', 'content': 'Task'}],
                 [{'role': 'user', 'content': 'Task'}, {'role': 'assistant', 'content': '{"commands":[]}'},
                  {'role': 'user', 'content': 'Terminal feedback'}]]
    for history in histories:
        assert tokenizer.apply_chat_template(history, tokenize=True) == previous.apply_chat_template(history, tokenize=True)
    plan = json.loads((root / 'plan.json').read_text())
    records = []
    async def probe(arm):
        target = root / arm
        client = NativeStreamClient(target / 'private.json')
        config = client.config
        async with httpx.AsyncClient(timeout=30, trust_env=False) as http:
            response = await http.get(config['base_url'].rstrip('/') + '/api/fleet/v1/deployments/' + config['task_id'],
                                      headers={'x-api-key': config['api_key']})
            response.raise_for_status()
            status = response.json()
        assert status['state'] in {'serving', 'succeeded'}
        assert status['model_id'] == config['task_id']
        assert status['base_model'] == 'Qwen/Qwen3.8-27B'
        expected = plan['arms'][arm]['checkpoint']
        assert status['source'] == ('lora' if expected else 'base')
        assert not expected or status.get('checkpoint') == expected
        wire = tokenizer.apply_chat_template([{'role': 'user', 'content': 'Reply with OK.'}], tokenize=False)
        result = await asyncio.wait_for(client.generate_async(wire, tokenizer,
            journal=target / 'transport-probe', sampling_params={'temperature': .6}, max_tokens=1024), 120)
        text, reasoning = split_thinking(result['text'], False)
        assert text.strip() and reasoning is None
        record = {'arm': arm, 'model': status['model_id'], 'source': status['source'],
                  'checkpoint_matches': True, 'cluster_id': status['cluster_id'],
                  'state': status['state'], 'request_id': result['meta_info']['id'],
                  'normal_stop': result['meta_info']['finish_reason']['type'] == 'stop',
                  'completion_tokens': result['meta_info']['completion_tokens'],
                  'response_sha256': sha(target / 'transport-probe/response.json')}
        dump(target / 'transport-probe-receipt.json', record)
        records.append(record)
    async def probes():
        await asyncio.gather(*(probe(arm) for arm in ARMS))
    try:
        asyncio.run(probes())
    except BaseException as exc:
        dump(root / 'preflight.json', {'passed': False, 'tests': suite, 'probes': records,
                                      'error_type': type(exc).__name__, 'at': time.time()})
        raise
    dump(root / 'preflight.json', {'passed': True, 'tests': suite, 'probes': records,
                                  'nonthinking_renderer_matches_original': True, 'at': time.time()})
    print(json.dumps({'passed': True, 'probes': records}))


def controller(root):
    import fcntl
    lock = (root / 'controller.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    assert not (root / 'dispatch-claim.json').exists(), 'Never reset a paid dispatch claim'
    plan = json.loads((root / 'plan.json').read_text())
    assert json.loads((root / 'preflight.json').read_text())['passed']
    for relative, expected in json.loads((root / 'runtime/files.json').read_text()).items():
        assert sha(root / 'runtime' / relative) == expected
    for arm in ARMS:
        target = root / arm
        for filename, key in [('config.json', 'config_sha256'), ('selection.json', 'selection_sha256'),
                              ('task-manifest.json', 'task_manifest_sha256')]:
            assert sha(target / filename) == plan['arms'][arm][key]
        for relative, expected in json.loads((target / 'task-manifest.json').read_text()).items():
            assert sha(target / relative) == expected
        for prior in json.loads((target / 'selection.json').read_text()).values():
            assert sha(Path(prior['result_path'])) == prior['result_sha256']
    dump(root / 'dispatch-claim.json', {'at': time.time(), 'plan_sha256': sha(root / 'plan.json'),
                                      'one_retry_per_selected_task': True})
    env = {**os.environ, 'PYTHONPATH': str(root / 'runtime/source/agentic/src')}
    children, logs = {}, []
    try:
        for arm in ARMS:
            target = root / arm
            log = (target / 'harbor.log').open('x')
            logs.append(log)
            child = subprocess.Popen([PYTHON, LAUNCHER, str(target / 'config.json')],
                                     env=env, stdout=log, stderr=log)
            children[arm] = child
            dump(target / 'launch.json', {'pid': child.pid, 'start_ticks':
                 Path(f'/proc/{child.pid}/stat').read_text().split()[21], 'at': time.time()})
        while any(p.poll() is None for p in children.values()):
            collect(root)
            time.sleep(20)
        summary = collect(root)
        for arm in ARMS:
            for prior in json.loads((root / arm / 'selection.json').read_text()).values():
                assert sha(Path(prior['result_path'])) == prior['result_sha256']
        dump(root / 'finished.json', {'at': time.time(), 'returncodes':
            {a: c.returncode for a, c in children.items()}, 'summary': summary,
            'prior_timeout_results_unchanged': True})
    finally:
        for log in logs:
            log.close()


if __name__ == '__main__':
    mode, folder = sys.argv[1:]
    {'prepare': prepare, 'preflight': preflight, 'controller': controller, 'collect': collect}[mode](Path(folder))
