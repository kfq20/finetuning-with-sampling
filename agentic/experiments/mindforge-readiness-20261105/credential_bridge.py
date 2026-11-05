"""Ephemeral stdin credential handoff; runs only approved preparation CLI commands.

No credentials on argv, in files or in diagnostics. This process is an interactive
transport worker, not a training controller; train start and deployment mutations
are deliberately absent from its allowlist.
"""
import json
import subprocess
import sys

identity = json.loads(sys.stdin.readline())
assert identity['host'] == 'https://mindforge.macaron.xin'
print('READY: credential held in process memory only', flush=True)
for line in sys.stdin:
    command = json.loads(line)
    if command.get('quit'):
        break
    args = command['args']
    allowed = [('sft', 'validate'), ('sft', 'upload'), ('sft', 'show'),
               ('sft', 'preflight'), ('sft', 'render'), ('train', 'models'), ('train', 'clusters')]
    assert tuple(args[:2]) in allowed
    inner = "import os,json,subprocess,pathlib\n"
    inner += 'env={**os.environ,"MINDFORGE_HOST":' + repr(identity['host']) + ',"MINDFORGE_TOKEN":' + repr(identity['token']) + '}\n'
    inner += "p=subprocess.run(['/root/MindForge/.venv/bin/python','/mnt/ecs-tb4/tools/mindforge-pat-compat-20261105/cli_pat_compat_v3.py',*" + repr(args) + "],cwd='/root/MindForge',env=env,capture_output=True,text=True,timeout=900)\n"
    inner += 'stdout=p.stdout.replace(env["MINDFORGE_TOKEN"],"<redacted>");stderr=p.stderr.replace(env["MINDFORGE_TOKEN"],"<redacted>")\n'
    if command.get('save'):
        dest = command['save']
        assert dest.startswith('/mnt/ecs-tb4/datasets/mindforge-1step-20261105/')
        inner += 'pathlib.Path(' + repr(dest) + ').write_text(stdout)\n'
    inner += 'print(json.dumps({"exit_code":p.returncode,"stdout":stdout,"stderr":stderr}))\n'
    outer = "import sys,pathlib,subprocess,os\nsys.path.insert(0,'src')\nfrom relayforge.asset_org.ecs_sync import _resolve_remote\nremote,password=_resolve_remote(pathlib.Path('.secrets/ecs_remote.env'))\n"
    outer += "p=subprocess.run(['sshpass','-e','ssh','-o','ConnectTimeout=15',remote,'python3 -'],input=" + repr(inner) + ",text=True,capture_output=True,env={**os.environ,'SSHPASS':password},timeout=950)\nprint(p.stdout);print(p.stderr)\n"
    result = subprocess.run(['ssh', 'mindlab', 'cd /vePFS-Mindverse/user/intern/fanqi/relayforge && python3 -'], input=outer, capture_output=True, text=True, timeout=1000)
    print(result.stdout.replace(identity['token'], '<redacted>'), flush=True)
    print(result.stderr.replace(identity['token'], '<redacted>'), flush=True)
