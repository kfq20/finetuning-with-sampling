"""Read-only SDK capability probe; credential arrives over stdin and is never saved."""
import asyncio
import json
import logging
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

logging.disable(logging.CRITICAL)
print('READY: enter transient credential JSON on stdin', flush=True)
identity = json.loads(sys.stdin.readline())
key = identity['token']
assert key.startswith('sk-')
import mint
import httpx
from tinker._client import AsyncTinker

async def probe(base, credential=None, transport="httpx"):
    http_client = httpx.AsyncClient(timeout=30) if transport == "httpx" else None
    # The low-level SDK GET avoids ServiceClient's metadata create_session call.
    try:
        async with AsyncTinker(api_key=credential or key, base_url=base, timeout=30, max_retries=0, http_client=http_client) as client:
            result = await client.service.get_server_capabilities()
            payload = result.model_dump(mode='json')
            return {'base_url':base,'transport':transport,'ok':True,'supported_models':payload.get('supported_models'),
                    'other_capability_fields':sorted(k for k in payload if k!='supported_models')}
    except Exception as error:
        response = getattr(error, 'response', None)
        chain=[]
        current=error
        while current is not None and len(chain)<4:
            chain.append(type(current).__name__+': '+str(current).replace(key,'<redacted>')[:500])
            current=current.__cause__
        return {'base_url':base,'transport':transport,'cause_chain':chain,'ok':False,'error_type':type(error).__name__,
                'status_code':getattr(error,'status_code',None),
                'request_id':(response.headers.get('x-request-id') if response is not None else None),
                'error':str(error).replace(key,'<redacted>')[:1000]}

async def main():
    default_transport = await probe("https://mintcn.macaron.xin/train", transport="pyqwest")
    checks=[]
    for base in ('https://mintcn.macaron.xin','https://mintcn.macaron.xin/train'):
        checks.append(await probe(base))
    negative = await probe("https://mintcn.macaron.xin/train", "sk-invalid-readonly-control")
    report={'checked_at':datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
            'sdk_source_commit':'96d66d0027c2b22104ad0a7b941cbcdb669ce65d',
            'mint_version':mint.__version__,'tinker_version':mint.__tinker_version__,
            'requests':'get_server_capabilities only','created_sessions':0,
            'created_lora_clients':0,'optimizer_steps':0,'checks':checks,'invalid_key_control':negative,'default_transport_probe':default_transport}
    output=Path('/Users/fancy/project/finetuning-with-sampling-data/mindforge-1step-20261105/mint-sdk-readonly-probe.json')
    output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(report,ensure_ascii=False),flush=True)

asyncio.run(main())
identity.clear()
key=''
