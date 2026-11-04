"""One finite takeover of scheduling only; adopt every existing paid worker."""
import argparse
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
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--selection',type=Path);args=parser.parse_args()
    cfg=json.loads((args.selection or work/'runtime-selection.json').read_text());source=Path(cfg['source_root'])
    upgrade=cfg.get('upgrade_from_active',False);handoff=Path(cfg.get('handoff_directory',work))
    capacity=int(cfg.get('worker_capacity',8));score_capacity=int(cfg.get('score_prefill_capacity',2))
    assert capacity>0 and score_capacity>0
    assert json.loads((handoff/'tests.json').read_text())['returncode']==0
    if capacity>8:assert json.loads((handoff/'SCORE4-PROBE.json').read_text())['passed']
    assert not (handoff/'ACTIVATED.json').exists() and not (r/'USER_STOP.json').exists()
    before=json.loads((r/'campaign-progress.json' if upgrade else work/'campaign-progress-before.json').read_text());oldwave=Path(before['wave'])
    if upgrade:
        assert oldwave==work
        assert json.loads((work/'active_runtime_selection.json').read_text())['worker_capacity']==cfg['previous_worker_capacity']
    assert not (oldwave/'run/STOP_PROVIDER').exists()
    oldcampaign=json.loads((r/'campaign-launch.json' if upgrade else work/'old-campaign-launch.json').read_text())
    oldcoord=json.loads((oldwave/'production-launch.json').read_text())
    assert alive(oldcampaign) and external_worker_alive(oldcampaign)
    if upgrade:os.kill(oldcampaign['pid'],signal.SIGSTOP)
    assert proc(oldcampaign['pid'])['state']=='T'
    if upgrade:before=json.loads((r/'campaign-progress.json').read_text())
    if alive(oldcoord):
        assert external_worker_alive(oldcoord);os.kill(oldcoord['pid'],signal.SIGSTOP)
    # No original unclaimed work may be lost during this cross-run takeover.
    oldplan=Path(json.loads((oldwave/'active_runtime_selection.json').read_text())['plan'])
    if not upgrade:assert all((oldwave/'run/units'/x['unit_id']).exists() for x in json.loads(oldplan.read_text())['units'])
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
    assert len(workers)<=capacity
    archive=handoff/'before';archive.mkdir(exist_ok=False)
    for label,path in {'campaign-selection':r/'campaign-selection.json','campaign-launch':r/'campaign-launch.json','old-coordinator-launch':oldwave/'production-launch.json'}.items():
        (archive/(label+'.json')).write_bytes(path.read_bytes())
    for owner in [oldcampaign,oldcoord]:
        if alive(owner):os.kill(owner['pid'],signal.SIGTERM);os.kill(owner['pid'],signal.SIGCONT)
    for _ in range(100):
        if not any(alive(v) for v in [oldcampaign,oldcoord]):break
        time.sleep(.1)
    assert not any(alive(v) for v in [oldcampaign,oldcoord])
    dump(handoff/'adopt-workers.json',{'workers':workers})
    prepared=r/'wave-0400/prepared/plan.json'
    if not upgrade:dump(work/'plan.json',json.loads(prepared.read_text()) if prepared.exists() else {'units':[]})
    rec=r/'native-endpoint-recovery-20261104';fleet=rec/'qwen-native-private.json'
    env={**os.environ,'PYTHONPATH':str(source/'agentic/src'),'PYTHONDONTWRITEBYTECODE':'1',
         'DOCKER_HOST':'unix:///mnt/ecs-tb4/cli-gym-pilot-20261104/runtime/docker.sock','DOCKER_API_VERSION':'1.44','DOCKER_CONFIG':str(r/'docker-config'),
         'APPEND_REWRITE_STUDENT_POOL':str(rec/'active-student-pool'),'APPEND_REWRITE_SCORE_POOL':str(rec/'active-score-pool'),'APPEND_REWRITE_STUDENT_CAPACITY':str(capacity),'APPEND_REWRITE_SCORE_CAPACITY':str(score_capacity)}
    py=str(r/'support/sdk/bin/python')
    def launch(name,argv,receipt):
        with (handoff/(name+'.log')).open('xb') as log:p=subprocess.Popen(argv,env=env,cwd=source,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        v={**proc(p.pid),'argv':argv,'source_root':str(source),'source_commit':cfg['source_commit'],'created_at':time.time(),'log':str(handoff/(name+'.log'))};dump(receipt,v);return v
    argv=[py,'-m','append_rewrite.terminus.production','batch','--plan',str(work/'plan.json'),'--discovery-summary',str(work/'complete.json'),'--output',str(work/'run'),'--workers',str(capacity),'--adopt-workers',str(handoff/'adopt-workers.json')]
    for key,path in {'teacher-config':r/'support/private/terminus-deepseek.json','fleet-config':fleet,'tokenizer':r/'support/tokenizers/qwen38-27b-1d4bf0f','sandbox-credentials':r/'support/private/sandbox.env','runtime-assets':r/'support/runtime-assets/tmux-linux-x86_64-v1'}.items():argv+=['--'+key,str(path)]
    coordinator=launch('coordinator',argv,work/'production-launch.json')
    manifest=handoff/'manifest.json'
    dump(manifest,{'root':str(r),'work':str(work),'source':str(source),'source_commit':cfg['source_commit'],
         'prior_runs':[x for x in before['runs'] if Path(x)!=work/'run'],
         'initial_preparation_wave':before.get('preparing_wave') if upgrade else str(r/'wave-0400'),
         'next_offset':before['next_source_offset'] if upgrade else 500,
         'preparation_waves':before.get('preparation_waves',[str(r/'wave-0400')]),'worker_capacity':capacity})
    campaign=launch('producer',[py,str(source/'agentic/experiments/cli-gym-scale-20261104/rolling.py'),'--manifest',str(manifest)],r/'campaign-launch.json')
    selection={**cfg,'queue_policy':'cross_wave_shared','worker_capacity':capacity,'student_capacity':capacity,'score_prefill_capacity':score_capacity,'candidates_per_block':8,'adopted_workers':workers,'plan':str(work/'plan.json'),'transport_selection':str(r/'transport-selection.json'),'automatic_paid_retry':False,'current_activation_receipt':str(handoff/'ACTIVATED.json')}
    dump(work/'active_runtime_selection.json',selection)
    old=json.loads((r/'campaign-selection.json').read_text());old.update(selection);old['rolling_root']=str(work);dump(r/'campaign-selection.json',old)
    dump(handoff/'ACTIVATED.json',{'coordinator':coordinator,'campaign':campaign,'adopted_workers':workers,'worker_capacity':capacity,'score_prefill_capacity':score_capacity,'paid_worker_restarts':0,'paid_attempt_replays':0,'created_at':time.time()})
    dump(work/'handoff-state.json',{'phase':'rolling_active','paid_attempt_replays':0,'source_commit':cfg['source_commit']})
    print(json.dumps({'rolling':True,'worker_capacity':capacity,'score_prefill_capacity':score_capacity,'adopted_paid_workers':len(workers),'replays':0}))


if __name__=='__main__':main()
