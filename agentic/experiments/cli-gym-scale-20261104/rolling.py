"""Feed one explicitly sized worker queue across preparation batches, without wave barriers.

Preparation stays source-batched; paid dispatch is global, exclusive and rolling.
The existing500-SFT objective and all per-task quality/transport rules are retained.
"""
import argparse
import fcntl
import hashlib
import json
from pathlib import Path
import runpy
import shutil
import subprocess
import sys
import time


def dump(path,value):
    p=path.with_suffix('.tmp');p.write_text(json.dumps(value,indent=2)+'\n');p.replace(path)


def alive(value):
    p=Path('/proc')/str(value['pid'])/'stat'
    try:
        f=p.read_text().split(') ')[1].split()
        return f[0]!='Z' and f[19]==str(value['start_ticks'])
    except FileNotFoundError:return False


def pending(plan,output):
    return sum(not (output/'units'/x['unit_id']).exists() for x in plan['units'])


def merge(plan,items):
    """Append immutable new inputs; duplicate publication never creates an attempt."""
    known={x['unit_id']:x for x in plan['units']}
    for item in items:
        if item['unit_id'] in known:
            if item!=known[item['unit_id']]:raise ValueError('Published input identity drift')
        else:
            known[item['unit_id']]=item;plan['units'].append(item)
    return plan


def main():
    parser=argparse.ArgumentParser(__doc__);parser.add_argument('--manifest',type=Path,required=True);args=parser.parse_args()
    cfg=json.loads(args.manifest.read_text());root=Path(cfg['root']);work=Path(cfg['work']);source=Path(cfg['source'])
    lock=(root/'campaign.lock').open('a+');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    publish=runpy.run_path(str(Path(__file__).with_name('collect.py')))['publish']
    runs=list(map(Path,cfg['prior_runs']))+[work/'run'];plan_path=work/'plan.json';complete=work/'complete.json'
    catalog=json.loads((root/'catalog/manifest.json').read_text())
    for path,sha in catalog['pages'].items():
        assert hashlib.sha256(Path(path).read_bytes()).hexdigest()==sha
    capacity=int(cfg.get('worker_capacity',8))
    if capacity<1:raise ValueError('Positive worker capacity required')
    preparing=Path(cfg['initial_preparation_wave']) if cfg.get('initial_preparation_wave') else None
    next_offset=cfg['next_offset'];wave_records=list(cfg.get('preparation_waves',[str(preparing)] if preparing else []))
    stopping=None
    while True:
        plan=json.loads(plan_path.read_text())
        result=publish(runs,root/'campaign-sft');count=result['valid_trajectories']
        if (root/'USER_STOP.json').exists():
            stopping='user_stopped';dump(work/'run/STOP_PROVIDER',{'reason':stopping,'new_model_requests':0})
        elif (work/'run/STOP_PROVIDER').exists():stopping='provider_hold'
        elif count>=500:stopping='target_reached_drain'
        if preparing and not stopping:
            pp=preparing/'prepared/plan.json'
            if pp.exists():
                merge(plan,json.loads(pp.read_text())['units']);dump(plan_path,plan)
            done=preparing/'prepared/complete.json'
            launch=json.loads((preparing/'preparation-launch.json').read_text())
            if done.exists():
                receipt=json.loads(done.read_text());assert receipt['plan_sha256']==hashlib.sha256(pp.read_bytes()).hexdigest()
                preparing=None
            elif not alive(launch):
                stopping='preparation_infrastructure_hold'
        backlog=pending(plan,work/'run')
        # Maintain ready work ahead of the execution slots, while at most one preparation
        # batch runs. This is a prefetch watermark, not extra model concurrency.
        if not stopping and preparing is None and backlog<capacity:
            if next_offset>=1655:stopping='source_pool_exhausted_drain'
            elif shutil.disk_usage(root).free<20*1024**3:stopping='storage_hold_drain'
            else:
                offset=next_offset;next_offset+=100;preparing=root/f'wave-{offset:04d}';preparing.mkdir(mode=0o700,exist_ok=False)
                indices=list(range(offset,min(offset+100,1655)))
                pages=[Path(x) for x in catalog['pages'] if offset<=int(Path(x).stem.split('-')[1])<offset+100]
                command=[sys.executable,str(source/'agentic/experiments/cli-gym-pilot-20261104/prepare.py'),
                         '--rows',*map(str,pages),'--output',str(preparing/'prepared'),'--indices',*map(str,indices),
                         '--canonicalize-selectors','--storage-root',str(root)]
                with (preparing/'preparation.log').open('xb') as log:
                    child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
                f=(Path('/proc')/str(child.pid)/'stat').read_text().split(') ')[1].split()
                dump(preparing/'preparation-launch.json',{'pid':child.pid,'start_ticks':f[19],'argv':command,
                     'source_commit':cfg['source_commit'],'created_at':time.time(),'new_model_requests':0})
                wave_records.append(str(preparing))
                dump(preparing/'active_runtime_selection.json',{'source_commit':cfg['source_commit'],'source_rows':indices,
                     'role':'preparation_only','paid_dispatch_root':str(work),'new_model_requests':0})
        if stopping and not complete.exists():
            dump(complete,{'plan_sha256':hashlib.sha256(plan_path.read_bytes()).hexdigest(),'reason':stopping,'finished_at':time.time()})
        coordinator=json.loads((work/'production-launch.json').read_text())
        finished=(work/'run/coordinator-finished.json').exists()
        if not alive(coordinator) and not finished:
            stopping='coordinator_missing';dump(work/'runtime-hold.json',{'reason':stopping,'checked_at':time.time()})
        progress={'checked_at':time.time(),'phase':stopping or 'rolling_running','valid_sft':count,'target':500,
                  'requested_range':[500,1000],'runs':list(map(str,runs)),'wave':str(work),
                  'queue_policy':'cross_wave_shared','worker_capacity':capacity,'ready_backlog':backlog,
                  'preparing_wave':str(preparing) if preparing else None,'preparation_waves':wave_records,
                  'next_source_offset':next_offset,'published_units':len(plan['units']),'old_attempt_replays':0}
        dump(root/'campaign-progress.json',progress);dump(work/'progress.json',progress)
        if finished or stopping=='coordinator_missing':return
        time.sleep(5)


if __name__=='__main__':main()
