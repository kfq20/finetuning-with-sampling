"""One finite takeover of scheduling only; adopt every existing paid worker."""
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time

from append_rewrite.terminus.production import external_worker_alive


def dump(path,value):
    p=path.with_suffix('.tmp');p.write_text(json.dumps(value,indent=2)+'\n');p.replace(path)


def proc(pid):
    try:
        p=Path('/proc')/str(pid);f=(p/'stat').read_text().split(') ')[1].split()
        return {'pid':pid,'start_ticks':f[19],'state':f[0],'cmdline_sha256':hashlib.sha256((p/'cmdline').read_bytes()).hexdigest()}
    except FileNotFoundError:return None


def alive(v):
    p=proc(v['pid']);return p and p['start_ticks']==v['start_ticks'] and p['state']!='Z'


def main():
    r=Path('/mnt/ecs-tb4/cli-gym-scale-20261104');work=r/'rolling-acquisition-20261104'
    cfg=json.loads((work/'runtime-selection.json').read_text());source=Path(cfg['source_root'])
    assert json.loads((work/'tests.json').read_text())['returncode']==0
    assert not (work/'ACTIVATED.json').exists() and not (r/'USER_STOP.json').exists()
    before=json.loads((work/'campaign-progress-before.json').read_text());oldwave=Path(before['wave'])
    assert not (oldwave/'run/STOP_PROVIDER').exists()
    oldcampaign=json.loads((work/'old-campaign-launch.json').read_text())
    oldcoord=json.loads((oldwave/'production-launch.json').read_text())
    assert alive(oldcampaign) and proc(oldcampaign['pid'])['state']=='T'
    assert external_worker_alive(oldcampaign)
    if alive(oldcoord):
        assert external_worker_alive(oldcoord);os.kill(oldcoord['pid'],signal.SIGSTOP)
    # No original unclaimed work may be lost during this cross-run takeover.
    oldplan=Path(json.loads((oldwave/'active_runtime_selection.json').read_text())['plan'])
    assert all((oldwave/'run/units'/x['unit_id']).exists() for x in json.loads(oldplan.read_text())['units'])
    workers=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            a=(p/'cmdline').read_bytes().split(b'\0')
            if b'append_rewrite.terminus.production' not in a or b'unit' not in a:continue
            out=Path(a[a.index(b'--output')+1].decode())
            if r in out.parents:
                v=proc(int(p.name))
                if v and v['state']!='Z':v.update(unit_id=out.name,output=str(out));workers.append(v)
        except FileNotFoundError:pass
    assert len(workers)<=8
    archive=work/'before';archive.mkdir(exist_ok=False)
    for label,path in {'campaign-selection':r/'campaign-selection.json','campaign-launch':r/'campaign-launch.json','old-coordinator-launch':oldwave/'production-launch.json'}.items():
        (archive/(label+'.json')).write_bytes(path.read_bytes())
    for owner in [oldcampaign,oldcoord]:
        if alive(owner):os.kill(owner['pid'],signal.SIGTERM);os.kill(owner['pid'],signal.SIGCONT)
    for _ in range(100):
        if not any(alive(v) for v in [oldcampaign,oldcoord]):break
        time.sleep(.1)
    assert not any(alive(v) for v in [oldcampaign,oldcoord])
    dump(work/'adopt-workers.json',{'workers':workers})
    prepared=r/'wave-0400/prepared/plan.json'
    dump(work/'plan.json',json.loads(prepared.read_text()) if prepared.exists() else {'units':[]})
    rec=r/'native-endpoint-recovery-20261104';fleet=rec/'qwen-native-private.json'
    env={**os.environ,'PYTHONPATH':str(source/'agentic/src'),'PYTHONDONTWRITEBYTECODE':'1',
         'DOCKER_HOST':'unix:///mnt/ecs-tb4/cli-gym-pilot-20261104/runtime/docker.sock','DOCKER_API_VERSION':'1.44','DOCKER_CONFIG':str(r/'docker-config'),
         'APPEND_REWRITE_STUDENT_POOL':str(rec/'active-student-pool'),'APPEND_REWRITE_SCORE_POOL':str(rec/'active-score-pool'),'APPEND_REWRITE_STUDENT_CAPACITY':'8'}
    py=str(r/'support/sdk/bin/python')
    def launch(name,argv,receipt):
        with (work/(name+'.log')).open('xb') as log:p=subprocess.Popen(argv,env=env,cwd=source,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        v={**proc(p.pid),'argv':argv,'source_root':str(source),'source_commit':cfg['source_commit'],'created_at':time.time(),'log':str(work/(name+'.log'))};dump(receipt,v);return v
    argv=[py,'-m','append_rewrite.terminus.production','batch','--plan',str(work/'plan.json'),'--discovery-summary',str(work/'complete.json'),'--output',str(work/'run'),'--workers','8','--adopt-workers',str(work/'adopt-workers.json')]
    for key,path in {'teacher-config':r/'support/private/terminus-deepseek.json','fleet-config':fleet,'tokenizer':r/'support/tokenizers/qwen38-27b-1d4bf0f','sandbox-credentials':r/'support/private/sandbox.env','runtime-assets':r/'support/runtime-assets/tmux-linux-x86_64-v1'}.items():argv+=['--'+key,str(path)]
    coordinator=launch('coordinator',argv,work/'production-launch.json')
    dump(work/'manifest.json',{'root':str(r),'work':str(work),'source':str(source),'source_commit':cfg['source_commit'],'prior_runs':before['runs'],'initial_preparation_wave':str(r/'wave-0400'),'next_offset':500})
    campaign=launch('producer',[py,str(source/'agentic/experiments/cli-gym-scale-20261104/rolling.py'),'--manifest',str(work/'manifest.json')],r/'campaign-launch.json')
    selection={**cfg,'queue_policy':'cross_wave_shared','worker_capacity':8,'student_capacity':8,'score_prefill_capacity':2,'candidates_per_block':8,'adopted_workers':workers,'plan':str(work/'plan.json'),'transport_selection':str(r/'transport-selection.json'),'automatic_paid_retry':False}
    dump(work/'active_runtime_selection.json',selection)
    old=json.loads((r/'campaign-selection.json').read_text());old.update(selection);old['rolling_root']=str(work);dump(r/'campaign-selection.json',old)
    dump(work/'ACTIVATED.json',{'coordinator':coordinator,'campaign':campaign,'adopted_workers':workers,'worker_capacity':8,'paid_worker_restarts':0,'paid_attempt_replays':0,'created_at':time.time()})
    dump(work/'handoff-state.json',{'phase':'rolling_active','paid_attempt_replays':0,'source_commit':cfg['source_commit']})
    print(json.dumps({'rolling':True,'worker_capacity':8,'adopted_paid_workers':len(workers),'replays':0}))


if __name__=='__main__':main()
