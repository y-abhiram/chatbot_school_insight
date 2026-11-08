import asyncio,hashlib,json,os,time,uuid
from pathlib import Path
from collections import defaultdict,deque
from threading import Lock
from fastapi import FastAPI,Request,HTTPException,Depends,UploadFile,File
from fastapi.responses import JSONResponse,StreamingResponse,FileResponse
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel,Field,ConfigDict
from sqlalchemy import text
from product.config import ROOT,TENANT,settings
from product.storage import engine,rows,execute
from product.auth import current,login,logout,public,admin,Identity,ph
from product.sql_engine import catalog,run_sql,UnsafeSQL
from product.llm import select_provider,provider_status
from product.agent import graph
from product.cache import client as redis_client
from product.jobs import ingest_pdf
from product.policy import welcome
from product.sources import source_for
from product import accounts
from product.errors import assistant_error
from product.observability import record,metrics,audit
app=FastAPI(title='School Insight API',version='2.0.0',docs_url='/api/docs',openapi_url='/api/openapi.json',redoc_url=None)
limiter=defaultdict(deque);limit_lock=Lock()
class Strict(BaseModel):model_config=ConfigDict(extra='forbid')
class Credentials(Strict):
    username:str=Field(min_length=1,max_length=60)
    password:str=Field(min_length=1,max_length=200)
    tenant_id:str=Field(default=TENANT,min_length=2,max_length=63)
class Ask(Strict):
    question:str=Field(min_length=1,max_length=2000)
    conversation_id:uuid.UUID|None=None
    provider:str='auto'
    model:str=Field(default='',max_length=120)
class Feedback(Strict):message_id:uuid.UUID;rating:int=Field(ge=-1,le=1)
class AccountUpdate(Strict):active:bool
class ResetPassword(Strict):token:str=Field(min_length=20,max_length=120);password:str=Field(min_length=12,max_length=200)
class ChangePassword(Strict):current_password:str=Field(min_length=1,max_length=200);new_password:str=Field(min_length=12,max_length=200)
class ProvisionAccount(Strict):source_user_id:int=Field(gt=0)


@app.middleware('http')
async def headers(request,call_next):
    started=time.monotonic();request_id=str(uuid.uuid4())
    if request.method in ('POST','PATCH','PUT'):
        limit=16*1024*1024 if request.url.path=='/api/documents' else 20000
        try:declared=int(request.headers.get('content-length','0'))
        except ValueError:return JSONResponse({'detail':'Invalid request length.'},status_code=400)
        if declared<0 or declared>limit:return JSONResponse({'detail':'Request is too large.'},status_code=413)
        data=bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data)>limit:return JSONResponse({'detail':'Request is too large.'},status_code=413)
        request._body=bytes(data)
    if request.method in ('POST','PUT','PATCH','DELETE'):
        origin=request.headers.get('origin')
        allowed=os.getenv('PRODUCT_WEB_ORIGINS','http://127.0.0.1:3000,http://localhost:3000').split(',')
        if origin and origin not in allowed:return JSONResponse({'detail':'Untrusted request origin.'},status_code=403)
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff';response.headers['Cache-Control']='no-store';response.headers['Referrer-Policy']='same-origin'
    response.headers['X-Request-ID']=request_id
    if os.getenv('COOKIE_SECURE','false')=='true':response.headers['Strict-Transport-Security']='max-age=31536000'
    record('http_request',request_id=request_id,route=request.scope.get('route').path if request.scope.get('route') else 'unknown',status=response.status_code,duration_ms=round((time.monotonic()-started)*1000))
    return response

@app.get('/api/health')
def health():
    try:
        db=rows('SELECT 1 AS ok')[0]['ok']==1
        redis=redis_client().ping()
        return {'database':db,'redis':redis,'version':'2.0.0'}
    except Exception:return JSONResponse({'database':False,'redis':False,'version':'2.0.0'},status_code=503)
@app.post('/api/auth/login')
def sign_in(body:Credentials,request:Request):
    token=login(body.username.strip(),body.password,request.client.host if request.client else 'local',body.tenant_id)
    response=JSONResponse({'ok':True})
    response.set_cookie('insight_session',token,httponly=True,samesite='strict',secure=os.getenv('COOKIE_SECURE','false')=='true',max_age=28800,path='/')
    return response
