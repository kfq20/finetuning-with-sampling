"""Retire owned, already-failed units whose executor threads outlive the episode.

Never terminate an unclosed/normal model episode. Preserve original files and
bind status, error, public context and process identity before sending SIGTERM.
"""
import hashlib
import json
import os
from pathlib import Path
import signal
import time


def identity(pid):
    try:
        p=Path('/proc')/str(pid);f=(p/'stat').read_text().split(') ')[1].split()
        if f[0] in {'Z','X','x'}:return None
        argv=(p/'cmdline').read_bytes()
        return {'pid':pid,'start_ticks':f[19],'command_sha256':hashlib.sha256(argv).hexdigest()},argv.split(b'\0')
    except FileNotFoundError:return None


def retire_failed_workers(run,adopted,evidence,*,grace_sec=60):
    inherited={Path(x['output']):x for x in adopted if x.get('output')}
    retired=[]
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():continue
        info=identity(int(proc.name))
        if not info:continue
        owner,argv=info
        if b'append_rewrite.terminus.production' not in argv or b'unit' not in argv or b'--output' not in argv or b'--spec' not in argv:continue
        out=Path(argv[argv.index(b'--output')+1].decode());spec=Path(argv[argv.index(b'--spec')+1].decode())
        if out.parent!=run/'units':
            old=inherited.get(out)
            if not old or old['pid']!=owner['pid'] or str(old['start_ticks'])!=owner['start_ticks'] or old['cmdline_sha256']!=owner['command_sha256']:continue
        status=out/'status.json'
        if not status.exists() or json.loads(status.read_text()).get('phase')!='hold':continue
        if not spec.exists() or json.loads(spec.read_text()).get('unit_id')!=out.name:continue
        for role in ['student','teacher']:
            base=out/role;error=base/'error.json';history=base/'public-messages.json';context=base/'context.json'
            if not all(p.exists() for p in [error,history,context]):continue
            if time.time()-error.stat().st_mtime<grace_sec:continue
            receipt=base/'receipt.json'
            if receipt.exists():continue  # A completed receipt always takes precedence.
            evidence.mkdir(mode=0o700,parents=True,exist_ok=True)
            target=evidence/f"{owner['pid']}-{owner['start_ticks']}.json"
            if target.exists():break
            hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [status,spec,error,history,context]}
            record={'process':owner,'unit':out.name,'role':role,'reason':'terminal_failure_executor_still_alive','original_file_hashes':hashes,'model_replays':0,'raw_logs_preserved':True,'uncompleted_request_billing':'unknown; retained','signalled':False,'checked_at':time.time()}
            with target.open('x') as f:json.dump(record,f,indent=2)
            current=identity(owner['pid'])
            if current and current[0]==owner:
                os.kill(owner['pid'],signal.SIGTERM);record['signalled']=True;retired.append(out.name)
            temp=target.with_suffix('.tmp');temp.write_text(json.dumps(record,indent=2)+'\n');temp.replace(target)
            break
    return retired
