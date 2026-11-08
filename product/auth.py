import hashlib,secrets,time
from dataclasses import dataclass
from threading import Lock
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError,InvalidHashError
from fastapi import Request,HTTPException
from product.storage import rows,execute
from product.config import TENANT
ph=PasswordHasher();dummy=ph.hash(secrets.token_urlsafe(32))
lock=Lock();attempts={}
@dataclass(frozen=True)
class Identity:
    id:int
    tenant_id:str
    user_id:int
    username:str
    role_name:str
    name:str
    student_id:int|None=None
    faculty_id:int|None=None

def public(identity):return {k:v for k,v in identity.__dict__.items() if k not in ('user_id','student_id','faculty_id')}
def login(username,password,host,tenant=TENANT):
    now=time.monotonic()
    with lock:
        for key in list(attempts):
            if now-attempts[key][0]>600:del attempts[key]
        start,count=attempts.get(host,(now,0))
        if count>=10:raise HTTPException(429,'Too many login attempts. Try again in ten minutes.')
        attempts[host]=(start,count+1)
    match=rows('SELECT * FROM insight_app.identities WHERE tenant_id=:tenant AND username=:username',{'tenant':tenant,'username':username})
    account=match[0] if match else None
    try:valid=ph.verify(account['password_hash'] if account else dummy,password)
    except (VerifyMismatchError,InvalidHashError):valid=False
    if not valid or not account or not account['active']:raise HTTPException(401,'Username or password is incorrect.')
    with lock:attempts.pop(host,None)
    verified=Identity(**{k:account[k] for k in Identity.__dataclass_fields__})
    validate_external(verified)
    token=secrets.token_urlsafe(40)
    execute("INSERT INTO insight_app.sessions(token_hash,account_id,expires_at) VALUES(:token,:id,now()+interval '8 hours')",{'token':hashlib.sha256(token.encode()).hexdigest(),'id':account['id']})
    return token

def current(request:Request):
    token=request.cookies.get('insight_session','')
    if not token:raise HTTPException(401,'Please sign in to your school workspace.')
    data=rows('SELECT i.* FROM insight_app.sessions s JOIN insight_app.identities i ON i.id=s.account_id WHERE s.token_hash=:token AND s.expires_at>now() AND i.active',{'token':hashlib.sha256(token.encode()).hexdigest()})
    if not data:raise HTTPException(401,'Your session expired. Please sign in again.')
    identity=Identity(**{k:data[0][k] for k in Identity.__dataclass_fields__})
    validate_external(identity)
    return identity
def admin(user):
    if user.role_name!='Admin':raise HTTPException(403,'This page is available to administrators.')
def logout(token):execute('DELETE FROM insight_app.sessions WHERE token_hash=:token',{'token':hashlib.sha256(token.encode()).hexdigest()})


def validate_external(identity):
    if identity.tenant_id==TENANT:return
    from product.sources import source_for
    from product.sql_engine import run_sql
    source=source_for(identity.tenant_id)
    try:
        records=run_sql(f"SELECT role_name,is_active FROM {source['view_schema']}.users WHERE user_id={identity.user_id}",identity,use_cache=False)['rows']
    except Exception:raise HTTPException(503,'The organisation identity source is unavailable.')
    if len(records)!=1 or not records[0]['is_active'] or records[0]['role_name']!=identity.role_name:
        raise HTTPException(401,'Your source account or role changed. Contact your organisation administrator.')
