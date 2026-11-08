import json,uuid,pytest
from unittest.mock import patch
from types import SimpleNamespace
from fastapi.testclient import TestClient
from sqlalchemy import text
from product.api import app,limiter
from product.storage import engine,rows,execute
from product.auth import ph,attempts
from product.agent import Intent,ManualAnswer,graph
from product.llm import structured
from product.accounts import issue_reset,consume_reset
from tests_product.test_security import identity,sign_in
from tests_product.test_workflow import parse_events

@pytest.fixture(autouse=True)
def limits():limiter.clear();attempts.clear()

@pytest.fixture
def temporary_account():
    username='verify_'+uuid.uuid4().hex[:10]
    with engine().begin() as c:
        id=c.execute(text('INSERT INTO insight_app.accounts(tenant_id,user_id,username,password_hash) VALUES(\'school-demo\',1,:username,:hash) RETURNING id'),{'username':username,'hash':ph.hash('temporary-password-123')}).scalar()
    try:yield id,username
    finally:
        with engine().begin() as c:
            c.execute(text('DELETE FROM insight_app.password_resets WHERE account_id=:id'),{'id':id})
            c.execute(text('DELETE FROM insight_app.sessions WHERE account_id=:id'),{'id':id})
            c.execute(text('DELETE FROM insight_app.accounts WHERE id=:id'),{'id':id})

def test_reset_link_is_hashed_single_use_and_revokes_sessions(temporary_account):
    id,username=temporary_account
    with TestClient(app) as client:
        client.post('/api/auth/login',json={'username':username,'password':'temporary-password-123'}).raise_for_status()
        link=issue_reset(identity('admin01'),id)
        token=link['path'].split('token=',1)[1]
        assert not rows('SELECT token_hash FROM insight_app.password_resets WHERE token_hash=:raw',{'raw':token})
        assert client.get('/api/auth/me').status_code==200
        result=client.post('/api/auth/reset-password',json={'token':token,'password':'new-test-password-456'})
        assert result.status_code==200
        assert client.get('/api/auth/me').status_code==401
        assert client.post('/api/auth/reset-password',json={'token':token,'password':'another-password-789'}).status_code==400
        assert client.post('/api/auth/login',json={'username':username,'password':'new-test-password-456'}).status_code==200

def test_student_cannot_issue_reset_or_provision():
    with TestClient(app) as client:
        sign_in(client,'stu_arjun')
        assert client.post('/api/team/1/reset').status_code==403
        assert client.post('/api/team/provision',json={'source_user_id':1}).status_code==403

def test_expired_reset_is_rejected(temporary_account):
    id,_=temporary_account;link=issue_reset(identity('admin01'),id);token=link['path'].split('token=',1)[1]
    execute("UPDATE insight_app.password_resets SET expires_at=now()-interval '1 minute' WHERE account_id=:id",{'id':id})
    with TestClient(app) as client:assert client.post('/api/auth/reset-password',json={'token':token,'password':'long-enough-password'}).status_code==400

def test_change_password_requires_old_password_and_revokes_session(temporary_account):
    _,username=temporary_account
    with TestClient(app) as client:
        client.post('/api/auth/login',json={'username':username,'password':'temporary-password-123'}).raise_for_status()
        assert client.post('/api/auth/change-password',json={'current_password':'wrong','new_password':'new-test-password-456'}).status_code==400
        assert client.post('/api/auth/change-password',json={'current_password':'temporary-password-123','new_password':'new-test-password-456'}).status_code==200
        assert client.get('/api/auth/me').status_code==401

def test_json_stream_uses_provider_partial_objects_before_completion(monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','test-key');events=[]
    def chunks(*args,**kwargs):
        yield {'kind':'answer','question':'hello','documentation_question':'','answer':'Hel'}
        assert events==['Hel']
        yield {'kind':'answer','question':'hello','documentation_question':'','answer':'Hello'}
    with patch('product.llm.ChatOpenAI') as factory:
        runnable=factory.return_value.with_structured_output.return_value;runnable.stream.side_effect=chunks
        response=structured('openai','test-model',Intent,'Be helpful','hello',on_delta=events.append)
    assert events==['Hel','lo'] and response.answer=='Hello'
    runnable.invoke.assert_not_called()

def test_http_stream_forwards_real_graph_custom_deltas():
    async def fake_stream(state,stream_mode):
        assert stream_mode==['updates','custom']
        yield 'updates',{'authentication':{}}
        yield 'custom',{'event':'answer_delta','target':'answer','text':'Hello '}
        yield 'custom',{'event':'answer_delta','target':'answer','text':'there'}
        yield 'updates',{'response_generation':{'response':{'kind':'answer','answer':'Hello there','report':None,'documentation':None,'provider':'openai','model':'test','duration_ms':5,'access_scope':'Student','source':'ASSISTANT'}}}
    with TestClient(app) as client:
        sign_in(client,'stu_arjun')
        with patch('product.api.graph.astream',side_effect=fake_stream):response=client.post('/api/chat/stream',json={'question':'hello','provider':'openai'})
    events=parse_events(response)
    assert [data['text'] for kind,data in events if kind=='answer_delta']==['Hello ','there']
    assert events[-1][0]=='result'

def test_no_oversized_body_reaches_chat():
    with TestClient(app) as client:assert client.post('/api/chat/stream',content=b'x'*20001,headers={'Content-Type':'application/json'}).status_code==413

def test_operational_metrics_and_audit_are_admin_only():
    with TestClient(app) as client:
        sign_in(client,'stu_arjun');assert client.get('/api/operations').status_code==403
        client.post('/api/auth/logout');sign_in(client,'admin01')
        response=client.get('/api/operations');assert response.status_code==200
        assert 'password_hash' not in response.text and 'token_hash' not in response.text