@app.post('/api/auth/logout')
def sign_out(request:Request,user=Depends(current)):
    logout(request.cookies.get('insight_session',''));response=JSONResponse({'ok':True});response.delete_cookie('insight_session',path='/');return response
@app.post('/api/auth/reset-password')
def reset_password(body:ResetPassword,request:Request):
    # Shared Redis limit bounds online guessing; token hashes are random 320-bit values.
    key='insight:reset-attempt:'+hashlib.sha256((request.client.host if request.client else 'local').encode()).hexdigest()
    try:
        count=redis_client().incr(key)
        if count==1:redis_client().expire(key,600)
        if count>20:raise HTTPException(429,'Too many recovery attempts. Try again later.')
    except HTTPException:raise
    except Exception:raise HTTPException(503,'Recovery is temporarily unavailable.')
    return accounts.consume_reset(body.token,body.password)
@app.post('/api/auth/change-password')
def change_password(body:ChangePassword,user=Depends(current)):
    result=accounts.change_password(user,body.current_password,body.new_password)
    response=JSONResponse(result);response.delete_cookie('insight_session',path='/');return response
@app.get('/api/operations')
def operations(user=Depends(current)):
    admin(user)
    return {'metrics':metrics(),'recent_events':rows('SELECT event,created_at,detail FROM insight_app.audit_events WHERE tenant_id=:tenant ORDER BY created_at DESC LIMIT 30',{'tenant':user.tenant_id})}
@app.get('/api/team/source-users')
def provisionable_users(user=Depends(current)):return accounts.source_users(user)
@app.post('/api/team/provision')
def provision_account(body:ProvisionAccount,user=Depends(current)):return accounts.provision(user,body.source_user_id)
@app.post('/api/team/{account_id}/reset')
def reset_link(account_id:int,user=Depends(current)):return accounts.issue_reset(user,account_id)
@app.get('/api/auth/me')
def me(user=Depends(current)):return public(user)
@app.get('/api/chat/bootstrap')
def bootstrap_chat(user=Depends(current)):
    return welcome(user)

@app.get('/api/settings')
def configuration(user=Depends(current)):
    try:p,m=select_provider()
    except Exception:p,m='guided',''
    return {'providers':provider_status(),'default_provider':p,'default_model':m,'read_only':True,'tenant':user.tenant_id,'embedding':'all-MiniLM-L6-v2 (local)','reranker':'ms-marco-MiniLM-L6-v2 (local)','tracing':os.getenv('LANGSMITH_TRACING','false')=='true'}

@app.get('/api/overview')
def overview(user=Depends(current)):
    def report(sql):return run_sql(sql,user,use_cache=False)['rows']
    source=source_for(user.tenant_id)
    if source['adapter']!='school':
        views=catalog(user.tenant_id)
        metrics=[]
        for name in list(views)[:4]:
            if name=='users' and user.role_name!='Admin':continue
            result=run_sql(f"SELECT COUNT(*) AS total FROM {source['view_schema']}.{name}",user,use_cache=False)
            metrics.append({'label':name.replace('_',' ').title(),'value':result['rows'][0]['total']})
        return {'metrics':metrics,'counts':{},'attendance':[],'marks':[],'scope':'Permitted organisation records','workspace':source['name']}
    counts={}
    for name in ['students','faculty','homework','v_pending_leaves']:
        counts[name]=report(f'SELECT COUNT(*) AS total FROM insight.{name}')[0]['total']
    attendance=report('SELECT student_name,class_name,attendance_pct,total_periods,attended FROM insight.v_student_attendance_report ORDER BY attendance_pct ASC')
    marks=report('SELECT subject_name,ROUND(AVG(marks_obtained),2) AS average_marks FROM insight.v_exam_report GROUP BY subject_name ORDER BY subject_name')
    total=sum(int(r['total_periods']) for r in attendance);attended=sum(int(r['attended']) for r in attendance)
    return jsonable_encoder({'counts':counts,'attendance':attendance,'marks':marks,'attendance_pct':round(100*attended/total,2) if total else None,'role':user.role_name,'scope':'Your own records' if user.role_name=='Student' else 'Assigned subjects and sections' if user.role_name=='Faculty' else 'School-wide records'})
