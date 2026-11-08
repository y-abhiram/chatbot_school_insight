"""Create the new product database once; never resets existing school data."""
import json,os,secrets,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import psycopg2
from psycopg2 import sql
from argon2 import PasswordHasher
from sqlalchemy import create_engine,inspect,text
from dotenv import dotenv_values
from product.config import ROOT,admin_database_url,database_url,env_value

engine=create_engine(admin_database_url(),hide_parameters=True)
with engine.connect() as conn:
    exists=conn.execute(text("SELECT EXISTS(SELECT 1 FROM information_schema.schemata WHERE schema_name='school')")).scalar()
if exists:
    if '--if-needed' in sys.argv and (ROOT/'.runtime/product.json').exists():
        import subprocess
        subprocess.run([sys.executable,str(ROOT/'scripts/migrate_product.py')],check=True)
        print('Existing deployment preserved; additive migrations applied.')
        raise SystemExit(0)
    raise SystemExit('Database already has a school schema; refusing to reset. Restore matching runtime state before retrying an existing deployment.')
query_password=env_value('PRODUCT_QUERY_PASSWORD') or secrets.token_urlsafe(36)
app_password=env_value('PRODUCT_APP_PASSWORD') or secrets.token_urlsafe(36)
raw=engine.raw_connection()
with raw.cursor() as cur:
    cur.execute((ROOT/'school_management_postgres92.sql').read_text())
    cur.execute('SET search_path TO public')
    cur.execute((ROOT/'scripts/product_schema.sql').read_text())
    cur.execute(sql.SQL('CREATE ROLE insight_query LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT').format(sql.Literal(query_password)))
    cur.execute(sql.SQL('CREATE ROLE insight_service LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT').format(sql.Literal(app_password)))
    cur.execute('GRANT USAGE ON SCHEMA insight TO insight_query; GRANT SELECT ON ALL TABLES IN SCHEMA insight TO insight_query; GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA insight TO insight_query; ALTER ROLE insight_query SET default_transaction_read_only=on')
    cur.execute(sql.SQL('REVOKE TEMPORARY ON DATABASE {} FROM PUBLIC').format(sql.Identifier(engine.url.database)))
    cur.execute((ROOT/'scripts/chat_permissions.sql').read_text())
    cur.execute('GRANT USAGE ON SCHEMA public TO insight_service; GRANT USAGE ON SCHEMA insight_app TO insight_service; GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA insight_app TO insight_service; GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA insight_app TO insight_service')
    cur.execute("SELECT u.user_id,u.username,r.role_name FROM school.users u JOIN school.roles r USING(role_id) ORDER BY u.user_id")
    identities=cur.fetchall()
    accounts=[]
    for user_id,username,role in identities:
        temporary=secrets.token_urlsafe(14)
        cur.execute('INSERT INTO insight_app.accounts(tenant_id,user_id,username,password_hash) VALUES(%s,%s,%s,%s)',('school-demo',user_id,username,PasswordHasher().hash(temporary)))
        accounts.append({'username':username,'role':role,'password':temporary})
raw.commit();raw.close()
# Complete catalogue from actual PostgreSQL metadata, not inferred column names.
inspector=inspect(engine)
catalog={'schema':'school','tables':{},'views':{},'verified_counts':{},'foreign_keys':[]}
for table in inspector.get_table_names(schema='school'):
    cols=[{'name':c['name'],'type':str(c['type']),'nullable':c['nullable']} for c in inspector.get_columns(table,schema='school')]
    fks=inspector.get_foreign_keys(table,schema='school')
    catalog['tables'][table]={'columns':cols,'primary_key':inspector.get_pk_constraint(table,schema='school'),'foreign_keys':fks,'indexes':inspector.get_indexes(table,schema='school'),'unique_constraints':inspector.get_unique_constraints(table,schema='school'),'checks':inspector.get_check_constraints(table,schema='school')}
    catalog['foreign_keys'] += [{'table':table,**fk} for fk in fks]
for view in inspector.get_view_names(schema='school'):
    catalog['views'][view]={'definition':inspector.get_view_definition(view,schema='school'),'columns':[{'name':c['name'],'type':str(c['type'])} for c in inspector.get_columns(view,schema='school')]}
with engine.begin() as conn:
    for table in ['users','students','faculty','timetable','marks']:
        catalog['verified_counts'][table]=conn.execute(text(f'SELECT COUNT(*) FROM school.{table}')).scalar()
    catalog['verified_counts']['pending_leaves']=conn.execute(text('SELECT COUNT(*) FROM school.v_pending_leaves')).scalar()
    conn.execute(text('INSERT INTO insight_app.schema_catalog(id,source) VALUES(1,CAST(:catalog AS jsonb))'),{'catalog':json.dumps(catalog,default=str)})
assert len(catalog['tables'])==29 and len(catalog['views'])==4
state={'app_url':database_url('insight_service',app_password).render_as_string(hide_password=False),'query_url':database_url('insight_query',query_password).render_as_string(hide_password=False)}
catalog_path=ROOT/'.runtime/verified-schema.json' if os.getenv('PRODUCT_DATABASE_HOST') else ROOT/'docs/verified-schema.json'
for path,value in [(ROOT/'.runtime/product.json',state),(ROOT/'.runtime/demo-accounts.json',accounts),(catalog_path,catalog)]:
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600 if '.runtime' in str(path) else 0o644)
    with os.fdopen(fd,'w') as out:json.dump(value,out,indent=2,default=str)
print('Verified:',len(catalog['tables']),'tables,',len(catalog['views']),'views;',catalog['verified_counts'])
print('One-time demo credentials: .runtime/demo-accounts.json (owner-only). No source passwords were changed.')

# Apply additive product migrations after first-time import and secret registration.
import subprocess,sys
subprocess.run([sys.executable,str(ROOT/'scripts/migrate_product.py')],check=True)
