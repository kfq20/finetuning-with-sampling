"""Switch only NEW owned loopback connections; never restart paid workers."""
import hashlib
import json
from pathlib import Path
import shlex
import subprocess
import time
import urllib.request

ROOT=Path('/mnt/ecs-tb4/cli-gym-scale-20261104')


def dump(path,value):
    p=path.with_suffix('.tmp');p.write_text(json.dumps(value,indent=2)+'\n');p.replace(path)


def main():
    r=ROOT;rec=r/'native-endpoint-recovery-20261104';d=rec/'direct-route-20261104'
    assert not (d/'SWITCH.json').exists() and not (r/'USER_STOP.json').exists()
    admission=json.loads((d/'ADMISSION.json').read_text());assert admission['passed']
    digest=hashlib.sha256((rec/'qwen-direct-private.json').read_bytes()).hexdigest()
    assert admission['direct_config_sha256']==digest
    launch=json.loads((d/'launch.json').read_text());proc=Path('/proc')/str(launch['pid'])
    fields=(proc/'stat').read_text().split(') ')[1].split()
    assert fields[19]==launch['start_ticks'] and fields[0]!='Z'
    assert hashlib.sha256((d/'http_bridge.py').read_bytes()).hexdigest()==launch['entry_sha256']
    rules=subprocess.run(['iptables','-t','nat','-S','OUTPUT'],check=True,capture_output=True,text=True).stdout
    append_rules=[x for x in rules.splitlines() if x.startswith('-A ')]
    matches=[(i+1,line) for i,line in enumerate(append_rules) if 'cli-gym-native-compression-20261104' in line]
    assert len(matches)==1
    index,old=matches[0];tokens=shlex.split(old)
    assert tokens[tokens.index('--dport')+1]=='18131' and tokens[tokens.index('--to-ports')+1]=='18132'
    workers=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit():continue
        try:
            argv=(p/'cmdline').read_bytes().split(b'\0')
            if b'append_rewrite.terminus.production' in argv and b'unit' in argv and b'--output' in argv:
                out=Path(argv[argv.index(b'--output')+1].decode())
                if r in out.parents:
                    f=(p/'stat').read_text().split(') ')[1].split()
                    if f[0]!='Z':workers.append({'pid':int(p.name),'start_ticks':f[19],'unit':out.name})
        except FileNotFoundError:pass
    assert len(workers)<=8
    closed={str(p.relative_to(r)):hashlib.sha256(p.read_bytes()).hexdigest() for p in r.glob('**/student/receipt.json')}
    dump(d/'switch-before.json',{'rules':rules,'workers':workers,'closed_receipts':closed,'campaign_selection':json.loads((r/'campaign-selection.json').read_text())})
    command=['iptables','-w','5','-t','nat','-R','OUTPUT',str(index),'-d','127.0.0.1/32','-p','tcp','--dport','18131','-m','comment','--comment','cli-gym-native-direct-20261104','-j','REDIRECT','--to-ports','18133']
    subprocess.run(command,check=True,capture_output=True,text=True)
    switched=time.time()
    request=urllib.request.Request('http://127.0.0.1:18131/v1/models',headers={'Authorization':'Bearer local'})
    with urllib.request.urlopen(request,timeout=20) as response:
        assert response.status==200;assert 'Qwen/Qwen3.8-27B' in [x['id'] for x in json.load(response)['data']]
    for path,checksum in closed.items():assert hashlib.sha256((r/path).read_bytes()).hexdigest()==checksum
    value={'switched_at':switched,'mode':'direct-http','new_connections_only':True,'old_connections_preserved':True,'no_ssh_fallback':True,'loopback_port':18131,'bridge_port':18133,'direct_config_sha256':digest,'bridge_entry_sha256':launch['entry_sha256'],'bridge_launch':str(d/'launch.json'),'admission_sha256':hashlib.sha256((d/'ADMISSION.json').read_bytes()).hexdigest(),'adopted_workers_untouched':workers,'closed_receipts_unchanged':len(closed),'model_replays':0,'worker_capacity':8,'iptables_command':command,'previous_owned_rule':old,'effective_identity':'original core/config plus this transport selection'}
    dump(d/'SWITCH.json',value);dump(r/'transport-selection.json',value)
    campaign=json.loads((r/'campaign-selection.json').read_text());campaign['transport_selection']=str(r/'transport-selection.json');campaign['transport_mode']='direct-http';dump(r/'campaign-selection.json',campaign)
    wave=Path(json.loads((r/'campaign-progress.json').read_text())['wave']);p=wave/'active_runtime_selection.json';selection=json.loads(p.read_text());selection['transport_selection']=str(r/'transport-selection.json');selection['transport_mode']='direct-http';dump(p,selection)
    print(json.dumps({'mode':'direct-http','workers_untouched':len(workers),'closed_receipts_unchanged':len(closed),'model_replays':0,'switched_at':switched}))


if __name__=='__main__':main()