@app.get('/api/sources')
def sources(user=Depends(current)):
    source=source_for(user.tenant_id);data=source.get('catalog') or {}
    return {'name':source['name'],'schema':source['source_schema'],'tables':len(data.get('tables',{})),'views':len(data.get('views',{})),'engine':'PostgreSQL + pgvector','access':'Read-only, identity-scoped views','verified_counts':data.get('verified_counts') if user.role_name=='Admin' else None,'reporting_views':list(catalog(user.tenant_id))}
@app.get('/api/schema')
def schema(user=Depends(current)):
    source=source_for(user.tenant_id)
    if user.role_name=='Admin':return source.get('catalog') or {'schema':source['view_schema'],'reporting_views':catalog(user.tenant_id)}
    return {'schema':source['view_schema'],'reporting_views':catalog(user.tenant_id),'note':'Queries are restricted to your authenticated identity.'}
@app.get('/api/documents')
def documents(user=Depends(current)):
    return rows('SELECT d.id,d.name,d.pages,d.status,d.error,d.created_at,(SELECT COUNT(*) FROM insight_app.chunks c WHERE c.document_id=d.id AND c.tenant_id=:tenant) AS chunks FROM insight_app.documents d WHERE d.tenant_id=:tenant ORDER BY d.created_at DESC',{'tenant':user.tenant_id})
@app.post('/api/documents')
async def upload(file:UploadFile=File(...),user=Depends(current)):
    admin(user)
    if file.content_type!='application/pdf':raise HTTPException(415,'Upload a PDF document.')
    data=bytearray()
    while chunk:=await file.read(65536):
        data.extend(chunk)
        if len(data)>15*1024*1024:raise HTTPException(413,'PDF limit is 15 MB.')
    if not data.startswith(b'%PDF-'):raise HTTPException(422,'The file is not a PDF.')
    digest=hashlib.sha256(data).hexdigest()
    existing=rows('SELECT id,status FROM insight_app.documents WHERE tenant_id=:tenant AND sha256=:hash',{'tenant':user.tenant_id,'hash':digest})
    if existing:return {'id':existing[0]['id'],'status':existing[0]['status'],'duplicate':True}
    id=str(uuid.uuid4());name=Path(file.filename or 'Document.pdf').name[:180]
    folder=ROOT/'.runtime/uploads';folder.mkdir(exist_ok=True);path=folder/f'{id}.pdf';path.write_bytes(data);path.chmod(0o600)
    execute('INSERT INTO insight_app.documents(id,tenant_id,name,sha256) VALUES(:id,:tenant,:name,:hash)',{'id':id,'tenant':user.tenant_id,'name':name,'hash':digest})
    try:ingest_pdf.delay(id,user.tenant_id)
    except Exception:
        execute("UPDATE insight_app.documents SET status='failed',error='Job queue unavailable. Retry when the worker is running.' WHERE id=:id",{'id':id})
        raise HTTPException(503,'The ingestion worker is unavailable.')
    return {'id':id,'status':'pending'}
@app.post('/api/documents/{document_id}/retry')
def retry_document(document_id:uuid.UUID,user=Depends(current)):
    admin(user)
    doc=rows('SELECT status FROM insight_app.documents WHERE id=:id AND tenant_id=:tenant',{'id':str(document_id),'tenant':user.tenant_id})
    if not doc:raise HTTPException(404,'Document not found.')
    if doc[0]['status']!='failed':raise HTTPException(409,'Only failed documents can be retried.')
    execute("UPDATE insight_app.documents SET status='pending',error=NULL WHERE id=:id",{'id':str(document_id)})
    ingest_pdf.delay(str(document_id),user.tenant_id);return {'status':'pending'}
@app.get('/api/documents/{document_id}/file')
def document_file(document_id:uuid.UUID,user=Depends(current)):
    if not rows('SELECT id FROM insight_app.documents WHERE id=:id AND tenant_id=:tenant',{'id':str(document_id),'tenant':user.tenant_id}):raise HTTPException(404,'Document not found.')
    return FileResponse(ROOT/'.runtime/uploads'/f'{document_id}.pdf',media_type='application/pdf')

