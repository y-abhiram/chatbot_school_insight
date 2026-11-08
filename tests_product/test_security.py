import json,pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from product.api import app,limiter
from product.auth import Identity,attempts
from product.storage import rows,engine
from product.sql_engine import validate_sql,run_sql,UnsafeSQL
from product.config import ROOT

@pytest.fixture(autouse=True)
def limits():limiter.clear();attempts.clear()
@pytest.fixture
def client():return TestClient(app)
def identity(username):
    data=rows('SELECT * FROM insight_app.identities WHERE username=:u',{'u':username})[0]
    return Identity(**{k:data[k] for k in Identity.__dataclass_fields__})
def sign_in(client,username):
    accounts=json.loads((ROOT/'.runtime/demo-accounts.json').read_text())
    account=next(a for a in accounts if a['username']==username)
    response=client.post('/api/auth/login',json={'username':username,'password':account['password']})
    assert response.status_code==200
    assert 'httponly' in response.headers['set-cookie'].lower()
    return client
@pytest.mark.parametrize('query',[
 'DELETE FROM insight.students','SELECT 1; DROP SCHEMA school CASCADE',
 'SELECT password_hash FROM school.users','SELECT * FROM pg_catalog.pg_authid',
 'SELECT password_hash FROM insight.users',"SELECT pg_read_file('/etc/passwd') FROM insight.students",
 "SELECT set_config('insight.role','Admin',true) FROM insight.students",
 'SELECT pg_sleep(20) FROM insight.students',
 'SELECT * INTO stolen FROM insight.students','SELECT * FROM insight.students FOR UPDATE',
 "WITH stolen AS (DELETE FROM insight.students RETURNING *) SELECT * FROM stolen",
 'SELECT * FROM insight.students UNION SELECT * FROM school.users',
 "SELECT 'insight.users'::regclass FROM insight.students",
 'SELECT * FROM insight_app.accounts','SELECT * FROM reporting.students',
 'SELECT * FROM insight.students LIMIT -1','SELECT * FROM insight.students OFFSET 1',
])
def test_unsafe_queries_are_rejected(query):
    with pytest.raises(UnsafeSQL):validate_sql(query)

def test_raw_reader_credentials_cannot_read_school_or_write():
    with engine('query').connect() as conn:
        with pytest.raises(DBAPIError):conn.execute(text('SELECT password_hash FROM school.users'))
    with engine('query').connect() as conn:
        with pytest.raises(DBAPIError):conn.execute(text('CREATE TABLE insight.illegal(id int)'))

def test_student_scope_and_injection():
    user=identity('stu_arjun')
    assert run_sql('SELECT student_name FROM insight.students',user)['rows']==[{'student_name':'Arjun Rao'}]
    assert run_sql("SELECT student_name FROM insight.students WHERE student_name ILIKE 'Kiran%' OR 1=1",user)['rows']==[{'student_name':'Arjun Rao'}]
    assert run_sql("SELECT student_name FROM insight.students WHERE student_name ILIKE 'Kiran%'",user)['rows']==[]
    assert run_sql('SELECT * FROM insight.v_exam_report',user)['rows']==[]
    assert run_sql('SELECT * FROM insight.users',user)['rows'][0]['username']=='stu_arjun'

def test_faculty_scope_is_subject_specific():
    data=run_sql('SELECT subject_name,student_name FROM insight.v_exam_report',identity('fac_anita'))['rows']
    assert len(data)==2 and {r['subject_name'] for r in data}=={'Mathematics'}
    assert run_sql('SELECT * FROM insight.v_pending_leaves',identity('fac_anita'))['rows']==[]
    assert run_sql('SELECT * FROM insight.progress_reports',identity('fac_anita'))['rows']==[]

def test_tenant_scope_and_transaction_reuse():
    from dataclasses import replace
    arjun=identity('stu_arjun');admin=identity('admin01')
    assert len(run_sql('SELECT * FROM insight.students',admin)['rows'])==4
    assert len(run_sql('SELECT * FROM insight.students',arjun)['rows'])==1
    with pytest.raises(ValueError,match='not configured'):
        run_sql('SELECT * FROM insight.students',replace(admin,tenant_id='another-school'))
    with engine('query').connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM insight.students')).scalar()==0

def test_limit_preserved_and_bounded():
    user=identity('admin01')
    result=run_sql('SELECT student_name FROM insight.students LIMIT 2',user)
    assert len(result['rows'])==2 and result['truncated']
    sql,limit=validate_sql('SELECT student_name FROM insight.students LIMIT 999999')
    assert limit==200 and '201' in sql

def test_no_unauthenticated_data(client):
    for endpoint in ['/overview','sources','schema','documents','history','team','conversations','analytics','settings']:
        path=endpoint if endpoint.startswith('/') else '/'+endpoint
        assert client.get('/api'+path).status_code==401

def test_authenticated_role_cannot_be_spoofed(client):
    sign_in(client,'stu_arjun')
    assert client.get('/api/auth/me').json()['role_name']=='Student'
    assert client.get('/api/team').status_code==403
    assert client.get('/api/overview').json()['counts']['students']==1
    assert client.post('/api/chat/stream',json={'question':'show students','role':'Admin'}).status_code==422
    assert client.post('/api/documents',files={'file':('bad.pdf',b'%PDF-bad','application/pdf')}).status_code==403

def test_cross_origin_logout_and_bad_credentials(client):
    sign_in(client,'admin01')
    assert client.post('/api/auth/logout',headers={'Origin':'https://evil.example'}).status_code==403
    assert client.post('/api/auth/logout').status_code==200
    assert client.get('/api/auth/me').status_code==401
    assert client.post('/api/auth/login',json={'username':'admin01','password':'wrong'}).status_code==401

def test_password_hashes_not_returned_in_team(client):
    sign_in(client,'admin01')
    response=client.get('/api/team')
    assert response.status_code==200 and len(response.json())==8
    assert 'password' not in response.text

def test_actual_schema_catalogue(client):
    sign_in(client,'admin01')
    doc=client.get('/api/schema').json()
    assert len(doc['tables'])==29 and len(doc['views'])==4
    assert doc['verified_counts']=={'users':8,'students':4,'faculty':3,'timetable':8,'marks':6,'pending_leaves':1}
    assert doc['tables']['students']['foreign_keys']
    assert doc['tables']['timetable']['unique_constraints']
