"""Register another organisation using reviewed scoped views; never imports/resets source data."""
import argparse,json,os,re,sys,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from sqlalchemy import create_engine,inspect,text
from product.config import ROOT
from product.sources import safe_tenant
from product.storage import engine

def onboard(manifest,url):
    tenant=safe_tenant(manifest['tenant_id']);schema=manifest.get('view_schema','insight')
    if tenant=='school-demo':raise ValueError('Use a new organisation ID; the supplied school is preserved.')
    if not re.fullmatch('[a-z][a-z0-9_]{0,62}',schema):raise ValueError('Invalid reporting schema name.')
    policies=manifest['policies']
    for role in ['Admin','Faculty','Student']:
        policy=policies.get(role,{})
        if not all(k in policy for k in ['scope','can','cannot','questions']):raise ValueError('Every supported role needs explicit capabilities and restrictions.')
    candidate=create_engine(url,connect_args={'connect_timeout':5},hide_parameters=True)
    with candidate.connect() as c:
        role=c.execute(text('SELECT rolsuper,rolcreatedb,rolcreaterole FROM pg_roles WHERE rolname=current_user')).one()
        if any(role):raise ValueError('Use a restricted source login without superuser, role or database creation privileges.')
        if c.execute(text('SELECT has_schema_privilege(current_user,:schema,\'CREATE\')'),{'schema':schema}).scalar():raise ValueError('The query login must not own or create objects in the reporting schema.')
        # Refuse a broad login even though generated SQL is also validated and read-only.
        excessive=c.execute(text("""SELECT n.nspname,p.relname FROM pg_class p JOIN pg_namespace n ON n.oid=p.relnamespace
          WHERE n.nspname NOT IN ('pg_catalog','information_schema') AND n.nspname NOT LIKE 'pg_toast%'
          AND p.relkind IN ('r','p','v','m','f') AND (
            (n.nspname<>:schema AND has_table_privilege(p.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER'))
            OR (n.nspname=:schema AND (p.relkind<>'v' AND has_table_privilege(p.oid,'SELECT')))
            OR has_table_privilege(p.oid,'INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
          ) LIMIT 1"""),{'schema':schema}).first()
        if excessive:raise ValueError('The source login has raw-table or write privileges; grant SELECT only on reviewed reporting views.')
        inspector=inspect(candidate);views=inspector.get_view_names(schema=schema)
        if not views:raise ValueError('No reviewed reporting views were found.')
        for view in views:
            properties=c.execute(text('SELECT reloptions,pg_get_userbyid(relowner) AS owner FROM pg_class p JOIN pg_namespace n ON n.oid=p.relnamespace WHERE n.nspname=:schema AND p.relname=:name'),{'schema':schema,'name':view}).mappings().one()
            if 'security_barrier=true' not in (properties['reloptions'] or []):raise ValueError('Reporting views must use security_barrier=true.')
        catalogue={v:{x['name']:str(x['type']) for x in inspector.get_columns(v,schema=schema)} for v in views}
        contract={'user_id','username','first_name','last_name','role_name','is_active'}
        if not contract.issubset(catalogue.get('users',{})):raise ValueError('The reviewed users view must expose the documented redacted identity contract.')
    with engine().begin() as c:
        if c.execute(text('SELECT 1 FROM insight_app.sources WHERE tenant_id=:tenant'),{'tenant':tenant}).scalar():raise ValueError('This organisation ID already exists; refusing to overwrite it.')
        c.execute(text('INSERT INTO insight_app.sources(tenant_id,name,adapter,view_schema,source_schema,policies,overview,catalog) VALUES(:tenant,:name,:adapter,:schema,:source,CAST(:policies AS jsonb),CAST(:overview AS jsonb),CAST(:catalog AS jsonb))'),{'tenant':tenant,'name':manifest['name'],'adapter':manifest.get('adapter','generic'),'schema':schema,'source':manifest.get('source_schema',schema),'policies':json.dumps(policies),'overview':json.dumps(manifest.get('overview',[])),'catalog':json.dumps({'schema':schema,'reporting_views':catalogue})})
        # Store the secret reference atomically with owner-only permissions. Not exposed through APIs.
        path=ROOT/'.runtime/tenants.json';registry=json.loads(path.read_text()) if path.exists() else {}
        registry[tenant]={'query_url':url}
        fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.tenant-')
        try:
            with os.fdopen(fd,'w') as f:json.dump(registry,f)
            os.replace(tmp,path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
    return {'tenant_id':tenant,'views':len(views),'registered':True}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--manifest',required=True);parser.add_argument('--query-url-env',required=True,help='Name of a server-side environment variable containing the read-only source URL');args=parser.parse_args()
    if not os.getenv(args.query_url_env):raise SystemExit('The named source connection environment variable is missing.')
    try:print(onboard(json.loads(Path(args.manifest).read_text()),os.environ[args.query_url_env]))
    except Exception as error:raise SystemExit('Onboarding failed ('+type(error).__name__+'). Check the reviewed manifest, view contract and restricted connection. No source data was reset.')