@app.get('/api/conversations')
def conversations(user=Depends(current)):
    return rows('SELECT id,title,provider,model,created_at FROM insight_app.conversations WHERE account_id=:account AND tenant_id=:tenant ORDER BY created_at DESC LIMIT 100',{'account':user.id,'tenant':user.tenant_id})
def owned_conversation(id,user):
    found=rows('SELECT * FROM insight_app.conversations WHERE id=:id AND account_id=:account AND tenant_id=:tenant',{'id':str(id),'account':user.id,'tenant':user.tenant_id})
    if not found:raise HTTPException(404,'Conversation not found.')
    return found[0]
@app.get('/api/conversations/{conversation_id}')
def messages(conversation_id:uuid.UUID,user=Depends(current)):
    owned_conversation(conversation_id,user)
    return rows('SELECT id,role,content,payload,created_at FROM insight_app.messages WHERE conversation_id=:id ORDER BY created_at,id',{'id':str(conversation_id)})
@app.delete('/api/conversations/{conversation_id}')
def delete_conversation(conversation_id:uuid.UUID,user=Depends(current)):
    owned_conversation(conversation_id,user)
    execute('DELETE FROM insight_app.conversations WHERE id=:id',{'id':str(conversation_id)});return {'deleted':True}
@app.get('/api/history')
def history(user=Depends(current)):
    return rows('SELECT id,question,sql_text,row_count,duration_ms,status,created_at FROM insight_app.queries WHERE account_id=:account AND tenant_id=:tenant ORDER BY created_at DESC LIMIT 100',{'account':user.id,'tenant':user.tenant_id})
@app.get('/api/analytics')
def analytics(user=Depends(current)):
    return rows('SELECT status,COUNT(*) AS queries,ROUND(AVG(duration_ms)) AS average_ms,SUM(row_count) AS rows_returned FROM insight_app.queries WHERE account_id=:account AND tenant_id=:tenant GROUP BY status',{'account':user.id,'tenant':user.tenant_id})
@app.get('/api/team')
def team(user=Depends(current)):
    admin(user)
    return rows('SELECT id,username,name,role_name,active FROM insight_app.identities WHERE tenant_id=:tenant ORDER BY id',{'tenant':user.tenant_id})
@app.patch('/api/team/{account_id}')
def update_team(account_id:int,body:AccountUpdate,user=Depends(current)):
    admin(user)
    if account_id==user.id:raise HTTPException(409,'You cannot deactivate your own account.')
    execute('UPDATE insight_app.accounts SET active=:active WHERE id=:id AND tenant_id=:tenant',{'id':account_id,'tenant':user.tenant_id,'active':body.active})
    audit(user,'account_access_changed',{'target_account':account_id,'active':body.active})
    return {'updated':True}
@app.post('/api/feedback')
def feedback(body:Feedback,user=Depends(current)):
    if body.rating not in (-1,1):raise HTTPException(422,'Rating must be -1 or 1.')
    found=rows('SELECT m.id FROM insight_app.messages m JOIN insight_app.conversations c ON c.id=m.conversation_id WHERE m.id=:id AND c.account_id=:account AND c.tenant_id=:tenant AND m.role=\'assistant\'',{'id':str(body.message_id),'account':user.id,'tenant':user.tenant_id})
    if not found:raise HTTPException(404,'Response not found.')
    execute('INSERT INTO insight_app.feedback(account_id,message_id,rating) VALUES(:account,:message,:rating) ON CONFLICT(account_id,message_id) DO UPDATE SET rating=excluded.rating',{'account':user.id,'message':str(body.message_id),'rating':body.rating});return {'saved':True}

