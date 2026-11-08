"""Revalidate saved live responses against the current database and combine provider coverage."""
import argparse,json,sys,uuid
from datetime import datetime,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import dotenv_values
from sqlalchemy import create_engine,text
from product.config import ROOT
from product.evaluation import CASES,verify,serial
parser=argparse.ArgumentParser();parser.add_argument('reports',nargs='+');parser.add_argument('--output',default='docs/evaluation/acceptance-matrix.json');args=parser.parse_args()
reports=[(name,json.loads((ROOT/name).read_text())) for name in args.reports]
password=dotenv_values(ROOT/'.runtime/services.env')['PRODUCT_POSTGRES_PASSWORD']
engine=create_engine(f'postgresql+psycopg2://postgres:{password}@127.0.0.1:55433/school_ai',hide_parameters=True)
result={'run_id':str(uuid.uuid4()),'created_at':datetime.now(timezone.utc).isoformat(),'provider':'multiple','model':'See per-case provider/model','method':'Saved live responses independently revalidated against current source SQL and exact manual chunks. Provider coverage; not a single-provider success claim.','cases':[]}
with engine.connect() as connection:
    for case in CASES:
        expected=[dict(r) for r in connection.execute(text(case['reference_sql'])).mappings()] if case.get('reference_sql') else None
        candidates=[]
        for name,report in reports:
            for entry in report.get('cases',[]):
                if entry['id']!=case['id'] or not entry.get('response'):continue
                checks=verify(case,entry['response'],expected,connection)
                candidates.append({**entry,'question':case['question'],'checks':checks,'expected':serial(expected),'passed':all(checks.values()),'evidence_report':name,'provider':report['provider'],'model':report['model']})
        passing=[entry for entry in candidates if entry['passed']]
        result['cases'].append(passing[-1] if passing else {'id':case['id'],'question':case['question'],'passed':False,'checks':{'passing_live_evidence':False}})
result['passed']=sum(c['passed'] for c in result['cases']);result['total']=len(CASES)
(ROOT/args.output).write_text(json.dumps(result,indent=2,default=str)+'\n')
print('Independently revalidated coverage:',result['passed'],'/',result['total'])
raise SystemExit(0 if result['passed']==result['total'] else 1)
