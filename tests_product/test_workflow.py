import json,uuid
from unittest.mock import patch
from fastapi.testclient import TestClient
from product.api import app,limiter
from product.agent import Intent,SQLProposal,ManualAnswer,graph
from product.auth import attempts
from product.storage import rows
from tests_product.test_security import identity,sign_in

def parse_events(response):
    events=[]
    for chunk in response.text.split('\n\n'):
        lines=chunk.splitlines()
        kind=next((x[7:] for x in lines if x.startswith('event: ')),None)
        data=next((x[6:] for x in lines if x.startswith('data: ')),None)
        if data:events.append((kind,json.loads(data)))
    return events

def test_graph_executes_validated_sql_and_sends_stream():
    limiter.clear();attempts.clear()
    with TestClient(app) as client:
        sign_in(client,'admin01')
        responses=[Intent(kind='sql',question='Count students',documentation_question='',answer=''),SQLProposal(sql='SELECT COUNT(*) AS total FROM insight.students')]
        with patch('product.agent.structured',side_effect=responses):
            response=client.post('/api/chat/stream',json={'question':'How many students are there?','provider':'openai'})
        events=parse_events(response)
        result=next(value for kind,value in events if kind=='result')
        assert result['report']['rows']==[{'total':4}]
        assert '4' in result['answer'] and result['source']=='SQL'
        assert any(kind=='report' for kind,value in events)
        assert any(kind=='stage' and value['node']=='sql_validation' for kind,value in events)
        assert client.get('/api/history').json()
        conversation=result['conversation_id']
        client.post('/api/feedback',json={'message_id':result['message_id'],'rating':1}).raise_for_status()
        client.post('/api/auth/logout')
        sign_in(client,'stu_arjun')
        assert client.get('/api/conversations/'+conversation).status_code==404
        assert client.post('/api/feedback',json={'message_id':result['message_id'],'rating':-1}).status_code==404

def test_repair_is_bounded_to_one_retry():
    proposals=[Intent(kind='sql',question='Count',documentation_question='',answer=''),SQLProposal(sql='SELECT password_hash FROM school.users'),SQLProposal(sql='SELECT password_hash FROM school.users')]
    with patch('product.agent.structured',side_effect=proposals) as model:
        try:
            graph.invoke({'question':'Count users','identity':identity('admin01'),'provider':'openai','model':'test','history':[]})
        except ValueError:pass
        else:raise AssertionError('Unsafe SQL should not finish')
        assert model.call_count==3

def test_rag_cannot_return_fabricated_citation():
    from product.agent import document_answer
    evidence=[{'id':str(uuid.uuid4()),'document_id':str(uuid.uuid4()),'name':'Manual.pdf','page':10,'section':'6.5 Leave approvals','content':'Requests are pending until reviewed.'}]
    with patch('product.agent.structured',return_value=ManualAnswer(answer='Unsupported text',citation_ids=['invented'])):
        result=document_answer({'identity':identity('admin01'),'evidence':evidence,'provider':'openai','model':'test','intent':{'documentation_question':'Leave approvals'},'question':'Leave'})
    assert result['documentation']['citations']==[]
    assert 'verifiable' in result['documentation']['answer']
