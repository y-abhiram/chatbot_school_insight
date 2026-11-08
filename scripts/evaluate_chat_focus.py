"""Live conversational checks against the real sample data; never print login/API secrets."""
import json,time
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
accounts=json.loads((ROOT/'.runtime/demo-accounts.json').read_text())
checks=[]
def ask(client,question,conversation=None):
    started=time.monotonic()
    response=client.post('/api/chat/stream',json={'question':question,'provider':'openai','conversation_id':conversation})
    response.raise_for_status()
    final=None
    for packet in response.text.split('\n\n'):
        if packet.startswith('event: result'):
            final=json.loads(packet.split('data: ',1)[1])
        elif packet.startswith('event: error'):raise RuntimeError(json.loads(packet.split('data: ',1)[1])['detail'])
    if final is None:raise RuntimeError('No final response received.')
    print(question,'->',final['kind'],round(time.monotonic()-started,1),'s',flush=True)
    return final

def verify(value,label,response=None):
    checks.append({'check':label,'passed':bool(value),'kind':response.get('kind') if response else None,'answer':response.get('answer') if response else None})
    print(('PASS: ' if value else 'FAIL: ')+label,flush=True)
    if not value:raise AssertionError(label)
with httpx.Client(base_url='http://127.0.0.1:8100',timeout=150,trust_env=False) as client:
    a=next(x for x in accounts if x['username']=='stu_divya')
    client.post('/api/auth/login',json={'username':a['username'],'password':a['password']}).raise_for_status()
    welcome=client.get('/api/chat/bootstrap').json()
    verify('Divya' in welcome['greeting'] and welcome['profile']['class_name']=='Grade 10','Login-aware greeting uses verified Divya / Grade 10 profile')
    result=ask(client,'What is my attendance percentage?')
    verify(result['kind']=='sql' and '100%' in result['answer'],'Natural-language attendance returns actual 100%',result)
    conversation=result['conversation_id']
    result=ask(client,'Summarize that',conversation)
    verify(result['kind']=='summary' and '100%' in result['answer'] and result['report'] is None,'Summary uses previous verified result and runs no new report',result)
    result=ask(client,"Show Kiran's marks",conversation)
    verify(result['report'] is None and 'can’t show another student' in result['answer'],'Student cross-record request is refused',result)
    result=ask(client,'Show my marks',conversation)
    values={float(r['marks_obtained']) for r in (result.get('report') or {}).get('rows',[]) if r.get('marks_obtained') is not None}
    verify(values=={95,91,89},'My marks resolves to Divya: 95, 91, 89',result)
    result=ask(client,'How do I apply for leave?',conversation)
    doc=result.get('documentation') or {}
    verify(result['kind']=='rag' and bool(doc.get('citations')),'Manual-based student leave answer includes verified page citations',result)
    result=ask(client,'I want')
    verify(result['kind']=='clarification' and bool(result['answer']),'Incomplete request receives a natural clarification',result)
    client.post('/api/auth/logout')
    a=next(x for x in accounts if x['username']=='stu_arjun')
    client.post('/api/auth/login',json={'username':a['username'],'password':a['password']}).raise_for_status()
    result=ask(client,'Show my marks')
    verify(result['report']['rows']==[] and 'not been recorded' in result['answer'],'Arjun missing marks are not presented as zero or fail',result)
(ROOT/'.runtime/chat-focused-evaluation.json').write_text(json.dumps({'checks':checks,'passed':len(checks)},indent=2))
print('Live checks passed:',len(checks),flush=True)
