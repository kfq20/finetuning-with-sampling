"""One explicitly authorized SDK acceptance, using frozen datums; no auto replay.

Credentials arrive only on stdin. Dataset preparation and tokenization happen
before this worker; no serving tokenizer can silently rewrite the frozen IDs.
"""
import hashlib
import json
import logging
import math
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

logging.disable(logging.CRITICAL)
root = Path(sys.argv[1]).resolve()
plan = json.loads((root/'plan.json').read_text())
secret = ''
service = None
stage = 'preflight'

def dump(name, value):
    path=root/name
    text=json.dumps(value,ensure_ascii=False,indent=2,default=str)
    if secret:
        text=text.replace(secret,'<redacted>')
    temporary=path.with_suffix(path.suffix+'.new')
    temporary.write_text(text+'\n')
    temporary.replace(path)

def event(name, **values):
    row={'at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),'stage':name,**values}
    text=json.dumps(row,ensure_ascii=False,default=str)
    if secret:text=text.replace(secret,'<redacted>')
    with (root/'events.jsonl').open('a') as f:f.write(text+'\n')
    dump('status.json',row)
    print(text,flush=True)

def result(value):
    return value.result() if hasattr(value,'result') else value

def obj(value):
    return value.model_dump(mode='json') if hasattr(value,'model_dump') else value

def call(name, function):
    global stage
    stage=name
    event(name+'_started')
    started=time.monotonic()
    value=result(function())
    dump(name+'.json',obj(value))
    event(name+'_completed',seconds=round(time.monotonic()-started,3))
    return value

def nll(value, datum):
    outputs=value.loss_fn_outputs
    logprobs=outputs[0]['logprobs']
    if hasattr(logprobs,'data'):logprobs=logprobs.data
    elif hasattr(logprobs,'tolist'):logprobs=logprobs.tolist()
    weights=datum.loss_fn_inputs['weights']
    if hasattr(weights,'data'):weights=weights.data
    elif hasattr(weights,'tolist'):weights=weights.tolist()
    assert len(logprobs)==len(weights)
    assert all(math.isfinite(float(x)) for x,w in zip(logprobs,weights) if w)
    total=sum(weights)
    assert total>0
    return -sum(float(x)*float(w) for x,w in zip(logprobs,weights))/total

try:
    for name, expected in plan['file_sha256'].items():
        assert hashlib.sha256((root/name).read_bytes()).hexdigest()==expected, name
    import mint
    import httpx
    def read_datum(name):
        payload=json.loads((root/name).read_text())
        return mint.types.Datum(model_input=mint.types.ModelInput.from_ints(payload['model_input_ids']),
            loss_fn_inputs={'target_tokens':payload['target_tokens'],'weights':payload['weights']})
    datum=read_datum('datum.json')
    eval_datum=read_datum('eval-datum.json')
    adam=mint.types.AdamParams(**plan['optimizer'])
    assert plan['training']['max_steps']==1 and plan['training']['batch_size']==1
    print('READY: transient credential JSON on stdin',flush=True)
    secret=json.loads(sys.stdin.readline())['token']
    assert secret.startswith('sk-')
    # Never clear an existing claim or create a second LoRA client on failure.
    with (root/'claim.json').open('x') as f:
        json.dump({'started_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
                   'plan_sha256':hashlib.sha256((root/'plan.json').read_bytes()).hexdigest()},f)
    stage='service_client'
    event('service_client_started')
    service=mint.ServiceClient(api_key=secret,base_url=plan['base_url'],
        timeout=120,max_retries=0,http_client=httpx.AsyncClient(timeout=120),
        user_metadata={'experiment':plan['experiment'],'authorization':'user-sdk-one-step-override'})
    session_id=service.holder._session_id
    dump('identity.json',{'session_id':session_id,'base_model':plan['model'],
        'credential_sha256':hashlib.sha256(secret.encode()).hexdigest(),
        'mint_version':mint.__version__,'tinker_version':mint.__tinker_version__})
    event('service_client_ready',session_id=session_id)
    client=call('create_lora',lambda:service.create_lora_training_client(
        base_model=plan['model'],**plan['lora']))
    dump('identity.json',{'session_id':session_id,'model_id':client.model_id,
        'base_model':plan['model'],'credential_sha256':hashlib.sha256(secret.encode()).hexdigest(),
        'mint_version':mint.__version__,'tinker_version':mint.__tinker_version__})
    info=call('model_info',lambda:client.get_info())
    baseline=call('baseline_forward',lambda:client.forward([eval_datum],loss_fn='cross_entropy'))
    baseline_loss=nll(baseline,eval_datum)
    forward=call('forward_backward',lambda:client.forward_backward([datum],loss_fn='cross_entropy'))
    loss=nll(forward,datum)
    assert math.isfinite(loss)
    optimizer=call('optim_step',lambda:client.optim_step(adam))
    name=plan['experiment']+'-step1'
    state=call('save_state',lambda:client.save_state(name+'-state'))
    sampler=call('save_sampler',lambda:client.save_weights_for_sampler(name+'-sampler'))
    assert state.path and sampler.path
    restored=call('load_state',lambda:client.load_state_with_optimizer(state.path))
    evaluated=call('reload_forward',lambda:client.forward([eval_datum],loss_fn='cross_entropy'))
    reload_loss=nll(evaluated,eval_datum)
    dump('training-acceptance.json',{'optimizer_steps':1,'mean_nll':loss,
        'reload_mean_nll':reload_loss,'baseline_mean_nll':baseline_loss,
        'eval_nll_change':reload_loss-baseline_loss,'state_path':state.path,'sampler_path':sampler.path,
        'state_reloaded_with_optimizer':True,'post_reload_forward_finite':True,
        'session_id':session_id,'model_id':client.model_id,
        'supervised_tokens':plan['selected_example']['supervised_tokens']})
    sampling=call('load_sampler',lambda:service.create_sampling_client(model_path=sampler.path))
    sampled=call('sampler_smoke',lambda:sampling.sample(
        prompt=mint.types.ModelInput.from_ints(plan['smoke_prompt_ids']),num_samples=1,
        sampling_params=mint.types.SamplingParams(max_tokens=16,temperature=0,
            stop=['<|im_end|>'])))
    assert len(sampled.sequences)==1 and len(sampled.sequences[0].tokens)>0
    dump('acceptance.json',{'passed':True,'optimizer_steps':1,
        'session_id':session_id,'model_id':client.model_id,'mean_nll':loss,
        'reload_mean_nll':reload_loss,'baseline_mean_nll':baseline_loss,
        'eval_nll_change':reload_loss-baseline_loss,'state_path':state.path,'sampler_path':sampler.path,
        'sampler_smoke_output_tokens':len(sampled.sequences[0].tokens),
        'formal_sft_started':False,'mindforge_job_created':False})
    event('acceptance_passed',optimizer_steps=1,mean_nll=loss,
          reload_mean_nll=reload_loss,smoke_output_tokens=len(sampled.sequences[0].tokens))
except Exception as error:
    dump('error.json',{'stage':stage,'type':type(error).__name__,
        'message':str(error),'traceback':traceback.format_exc(),'automatic_replay':False})
    event('error',failed_stage=stage,error_type=type(error).__name__,message=str(error))
finally:
    if service is not None:
        # Only this exact newly-created metadata session; never list/delete others.
        session_id=getattr(service.holder,'_session_id',None)
        if session_id:
            try:
                import httpx
                response=httpx.delete(plan['base_url']+'/api/v1/mint/sessions/'+session_id,
                    headers={'X-API-Key':secret,'Authorization':'Bearer '+secret},timeout=40)
                dump('cleanup.json',{'session_id':session_id,'http_status':response.status_code,
                    'accepted':response.status_code in (200,404),
                    'checkpoint_deletion_requested':False})
                print(json.dumps({'cleanup_http_status':response.status_code}),flush=True)
            except Exception as error:
                dump('cleanup.json',{'session_id':session_id,'accepted':False,'error':str(error)})
    secret=''
