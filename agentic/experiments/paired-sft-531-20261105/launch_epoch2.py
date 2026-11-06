"""Local stdin-only credential launcher; resume both completed epoch-one states."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import termios
import time


def main():
    os.umask(0o077)
    root = Path(sys.argv[1]).resolve()
    plan = json.loads((root / 'plan.json').read_text())
    assert not (root / 'launch.json').exists()
    assert not any((root / arm / 'claim.json').exists() for arm in ['method', 'expert'])
    parent = Path(plan['parent_training_root'])
    for arm in ['method', 'expert']:
        assert hashlib.sha256((parent / arm / 'training-complete.json').read_bytes()).hexdigest() == plan['resume'][arm]['completion_sha256']
        assert hashlib.sha256((parent / arm / 'checkpoint-0034.json').read_bytes()).hexdigest() == plan['resume'][arm]['checkpoint_reference_sha256']
    settings = None
    if sys.stdin.isatty():
        settings = termios.tcgetattr(sys.stdin)
        hidden = termios.tcgetattr(sys.stdin)
        hidden[3] &= ~termios.ECHO
        termios.tcsetattr(sys.stdin, termios.TCSANOW, hidden)
    print('READY: authorized training credential via stdin; terminal echo disabled', flush=True)
    try:
        credentials = json.loads(sys.stdin.readline())
    finally:
        if settings is not None:
            termios.tcsetattr(sys.stdin, termios.TCSANOW, settings)
    expected = json.loads((parent / 'method/identity.json').read_text())['credential_sha256']
    assert hashlib.sha256(credentials['token'].encode()).hexdigest() == expected, 'Credential identity changed'
    assert credentials['fleet_key'] == 'not-used-training-only'
    assert plan['evaluate_base'] is False and plan['deploy_after_training'] is False
    python = plan['python']
    command = [python, str(root / 'runtime/run.py'), str(root)]
    with (root / 'controller.log').open('x') as log:
        child = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=log, stderr=log,
                                 start_new_session=True)
        child.stdin.write((json.dumps(credentials) + '\n').encode())
        child.stdin.close()
    caffeinate = subprocess.Popen(['/usr/bin/caffeinate', '-im', '-w', str(child.pid)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    started = subprocess.check_output(['ps', '-p', str(child.pid), '-o', 'lstart='], text=True).strip()
    receipt = {'pid': child.pid, 'started_at': started, 'at': time.time(), 'command': command,
               'caffeinate_pid': caffeinate.pid, 'plan_sha256': hashlib.sha256((root/'plan.json').read_bytes()).hexdigest(),
               'credential_sha256': expected, 'source_commit': plan['source_commit'],
               'parent_training_root': str(parent)}
    (root / 'launch.json').write_text(json.dumps(receipt, indent=2) + '\n')
    selection_path = root.parent / 'active_training_selection.json'
    previous = json.loads(selection_path.read_text())
    assert previous['root'] == str(parent), 'Active selection changed concurrently'
    (root / 'previous_training_selection.json').write_text(json.dumps(previous, indent=2) + '\n')
    selected = {'root': str(root), 'source_commit': plan['source_commit'],
                'plan_sha256': receipt['plan_sha256'], 'batch_size': 16,
                'num_epochs': 2, 'initialization': 'Continue epoch1 final weights and Adam state',
                'parent_training_root': str(parent), 'rows_per_epoch_per_arm': 531,
                'previous_optimizer_updates_per_arm': 34, 'new_optimizer_updates_per_arm': 34,
                'target_optimizer_updates_per_arm': 68, 'launch': str(root/'launch.json'),
                'epoch1_evaluation_unchanged': True, 'automatic_deployment': False}
    temporary = selection_path.with_suffix('.json.new')
    temporary.write_text(json.dumps(selected, indent=2) + '\n')
    temporary.replace(selection_path)
    print(json.dumps(receipt), flush=True)


if __name__ == '__main__':
    main()
