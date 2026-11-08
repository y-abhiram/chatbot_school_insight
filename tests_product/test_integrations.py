import uuid
from unittest.mock import Mock
from types import SimpleNamespace
import pytest
from product.errors import assistant_error
from product.langsmith_eval import publish
from product.evaluation import verify

def test_provider_error_never_echoes_secret_or_account_details():
    error=type('APIError',(Exception,),{})('Rate limit reached for private-account with key secret-value')
    message=assistant_error(error)
    assert 'usage limit' in message and 'secret-value' not in message and 'private-account' not in message
    assert 'secret-value' not in assistant_error(RuntimeError('secret-value'))

def test_langsmith_publication_links_examples_runs_and_feedback():
    client=Mock();client.create_dataset.return_value=SimpleNamespace(id=uuid.uuid4())
    report={'run_id':str(uuid.uuid4()),'provider':'openai','model':'test','cases':[{'id':1,'question':'Count students','expected':[{'total':4}],'checks':{'intent':True,'sql_result':True},'passed':True,'response':{'answer':'4'}}]}
    result=publish(report,client)
    example=client.create_examples.call_args.kwargs['examples'][0]
    run=client.create_run.call_args.kwargs
    assert str(run['reference_example_id'])==str(example['id'])
    assert client.update_run.call_args.kwargs['outputs']=={'answer':'4'}
    assert client.create_feedback.call_count==3 and result['cases']==1

def test_langsmith_requires_explicit_configured_key(monkeypatch):
    monkeypatch.delenv('LANGSMITH_API_KEY',raising=False)
    with pytest.raises(ValueError):publish({'run_id':'unused'})


def test_https_login_uses_secure_cookie_and_hsts(monkeypatch):
    from fastapi.testclient import TestClient
    from product.api import app
    from tests_product.test_security import sign_in
    monkeypatch.setenv('COOKIE_SECURE','true')
    with TestClient(app,base_url='https://testserver') as client:
        sign_in(client,'admin01')
        cookie=client.cookies.jar._cookies['testserver.local']['/']['insight_session']
        assert cookie.secure and 'HttpOnly' in cookie._rest and cookie._rest.get('SameSite')=='strict'
        response=client.get('/api/auth/me')
        assert response.status_code==200 and 'max-age=' in response.headers['strict-transport-security']
