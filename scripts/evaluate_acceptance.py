"""Run all 17 original questions against live SQL/RAG; optional explicit LangSmith publication."""
import argparse,json,sys,time,uuid
from pathlib import Path
from datetime import datetime,timezone
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import dotenv_values
from sqlalchemy import create_engine,text
from product.config import ROOT
from product.evaluation import CASES,serial,verify
from product.auth import Identity
from product.storage import rows
from product.agent import graph
from product.providers import select_provider
parser=argparse.ArgumentParser();parser.add_argument('--provider',default='openai',choices=['openai','gemini','groq']);parser.add_argument('--ids',default='');parser.add_argument('--model',default='');parser.add_argument('--resume',action='store_true');parser.add_argument('--publish-langsmith',action='store_true');parser.add_argument('--output',default='docs/evaluation/acceptance-results.json');args=parser.parse_args()
case_ids={int(x) for x in args.ids.split(',') if x} or set(range(1,18))
password=dotenv_values(ROOT/'.runtime/services.env')['PRODUCT_POSTGRES_PASSWORD']
admin=create_engine(f'postgresql+psycopg2://postgres:{password}@127.0.0.1:55433/school_ai')
row=rows("SELECT * FROM insight_app.identities WHERE username='admin01' AND tenant_id='school-demo'")[0]
user=Identity(**{k:row[k] for k in Identity.__dataclass_fields__});provider,model=select_provider(args.provider,args.model)
output={'run_id':str(uuid.uuid4()),'provider':provider,'model':model,'created_at':datetime.now(timezone.utc).isoformat(),'method':'Live model and independently executed source SQL; page/concept/citation checks','requested_case_ids':sorted(case_ids),'complete':False,'cases':[]}
existing_path=ROOT/args.output
if args.resume and existing_path.exists():
    prior=json.loads(existing_path.read_text())
    if prior.get('model')==model and prior.get('provider')==provider:output['cases']=[c for c in prior.get('cases',[]) if c.get('passed')]
with admin.connect() as connection:
    for case in CASES:
        if case['id'] not in case_ids:continue
        if any(c['id']==case['id'] for c in output['cases']):continue
        expected=[dict(r) for r in connection.execute(text(case['reference_sql'])).mappings()] if case.get('reference_sql') else None
        question=case['question']
        if case.get('columns'):question+='\nFor an inspectable report, include these output column names: '+', '.join(case['columns'])+'.'
        start=time.monotonic()
        try:
            for attempt in range(3):
                try:
                    result=graph.invoke({'question':question,'identity':user,'provider':provider,'model':model,'history':[]})['response'];break
                except Exception as retry_error:
                    if any(term in str(retry_error).lower() for term in ('per day','rpd','daily quota')):raise
                    if type(retry_error).__name__ not in ('RateLimitError','OpenAIRateLimitError','APIError','APIConnectionError','APITimeoutError','InternalServerError') or attempt==2:raise
                    print('Provider transient error; bounded retry',attempt+1,'for case',case['id'],flush=True)
                    time.sleep(10*(attempt+1))
            checks=verify(case,result,expected,connection)
            entry={'id':case['id'],'question':case['question'],'expected':serial(expected),'checks':checks,'passed':all(checks.values()),'response':serial(result),'duration_ms':round((time.monotonic()-start)*1000)}
        except Exception as error:entry={'id':case['id'],'question':case['question'],'passed':False,'error_type':type(error).__name__,'duration_ms':round((time.monotonic()-start)*1000)}
        output['cases'].append(entry)
        output['passed']=sum(c['passed'] for c in output['cases']);output['total']=len(output['cases'])
        print(('PASS' if entry['passed'] else 'FAIL'),case['id'],case['question'],entry.get('checks',entry.get('error_type')),flush=True)
        path=ROOT/args.output;path.parent.mkdir(exist_ok=True,parents=True);path.write_text(json.dumps(output,indent=2,default=str))
output['complete']=all(any(c['id']==id for c in output['cases']) for id in case_ids)
output['passed']=sum(c['passed'] for c in output['cases']);output['total']=len(output['cases']);path.write_text(json.dumps(output,indent=2,default=str))
print('Acceptance:',output['passed'],'/',output['total'],flush=True)
if args.publish_langsmith:
    from product.langsmith_eval import publish
    print('LangSmith evaluation:',publish(output),flush=True)
raise SystemExit(0 if output['passed']==output['total'] else 1)
