"""A different organisation uses a separate database without changing core application code."""
import json,uuid
from pathlib import Path
import pytest
from dotenv import dotenv_values
from sqlalchemy import create_engine,text
from psycopg2 import sql
import psycopg2
from fastapi.testclient import TestClient
from scripts.onboard_source import onboard
from product.config import ROOT
from product.storage import engine,rows
from product.sql_engine import run_sql,catalog
from product.auth import Identity,ph
from product.api import app,limiter

@pytest.fixture(scope='module')
def organisation():
    suffix=uuid.uuid4().hex[:10];tenant='verify-org-'+suffix;database='insight_verify_'+suffix;role='insight_verify_'+suffix
    password=dotenv_values(ROOT/'.runtime/services.env')['PRODUCT_POSTGRES_PASSWORD']
    connection=psycopg2.connect(dbname='postgres',user='postgres',password=password,host='127.0.0.1',port=55433);connection.autocommit=True
    with connection.cursor() as c:c.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
    external=create_engine(f'postgresql+psycopg2://postgres:{password}@127.0.0.1:55433/{database}',hide_parameters=True)
    with external.begin() as c:
        c.execute(text('CREATE SCHEMA business;CREATE SCHEMA reporting;CREATE TABLE business.directory(user_id int,username text,first_name text,last_name text,role_name text,is_active boolean);CREATE TABLE business.orders(order_id int,customer_id int,amount numeric)'))
        c.execute(text("INSERT INTO business.directory VALUES(101,'org_admin','Organisation','Admin','Admin',true),(102,'customer','Verified','Customer','Student',true);INSERT INTO business.orders VALUES(1,102,42),(2,999,99)"))
        c.execute(text("CREATE VIEW reporting.users WITH(security_barrier=true) AS SELECT * FROM business.directory WHERE current_setting('insight.tenant',true)=:tenant AND (current_setting('insight.role',true)='Admin' OR user_id::text=current_setting('insight.user_id',true))"),{'tenant':tenant})
        c.execute(text("CREATE VIEW reporting.orders WITH(security_barrier=true) AS SELECT * FROM business.orders WHERE current_setting('insight.tenant',true)=:tenant AND (current_setting('insight.role',true)='Admin' OR customer_id::text=current_setting('insight.user_id',true))"),{'tenant':tenant})
    with connection.cursor() as c:
        c.execute(sql.SQL('CREATE ROLE {} LOGIN PASSWORD {} NOSUPERUSER NOCREATEDB NOCREATEROLE').format(sql.Identifier(role),sql.Literal('test-only-long-password')))
    with external.begin() as c:
        c.execute(text(f'GRANT USAGE ON SCHEMA reporting TO {role};GRANT SELECT ON ALL TABLES IN SCHEMA reporting TO {role}'))
    policy={'scope':'Your permitted orders','can':['Read permitted orders','Consult organisation documents'],'cannot':['Read another customer’s orders','Change source data'],'questions':['Show my orders'],'manual_pages':[]}
    manifest={'tenant_id':tenant,'name':'Verified business','adapter':'generic','view_schema':'reporting','source_schema':'business','policies':{r:policy for r in ['Admin','Faculty','Student']}}
    onboard(manifest,f'postgresql+psycopg2://{role}:test-only-long-password@127.0.0.1:55433/{database}')
    with engine().begin() as c:
        c.execute(text('INSERT INTO insight_app.accounts(tenant_id,user_id,username,password_hash,role_snapshot,name_snapshot) VALUES(:tenant,102,\'customer\',:hash,\'Student\',\'Verified Customer\')'),{'tenant':tenant,'hash':ph.hash('test-customer-password-123')})
    try:yield tenant,external
    finally:
        from product.storage import engine as cached_engine
        try:cached_engine('query',tenant).dispose()
        except Exception:pass
        with engine().begin() as c:
            c.execute(text('DELETE FROM insight_app.sessions WHERE account_id IN(SELECT id FROM insight_app.accounts WHERE tenant_id=:tenant)'),{'tenant':tenant})
            c.execute(text('DELETE FROM insight_app.password_resets WHERE account_id IN(SELECT id FROM insight_app.accounts WHERE tenant_id=:tenant)'),{'tenant':tenant})
            c.execute(text('DELETE FROM insight_app.audit_events WHERE tenant_id=:tenant'),{'tenant':tenant})
            c.execute(text('DELETE FROM insight_app.accounts WHERE tenant_id=:tenant'),{'tenant':tenant})
            c.execute(text('DELETE FROM insight_app.sources WHERE tenant_id=:tenant'),{'tenant':tenant})
        registry=ROOT/'.runtime/tenants.json';data=json.loads(registry.read_text());data.pop(tenant,None);registry.write_text(json.dumps(data));registry.chmod(0o600)
        external.dispose()
        with connection.cursor() as c:
            c.execute(sql.SQL('DROP DATABASE {} WITH(FORCE)').format(sql.Identifier(database)))
            c.execute(sql.SQL('DROP ROLE {}').format(sql.Identifier(role)))
        connection.close()

