"""Local operator provisioning for the first admin of a newly onboarded organisation."""
import argparse,getpass,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import text
from product.storage import engine
from product.sources import source_for
from product.auth import Identity,ph
from product.sql_engine import run_sql
parser=argparse.ArgumentParser();parser.add_argument('--tenant',required=True);parser.add_argument('--source-user-id',required=True,type=int);args=parser.parse_args()
source=source_for(args.tenant)
# This CLI is a trusted local operator, not a chatbot tool. Identity and role are verified in the source.
operator=Identity(0,args.tenant,args.source_user_id,'operator','Admin','Local operator')
result=run_sql(f"SELECT user_id,username,first_name,last_name,role_name,is_active FROM {source['view_schema']}.users WHERE user_id={args.source_user_id}",operator)['rows']
if len(result)!=1 or not result[0]['is_active']:raise SystemExit('No active source identity found.')
u=result[0]
if u['role_name'] not in ('Admin','Faculty','Student'):raise SystemExit('Unsupported source role.')
password=getpass.getpass('Initial password (at least 12 characters): ')
if len(password)<12:raise SystemExit('Password is too short.')
with engine().begin() as c:c.execute(text('INSERT INTO insight_app.accounts(tenant_id,user_id,username,password_hash,role_snapshot,name_snapshot) VALUES(:tenant,:uid,:username,:hash,:role,:name)'),{'tenant':args.tenant,'uid':u['user_id'],'username':u['username'],'hash':ph.hash(password),'role':u['role_name'],'name':u['first_name']+' '+(u['last_name'] or '')})
print('Provisioned verified source identity. No school/source record was changed.')
