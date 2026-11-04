"""Prioritize completed experts while adopting all already-paid unit workers."""
import hashlib
import json
import os
from pathlib import Path
import runpy
import signal
import subprocess
import time

ROOT = Path('/mnt/ecs-tb4/cli-gym-scale-20261104')


def main():
    r=ROOT;rec=r/'native-endpoint-recovery-20261104';w=r/'wave-0300'
    api=runpy.run_path(str(rec/'resume_native-v3.py'));proc=api['proc'];alive=api['alive'];dump=api['dump']
    archive=rec/'reuse-priority';archive.mkdir(exist_ok=False)
    campaign=json.loads((r/'campaign-launch.json').read_text());old=json.loads((w/'production-launch.json').read_text())
    assert alive(campaign) and alive(old)
    os.kill(campaign['pid'],signal.SIGSTOP);os.kill(old['pid'],signal.SIGSTOP)
    workers=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            argv=(p/'cmdline').read_bytes().split(b'\0')
            if b'append_rewrite.terminus.production' not in argv or b'unit' not in argv:continue
            out=Path(argv[argv.index(b'--output')+1].decode())
            if out.parent==w/'run/units':
                v=proc(int(p.name))
                if v and v['state']!='Z':v['unit_id']=out.name;workers.append(v)
        except FileNotFoundError:pass
    assert len(workers)<=8
    for name,p in {'old-launch':w/'production-launch.json','plan-before':rec/'dispatch-plan.json','selection-before':w/'active_runtime_selection.json','complete-before':rec/'dispatch-complete.json'}.items():
        (archive/(name+'.json')).write_bytes(p.read_bytes())
    plan=json.loads((rec/'dispatch-plan.json').read_text())
    plan['units'].sort(key=lambda x:not x['unit_id'].endswith('-native-recovery'))
    dump(rec/'dispatch-plan.json',plan)
    dump(rec/'dispatch-complete.json',{'plan_sha256':hashlib.sha256((rec/'dispatch-plan.json').read_bytes()).hexdigest(),'finished_at':time.time(),'expert_replays':0,'priority':'completed_experts_first'})
    adoption=archive/'adopt-workers.json';dump(adoption,{'workers':workers})
    os.kill(old['pid'],signal.SIGTERM);os.kill(old['pid'],signal.SIGCONT)
    for _ in range(100):
        if not alive(old):break
        time.sleep(.05)
    assert not alive(old)
    argv=list(old['argv']);argv[argv.index('--adopt-workers')+1]=str(adoption)
    env={**os.environ,'PYTHONPATH':str(rec/'frozen-production-be4b594/agentic/src'),'PYTHONDONTWRITEBYTECODE':'1','DOCKER_HOST':'unix:///mnt/ecs-tb4/cli-gym-pilot-20261104/runtime/docker.sock','DOCKER_API_VERSION':'1.44','DOCKER_CONFIG':str(r/'docker-config'),'APPEND_REWRITE_STUDENT_POOL':str(rec/'active-student-pool'),'APPEND_REWRITE_SCORE_POOL':str(rec/'active-score-pool'),'APPEND_REWRITE_STUDENT_CAPACITY':'8'}
    with (archive/'coordinator.log').open('xb') as log:
        p=subprocess.Popen(argv,env=env,cwd=rec/'frozen-production-be4b594',stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
    new={**proc(p.pid),'argv':argv,'source_commit':'be4b594','source_root':str(rec/'frozen-production-be4b594'),'created_at':time.time(),'log':str(archive/'coordinator.log')}
    dump(w/'production-launch.json',new)
    selection=json.loads((w/'active_runtime_selection.json').read_text());selection['dispatch_priority']='reuse_existing_experts_before_new_sources';selection['adopted_running_workers']=workers;dump(w/'active_runtime_selection.json',selection)
    os.kill(campaign['pid'],signal.SIGCONT)
    dump(archive/'receipt.json',{'old_controller':old,'new_controller':new,'adopted_workers':workers,'paid_worker_restarts':0,'teacher_replays':0,'paid_student_replays':0,'priority':'reuse_existing_experts_before_new_sources'})
    print(json.dumps({'adopted':len(workers),'priority':'completed experts first','replays':0}))


if __name__=='__main__':main()