def test_generic_source_uses_own_database_and_identity(organisation):
    tenant,_=organisation
    user=Identity(0,tenant,102,'customer','Student','Verified Customer')
    assert set(catalog(tenant))=={'users','orders'}
    data=run_sql('SELECT order_id,amount FROM reporting.orders',user)['rows']
    assert data==[{'order_id':1,'amount':42}]
    assert run_sql('SELECT user_id FROM reporting.users',user)['rows']==[{'user_id':102}]
    with pytest.raises(ValueError):run_sql('SELECT student_name FROM insight.students',user)

def test_organisation_login_and_welcome_do_not_use_school_identity(organisation):
    tenant,_=organisation;limiter.clear()
    with TestClient(app) as client:
        assert client.post('/api/auth/login',json={'tenant_id':tenant,'username':'customer','password':'test-customer-password-123'}).status_code==200
        me=client.get('/api/auth/me').json();assert me['tenant_id']==tenant and me['name']=='Verified Customer'
        welcome=client.get('/api/chat/bootstrap').json();assert 'Verified business' in welcome['greeting'] and welcome['profile'] is None
        overview=client.get('/api/overview').json();assert overview['workspace']=='Verified business'
        assert client.get('/api/documents').json()==[]

def test_external_source_deactivation_revokes_access_immediately(organisation):
    tenant,external=organisation
    with TestClient(app) as client:
        client.post('/api/auth/login',json={'tenant_id':tenant,'username':'customer','password':'test-customer-password-123'}).raise_for_status()
        with external.begin() as c:c.execute(text('UPDATE business.directory SET is_active=false WHERE user_id=102'))
        try:assert client.get('/api/auth/me').status_code==401
        finally:
            with external.begin() as c:c.execute(text('UPDATE business.directory SET is_active=true WHERE user_id=102'))


def test_provision_uses_verified_source_role_and_single_use_setup(organisation):
    from product.accounts import provision,consume_reset
    from sqlalchemy import text
    tenant,external=organisation
    with external.begin() as c:
        c.execute(text("INSERT INTO business.directory VALUES(103,'new_faculty','New','Faculty','Faculty',true)"))
    with engine().begin() as c:
        account=c.execute(text("INSERT INTO insight_app.accounts(tenant_id,user_id,username,password_hash,role_snapshot,name_snapshot) VALUES(:tenant,101,'org_admin',:hash,'Admin','Organisation Admin') RETURNING id"),{'tenant':tenant,'hash':ph.hash('test-admin-password-123')}).scalar()
    user=Identity(account,tenant,101,'org_admin','Admin','Organisation Admin')
    result=provision(user,103)
    row=rows('SELECT username,role_snapshot FROM insight_app.accounts WHERE id=:id',{'id':result['account_id']})[0]
    assert row=={'username':'new_faculty','role_snapshot':'Faculty'}
    token=result['path'].split('token=')[1]
    consume_reset(token,'new-faculty-password-123')
    with TestClient(app) as client:
        client.post('/api/auth/login',json={'tenant_id':tenant,'username':'new_faculty','password':'new-faculty-password-123'}).raise_for_status()
        assert client.get('/api/auth/me').json()['role_name']=='Faculty'


def test_onboarding_refuses_login_with_raw_source_privileges(organisation):
    from sqlalchemy.engine import make_url
    from product.sources import query_url
    from scripts.onboard_source import onboard
    tenant,external=organisation
    url=query_url(tenant);role=make_url(url).username
    assert role.startswith('insight_verify_')
    with external.begin() as c:c.execute(text(f'GRANT SELECT ON business.orders TO {role}'))
    policy={'scope':'Permitted records','can':['Read records'],'cannot':['Write records'],'questions':['Show my orders']}
    manifest={'tenant_id':tenant,'name':'Rejected broad login','view_schema':'reporting','policies':{r:policy for r in ['Admin','Faculty','Student']}}
    try:
        with pytest.raises(ValueError,match='raw-table or write privileges'):onboard(manifest,url)
    finally:
        with external.begin() as c:c.execute(text(f'REVOKE SELECT ON business.orders FROM {role}'))