@app.post('/api/chat/stream')
async def chat(body:Ask,user=Depends(current)):
    with limit_lock:
        now=time.monotonic()
        for k in list(limiter):
            if not limiter[k] or now-limiter[k][-1]>60:del limiter[k]
        bucket=limiter[user.id]
        while bucket and now-bucket[0]>60:bucket.popleft()
        if len(bucket)>=15:raise HTTPException(429,'Please wait a minute before asking more questions.')
        bucket.append(now)
    try:provider,model=select_provider(body.provider,body.model)
    except ValueError as error:raise HTTPException(422,str(error))
    if provider=='guided':raise HTTPException(422,'Configure a real AI provider and model in .env to use the product assistant.')
    question=body.question.strip()
    if not question:raise HTTPException(422,'Please enter a question.')
    conversation_id=str(body.conversation_id) if body.conversation_id else str(uuid.uuid4())
    if body.conversation_id:
        conversation=owned_conversation(conversation_id,user)
        if (conversation['provider'],conversation['model'])!=(provider,model):raise HTTPException(409,'Start a new conversation when switching provider or model.')
    else:execute('INSERT INTO insight_app.conversations(id,tenant_id,account_id,title,provider,model) VALUES(:id,:tenant,:account,:title,:provider,:model)',{'id':conversation_id,'tenant':user.tenant_id,'account':user.id,'title':question[:100],'provider':provider,'model':model})
    previous=rows('SELECT role,content,payload FROM insight_app.messages WHERE conversation_id=:id ORDER BY created_at DESC,id DESC LIMIT 8',{'id':conversation_id})[::-1]
    previous_result=next((m['payload']['report'] for m in reversed(previous) if m['role']=='assistant' and m['payload'].get('report') and m['payload'].get('access_scope')==user.role_name),{})
    previous_sql=previous_result.get('sql','')
    execute('INSERT INTO insight_app.messages(id,conversation_id,role,content) VALUES(:id,:conversation,\'user\',:content)',{'id':str(uuid.uuid4()),'conversation':conversation_id,'content':question})
    async def stream():
        def event(kind,data):return 'event: '+kind+'\ndata: '+json.dumps(jsonable_encoder(data),ensure_ascii=False)+'\n\n'
        yield event('conversation',{'id':conversation_id})
        state={'question':question,'identity':user,'provider':provider,'model':model,'history':[{'role':m['role'],'content':m['content']} for m in previous],'previous_plan':previous_sql,'previous_result':previous_result}
        try:
            response=None
            async with asyncio.timeout(120):
                async for mode,update in graph.astream(state,stream_mode=['updates','custom']):
                    if mode=='custom':
                        if update.get('event')=='answer_delta':yield event('answer_delta',{'target':update['target'],'text':update['text']})
                        continue
                    for node,values in update.items():
                        yield event('stage',{'node':node})
                        if node=='sql_execution' and values.get('sql_result'):yield event('report',values['sql_result'])
                        if node=='response_generation':response=values['response']
            if response is None:raise RuntimeError('Workflow produced no response.')
            id=str(uuid.uuid4());response['message_id']=id;response['conversation_id']=conversation_id
            content=response['answer']+('\n\n'+response['documentation']['answer'] if response.get('kind')=='hybrid' and response.get('documentation') else '')
            execute('INSERT INTO insight_app.messages(id,conversation_id,role,content,payload) VALUES(:id,:conversation,\'assistant\',:content,CAST(:payload AS jsonb))',{'id':id,'conversation':conversation_id,'content':content,'payload':json.dumps(jsonable_encoder(response))})
            if response.get('report') and response.get('kind')!='summary':
                report=response['report'];execute('INSERT INTO insight_app.queries(id,tenant_id,account_id,message_id,question,sql_text,row_count,duration_ms,status) VALUES(:id,:tenant,:account,:message,:question,:sql,:count,:duration,\'success\')',{'id':str(uuid.uuid4()),'tenant':user.tenant_id,'account':user.id,'message':id,'question':question,'sql':report['sql'],'count':len(report['rows']),'duration':response['duration_ms']})
            record('chat_completed',tenant=user.tenant_id,role=user.role_name,duration_ms=response['duration_ms'],success=True)
            yield event('result',response)
        except Exception as error:
            record('chat_failed',tenant=user.tenant_id,role=user.role_name,error_type=type(error).__name__,success=False)
            # Do not return provider or database exception strings that can contain secrets.
            safe=assistant_error(error)
            yield event('error',{'detail':safe,'conversation_id':conversation_id})
    return StreamingResponse(stream(),media_type='text/event-stream',headers={'X-Accel-Buffering':'no','Cache-Control':'no-cache'})
