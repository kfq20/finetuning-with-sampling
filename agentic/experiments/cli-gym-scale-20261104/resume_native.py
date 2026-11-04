"""Resume8 workers only after a hash-bound native-endpoint canary review.

Reuse completed experts; never retry a started student or interrupt an expert.
"""
import hashlib
import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import time

ROOT=Path('/mnt/ecs-tb4/cli-gym-scale-20261104')


def dump(path,value):
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2)+'\n');temp.replace(path)


def proc(pid):
    p=Path('/proc')/str(pid)
    try:
        fields=(p/'stat').read_text().split(') ')[1].split()
        return {'pid':pid,'start_ticks':fields[19],'state':fields[0],
                'cmdline_sha256':hashlib.sha256((p/'cmdline').read_bytes()).hexdigest()}
    except FileNotFoundError:return None


def alive(v):
    p=proc(v['pid']);return p and p['start_ticks']==v['start_ticks'] and p['state']!='Z'


def main():
    r=ROOT;rec=r/'native-endpoint-recovery-20261104';src=rec/'frozen-production-be4b594'
    review=json.loads((rec/'CANARY-REVIEW.json').read_text())
    assert review['passed'] and not review['teacher_replayed']
    assert hashlib.sha256(Path(review['student_receipt']).read_bytes()).hexdigest()==review['student_receipt_sha256']
    assert hashlib.sha256((rec/'qwen-native-private.json').read_bytes()).hexdigest()==review['native_config_sha256']
    assert not (r/'USER_STOP.json').exists()
    w=Path(json.loads((r/'campaign-progress.json').read_text())['wave']);assert w.name=='wave-0300'
    assert (w/'run/STOP_PROVIDER').exists()
    owners=[json.loads((r/'campaign-launch.json').read_text()),json.loads((w/'production-launch.json').read_text())]
    archive=rec/'scheduler-before';archive.mkdir(mode=0o700,exist_ok=False)
    for owner in owners:
        assert alive(owner);os.kill(owner['pid'],signal.SIGSTOP)
    # Stable current dispatch, while actual expert unit processes stay alive.
    workers=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            argv=(p/'cmdline').read_bytes().split(b'\0')
            if b'append_rewrite.terminus.production' not in argv or b'unit' not in argv or b'--output' not in argv:continue
            out=Path(argv[argv.index(b'--output')+1].decode())
            if out.parent!=w/'run/units' or out.name.endswith('-native-recovery'):continue
            v=proc(int(p.name))
            if v and v['state']!='Z':
                assert not (out/'student').exists(),'Never repeat a requested student'
                v['unit_id']=out.name;workers.append(v)
        except FileNotFoundError:pass
    assert len(workers)<=8
    for label,p in {'campaign-selection':r/'campaign-selection.json','campaign-launch':r/'campaign-launch.json',
                    'campaign-progress':r/'campaign-progress.json','wave-selection':w/'active_runtime_selection.json',
                    'coordinator-launch':w/'production-launch.json','coordinator-state':w/'run/coordinator.json',
                    'provider-hold':r/'PROVIDER_HOLD.json','wave-provider-stop':w/'run/STOP_PROVIDER'}.items():
        (archive/(label+'.json')).write_bytes(p.read_bytes())
    for owner in owners:
        os.kill(owner['pid'],signal.SIGTERM)
        if alive(owner):os.kill(owner['pid'],signal.SIGCONT)
    for _ in range(100):
        if not any(alive(v) for v in owners):break
        time.sleep(.1)
    assert not any(alive(v) for v in owners)
    helper=Path(json.loads((rec/'recovery-operations.json').read_text())['plan_producer_entry'])
    transfer=runpy.run_path(str(helper))['transfer']
    plan=json.loads((w/'prepared/plan.json').read_text());late=[]
    for worker in workers:
        item=transfer(r,rec,w,worker)
        if item:plan['units'].append(item)
        elif alive(worker):late.append(worker)
    plan_path=rec/'dispatch-plan.json';dump(plan_path,plan)
    complete=rec/'dispatch-complete.json'
    dump(rec/'adopt-workers.json',{'workers':late})
    manifest=rec/'producer-manifest.json';dump(manifest,{'root':str(r),'recovery':str(rec),'wave':str(w),
        'late_workers':late,'plan':str(plan_path),'complete':str(complete)})
    env={**os.environ,'PYTHONPATH':str(src/'agentic/src'),'PYTHONDONTWRITEBYTECODE':'1',
         'DOCKER_HOST':'unix:///mnt/ecs-tb4/cli-gym-pilot-20261104/runtime/docker.sock',
         'DOCKER_API_VERSION':'1.44','DOCKER_CONFIG':str(r/'docker-config'),
         'APPEND_REWRITE_STUDENT_POOL':str(rec/'active-student-pool'),
         'APPEND_REWRITE_SCORE_POOL':str(rec/'active-score-pool'),'APPEND_REWRITE_STUDENT_CAPACITY':'8'}
    py=str(r/'support/sdk/bin/python')
    def launch(name,argv,receipt):
        with (rec/(name+'.log')).open('xb') as log:
            p=subprocess.Popen(argv,env=env,cwd=src,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
        v={**proc(p.pid),'argv':argv,'source_commit':'be4b594','source_root':str(src),
           'created_at':time.time(),'log':str(rec/(name+'.log'))};dump(receipt,v);return v
    selection=json.loads((w/'active_runtime_selection.json').read_text());selection.update(
        source_commit='be4b594',source_root=str(src),plan=str(plan_path),discovery_summary=str(complete),
        fleet_config_sha256=review['native_config_sha256'],worker_capacity=8,student_target=8,queue_policy='shared',
        score_prefill_concurrency=2,canonical_source_count=100,teacher_reuse=True,
        old_experts_still_running=late,canary_review=str(rec/'CANARY-REVIEW.json'))
    dump(w/'active_runtime_selection.json',selection)
    # The stopped old coordinator cannot dispatch; new provider was canary-approved.
    (w/'run/STOP_PROVIDER').rename(archive/'STOP_PROVIDER.original')
    (r/'PROVIDER_HOLD.json').rename(archive/'PROVIDER_HOLD.original')
    launch('late-expert-producer',[py,str(helper),'--manifest',str(manifest)],rec/'producer-launch.json')
    argv=[py,'-m','append_rewrite.terminus.production','batch','--plan',str(plan_path),
          '--discovery-summary',str(complete),'--output',str(w/'run'),'--workers','8',
          '--adopt-workers',str(rec/'adopt-workers.json')]
    for key,p in {'teacher-config':r/'support/private/terminus-deepseek.json','fleet-config':rec/'qwen-native-private.json',
                  'tokenizer':r/'support/tokenizers/qwen38-27b-1d4bf0f','sandbox-credentials':r/'support/private/sandbox.env',
                  'runtime-assets':r/'support/runtime-assets/tmux-linux-x86_64-v1'}.items():argv+=['--'+key,str(p)]
    coordinator=launch('coordinator-native',argv,w/'production-launch.json')
    config=json.loads((r/'campaign-selection.json').read_text());config.update(source_commit='be4b594',
        source_root=str(src),native_config_sha256=review['native_config_sha256'],canary_review=str(rec/'CANARY-REVIEW.json'),
        provider='user-approved-ssh-native-qwen',worker_capacity=8,student_target=8,score_prefill_concurrency=2)
    dump(r/'campaign-selection.json',config)
    campaign=launch('campaign-native',[py,str(src/'agentic/experiments/cli-gym-scale-20261104/campaign.py'),
        '--root',str(r),'--source-commit','be4b594','--workers','8','--resume',
        '--fleet-config',str(rec/'qwen-native-private.json')],r/'campaign-launch.json')
    dump(rec/'resume-receipt.json',{'new_coordinator':coordinator,'new_campaign':campaign,
        'adopted_running_experts':late,'teacher_replays':0,'paid_student_replays':0,
        'derived_plan_execution_records':len(plan['units']),'canary_review_sha256':hashlib.sha256((rec/'CANARY-REVIEW.json').read_bytes()).hexdigest()})
    print(json.dumps({'restored_worker_capacity':8,'adopted_experts':len(late),'teacher_replays':0,'paid_student_replays':0}))


if __name__=='__main__':main()
