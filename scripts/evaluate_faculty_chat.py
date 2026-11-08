"""Live regression for the faculty requests shown in the UI screenshot."""
import json,time
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]
account=next(a for a in json.loads((ROOT/'.runtime/demo-accounts.json').read_text()) if a['username']=='fac_vijay')
checks=[]
def verify(condition,name,result=None):
    checks.append({'check':name,'passed':bool(condition),'kind':result.get('kind') if result else None,'answer':result.get('answer') if result else None})
    print(('PASS: ' if condition else 'FAIL: ')+name,flush=True)
    if not condition:raise AssertionError(name)
def ask(client,q,conversation=None):
    started=time.monotonic()
    response=client.post('/api/chat/stream',json={'question':q,'provider':'openai','conversation_id':conversation});response.raise_for_status()
    for packet in response.text.split('\n\n'):
        if packet.startswith('event: result'):
            result=json.loads(packet.split('data: ',1)[1]);print(q,'->',result['kind'],round(time.monotonic()-started,1),'s',flush=True)
            verify(bool(result['answer'].strip()),'Nonempty reply: '+q,result)
            return result
        if packet.startswith('event: error'):raise RuntimeError(json.loads(packet.split('data: ',1)[1])['detail'])
    raise RuntimeError('No final response.')
with httpx.Client(base_url='http://127.0.0.1:8100',timeout=140,trust_env=False) as client:
    client.post('/api/auth/login',json={'username':account['username'],'password':account['password']}).raise_for_status()
    boot=client.get('/api/chat/bootstrap').json()
    verify('List students in my assigned sections' in boot['suggestions'],'Faculty onboarding offers the permitted student roster')
    result=ask(client,'List students in my assigned sections')
    rows=(result.get('report') or {}).get('rows',[])
    verify({r['student_name'] for r in rows}=={'Arjun Rao','Meera Iyer','Kiran Patel','Divya Nair'},'Roster matches Vijay’s two assigned sections',result)
    conversation=result['conversation_id']
    result=ask(client,'attendence of all students',conversation)
    rows=(result.get('report') or {}).get('rows',[])
    verify(bool(rows) and {r['student_name'] for r in rows}=={'Arjun Rao','Meera Iyer'},'Misspelled attendance request returns only recorded Science attendance',result)
    verify('assigned subjects' in result['answer'],'Faculty report clearly labels the access scope',result)
    result=ask(client,'Show students marks for my subjects',conversation)
    rows=(result.get('report') or {}).get('rows',[])
    verify({(r['student_name'],float(r['marks_obtained'])) for r in rows}=={('Kiran Patel',76),('Divya Nair',91)},'Science marks match actual assigned-subject results',result)
    result=ask(client,'leaves and students marks',conversation)
    verify(result['kind']=='clarification' and 'own leave requests' in result['answer'],'Mixed leave/marks request asks a useful scoped follow-up',result)
    result=ask(client,'Show all students leave requests',conversation)
    verify(result['report'] is None and 'administrator' in result['answer'],'Faculty is not granted student leave review',result)
(ROOT/'.runtime/faculty-chat-evaluation.json').write_text(json.dumps({'checks':checks,'passed':len(checks),'conversation_id':conversation},indent=2))
print('Passed checks:',len(checks),flush=True)
