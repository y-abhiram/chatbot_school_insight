"""Verify real model deltas arrive through the running API before its final response."""
import argparse,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from product.config import ROOT
parser=argparse.ArgumentParser();parser.add_argument('--provider',default='gemini');parser.add_argument('--model',default='');args=parser.parse_args()
account=next(x for x in json.loads((ROOT/'.runtime/demo-accounts.json').read_text()) if x['username']=='stu_divya')
start=time.monotonic();deltas=[];final=None;conversation=None;kind=None
with httpx.Client(base_url='http://127.0.0.1:8100',trust_env=False,timeout=125) as client:
    client.post('/api/auth/login',json={'username':account['username'],'password':account['password']}).raise_for_status()
    try:
        with client.stream('POST','/api/chat/stream',json={'provider':args.provider,'model':args.model,'question':'Help me draft a friendly homework reminder. Write three short sentences for me to review.'}) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if line.startswith('event: '):kind=line[7:]
                elif line.startswith('data: '):
                    data=json.loads(line[6:]);elapsed=round((time.monotonic()-start)*1000)
                    if kind=='conversation':conversation=data['id']
                    if kind=='answer_delta':deltas.append({'time_ms':elapsed,'characters':len(data['text'])})
                    if kind=='result':final={'time_ms':elapsed,'kind':data['kind'],'provider':data['provider'],'model':data['model']}
                    if kind=='error':raise RuntimeError(data['detail'])
        assert deltas and final and deltas[0]['time_ms']<final['time_ms'],'No incremental model text reached the client before the final response.'
        result={'passed':True,'delta_events':len(deltas),'first_delta_ms':deltas[0]['time_ms'],'final':final}
        (ROOT/'.runtime/stream-verification.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
    finally:
        if conversation:client.delete('/api/conversations/'+conversation)
        client.post('/api/auth/logout')
