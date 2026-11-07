"""Provider outage admission gate; never retry or reset a benchmark attempt."""
import asyncio
import hashlib
import json
import os
from pathlib import Path
import sys
import time


def hold_path(role):
    root = os.environ.get('APPEND_REWRITE_PROVIDER_GATE')
    return Path(root) / (role + '-outage.json') if root else None


def record_outage(role, exc, journal):
    status = getattr(exc, 'code', None) or getattr(getattr(exc, 'response', None), 'status_code', None)
    path = hold_path(role)
    if not path or status not in (429, 500, 502, 503, 504):
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with path.open('x') as f:
            json.dump({'role': role, 'http_status': status, 'at': time.time(),
                       'journal': str(journal), 'benchmark_retry': False}, f)
    except FileExistsError:
        pass


async def check_gates(args):
    """Only the sole coordinator probes; bounded owned subprocesses, no fallback."""
    root = os.environ.get('APPEND_REWRITE_PROVIDER_GATE')
    if not root:
        return []
    blocked = []
    for role in ('teacher', 'student'):
        path = hold_path(role)
        if not path.exists():
            continue
        blocked.append(role)
        stamp = Path(root) / (role + '-last-probe.json')
        if stamp.exists() and time.time() - json.loads(stamp.read_text())['at'] < 300:
            continue
        before = hashlib.sha256(path.read_bytes()).hexdigest()
        dest = Path(root) / 'health-probes' / (role + '-' + str(time.time_ns()))
        dest.mkdir(parents=True)
        stamp.write_text(json.dumps({'at': time.time(), 'output': str(dest)}))
        argv = [sys.executable, '-m', __name__, role, str(dest),
                str(args.teacher_config if role == 'teacher' else args.fleet_config), str(args.tokenizer)]
        with (dest / 'process.log').open('x') as log:
            p = await asyncio.create_subprocess_exec(*argv, stdout=log, stderr=log)
            try:
                await asyncio.wait_for(p.wait(), 45)
            except asyncio.TimeoutError:
                p.kill()
                await p.wait()
                (dest / 'timeout.json').write_text(json.dumps({'benchmark_attempts': 0}))
        result = dest / 'result.json'
        if (result.exists() and json.loads(result.read_text()).get('passed') and path.exists()
                and hashlib.sha256(path.read_bytes()).hexdigest() == before):
            path.rename(dest / 'recovered-outage.json')
            blocked.remove(role)
    return blocked


def probe(role, dest, config, tokenizer):
    if role == 'teacher':
        from .teacher import DeepSeekTeacher
        b = DeepSeekTeacher(config, dest / 'requests')
        r = b.request([{'role': 'user', 'content': 'Health check. Reply with exactly OK.'}], dest / 'requests/request-0001')
        passed = r['content'].strip() == 'OK'
    else:
        from .suffix_score import NativeFullStreamClient
        from .scoring import render_candidate
        from .tokenizer import PinnedTokenizer
        t = PinnedTokenizer(tokenizer)
        raw = json.dumps({'analysis': '', 'plan': '', 'commands': [], 'task_complete': True})
        rendered = render_candidate([{'role': 'user', 'content': 'Health check.'}], raw, t, tokenizer_identity=t.identity)
        NativeFullStreamClient(config).score(rendered, journal=dest / 'score', timeout=40)
        passed = True
    (dest / 'result.json').write_text(json.dumps({'passed': passed, 'benchmark_attempts': 0}))


if __name__ == '__main__':
    probe(sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]))
