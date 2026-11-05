"""Bounded base/checkpoint SDK comparison; no training model or optimizer calls."""
import json
import logging
import sys
import time
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

root=Path(sys.argv[1]);root.mkdir(exist_ok=False)
key=''
logging.disable(logging.CRITICAL)
def save(name,value):
    text=json.dumps(value,ensure_ascii=False,indent=2,default=str)
    if key:text=text.replace(key,'<redacted>')
    (root/name).write_text(text+'\n')
def event(**values):
    values['at']=datetime.now(ZoneInfo('Asia/Shanghai')).isoformat()
    text=json.dumps(values,default=str)
    if key:text=text.replace(key,'<redacted>')
    with (root/'http-events.jsonl').open('a') as f:f.write(text+'\n')
    print(text,flush=True)

print('READY: transient credential on stdin',flush=True)
key=json.loads(sys.stdin.readline())['token']
import mint
import httpx
async def response_hook(response):
    data={}
    if response.request.url.path.endswith(('/asample','/retrieve_future','/create_sampling_session','/client/config')):
        try:data=json.loads(await response.aread())
        except Exception:pass
    selected={k:v for k,v in data.items() if k in ('request_id','sampling_session_id','queue_state','queue_state_reason','status','retry_after_s','error','message')}
    event(method=response.request.method,path=response.request.url.path,status=response.status_code,
          request_id=response.headers.get('x-request-id'),selected=selected)
service=None
try:
    service=mint.ServiceClient(api_key=key,base_url='https://mintcn.macaron.xin/train',timeout=90,max_retries=0,
        http_client=httpx.AsyncClient(timeout=90,event_hooks={'response':[response_hook]}),
        user_metadata={'experiment':'saved-sampler-diagnosis-20261105','training':'none'})
    sid=service.holder._session_id
    save('session.json',{'session_id':sid,'created_training_clients':0})
    config=service.holder.get_client_config()
    save('client-config.json',{name:getattr(config,name,None) for name in ('enable_grpc_retrieve_future','grpc_target','use_pyqwest_transport','sample_no_retries','pjwt_auth_enabled')})
    previous=Path('/Users/fancy/project/finetuning-with-sampling-data/mint-sdk-one-step-20261105-a1')
    binding=json.loads((previous/'training-acceptance.json').read_text())
    prompt=mint.types.ModelInput.from_ints(json.loads((previous/'plan.json').read_text())['smoke_prompt_ids'])
    samplers={
      'base':service.create_sampling_client(base_model='Qwen/Qwen3.8-27B'),
      'checkpoint':service.create_sampling_client(model_path=binding['sampler_path']),
    }
    save('samplers.json',{name:{'sampler_id':s._sampling_session_id,'model_path':binding['sampler_path'] if name=='checkpoint' else None} for name,s in samplers.items()})
    futures={name:s.sample(prompt=prompt,num_samples=1,
        sampling_params=mint.types.SamplingParams(max_tokens=1,temperature=0,stop=['<|im_end|>'])) for name,s in samplers.items()}
    results={}
    for name,future in futures.items():
        started=time.monotonic()
        try:
            value=future.result(timeout=60)
            results[name]={'ok':True,'output_tokens':[list(s.tokens) for s in value.sequences],
                           'seconds_waited':time.monotonic()-started}
        except Exception as error:
            results[name]={'ok':False,'error_type':type(error).__name__,'error':str(error),
                           'seconds_waited':time.monotonic()-started}
        save('results.json',results)
        event(probe=name,result=results[name])
finally:
    if service is not None:
        sid=service.holder._session_id
        response=httpx.delete('https://mintcn.macaron.xin/train/api/v1/mint/sessions/'+sid,
            headers={'X-API-Key':key},timeout=40)
        save('cleanup.json',{'session_id':sid,'status':response.status_code,'response':response.json()})
        event(cleanup_status=response.status_code)
    key=''
