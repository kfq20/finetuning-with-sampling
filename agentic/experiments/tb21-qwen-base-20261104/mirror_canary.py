"""One-image unpaid ACR bootstrap; immutable manifest, original dataset untouched."""
import os,json,subprocess,hashlib,pathlib,time,shutil,sys
from dotenv import dotenv_values
r=pathlib.Path(sys.argv[1]);os.umask(0o077)
v=dotenv_values('/mnt/ecs-tb4/cli-gym-scale-20261104/support/private/sandbox.env',interpolate=False)
c='/mnt/ecs-tb4/relayforge_scenario_deepseek_aliyun_20261028_v1/bin/crane'
a=r/'private/registry-auth';a.mkdir(parents=True,exist_ok=True)
env={**os.environ,'DOCKER_CONFIG':str(a)}
def run(args,**kw):
 p=subprocess.run([c,*args],env=env,text=True,capture_output=True,timeout=600,**kw)
 if p.returncode: raise RuntimeError(p.stderr[-1200:])
 return p.stdout.strip()
host='acr-rf-sg-registry.ap-southeast-8.cr.aliyuncs.com'
run(['auth','login',host,'-u',v['REGISTRY_USERNAME'],'--password-stdin'],input=v['REGISTRY_PASSWORD'])
src='alexgshaw/fix-git:20260403';digest=run(['digest','--platform','linux/amd64',src]);dst=host+'/mindlab/test:fanqi-tb21-base-1104-'+digest.split(':')[1][:24]
run(['copy','--platform','linux/amd64',src.split(':')[0]+'@'+digest,dst])
destdigest=run(['digest',dst]);assert destdigest==digest
record={'source_image':src,'source_digest':digest,'mirrored_image':dst.split(':')[0]+'@'+destdigest,'manifest_digest_preserved':True,'time':time.time(),'model_requests':0}
(r/'images').mkdir(exist_ok=True);(r/'images/fix-git.json').write_text(json.dumps(record,indent=2)+'\n')
source=r/'dataset/tasks/fix-git';target=r/'prepared-tasks/fix-git';shutil.copytree(source,target,dirs_exist_ok=True)
f=target/'task.toml';s=f.read_text();assert s.count(src)==1;f.write_text(s.replace(src,record['mirrored_image']))
print(json.dumps(record))
