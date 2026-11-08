"""One-time administrator-issued recovery links, password change, and verified-source provisioning."""
import hashlib,secrets
from fastapi import HTTPException
from sqlalchemy import text
from argon2.exceptions import VerifyMismatchError,InvalidHashError
from product.storage import engine,rows,execute
from product.auth import ph,admin
from product.observability import audit
from product.sql_engine import run_sql
from product.sources import source_for

def check_password(value):
    if len(value)<12 or len(value)>200:raise HTTPException(422,'Use a password between 12 and 200 characters.')

def issue_reset(user,account_id):
    admin(user)
    target=rows('SELECT id FROM insight_app.accounts WHERE id=:id AND tenant_id=:tenant',{'id':account_id,'tenant':user.tenant_id})
    if not target:raise HTTPException(404,'Account not found.')
    token=secrets.token_urlsafe(40)
    with engine().begin() as c:
        c.execute(text('DELETE FROM insight_app.password_resets WHERE account_id=:id'),{'id':account_id})
        c.execute(text("INSERT INTO insight_app.password_resets(token_hash,account_id,expires_at,created_by) VALUES(:token,:id,now()+interval '15 minutes',:actor)"),{'token':hashlib.sha256(token.encode()).hexdigest(),'id':account_id,'actor':user.id})
    audit(user,'password_reset_issued',{'target_account':account_id})
    return {'path':'/reset-password#token='+token,'expires_in_seconds':900,'delivery':'Share this one-time link privately with the verified account holder.'}

def consume_reset(token,password):
    check_password(password)
    digest=hashlib.sha256(token.encode()).hexdigest()
    with engine().begin() as c:
        reset=c.execute(text('SELECT r.account_id FROM insight_app.password_resets r JOIN insight_app.accounts a ON a.id=r.account_id WHERE r.token_hash=:token AND r.expires_at>now() AND r.used_at IS NULL AND a.active FOR UPDATE OF r'),{'token':digest}).mappings().first()
        if not reset:raise HTTPException(400,'This recovery link is invalid, expired, or already used. Ask your administrator for a new link.')
        c.execute(text('UPDATE insight_app.accounts SET password_hash=:hash WHERE id=:id'),{'hash':ph.hash(password),'id':reset['account_id']})
        c.execute(text('UPDATE insight_app.password_resets SET used_at=now() WHERE token_hash=:token'),{'token':digest})
        c.execute(text('DELETE FROM insight_app.sessions WHERE account_id=:id'),{'id':reset['account_id']})
    return {'changed':True,'message':'Your password was changed. Sign in with your new password.'}

def change_password(user,current_password,new_password):
    check_password(new_password)
    account=rows('SELECT password_hash FROM insight_app.accounts WHERE id=:id AND tenant_id=:tenant',{'id':user.id,'tenant':user.tenant_id})[0]
    try:valid=ph.verify(account['password_hash'],current_password)
    except (VerifyMismatchError,InvalidHashError):valid=False
    if not valid:raise HTTPException(400,'The current password is incorrect.')
    with engine().begin() as c:
        c.execute(text('UPDATE insight_app.accounts SET password_hash=:hash WHERE id=:id'),{'hash':ph.hash(new_password),'id':user.id})
        c.execute(text('DELETE FROM insight_app.sessions WHERE account_id=:id'),{'id':user.id})
    audit(user,'password_changed')
    return {'changed':True,'message':'Password changed. Please sign in again.'}

def source_users(user):
    admin(user);schema=source_for(user.tenant_id)['view_schema']
    # Identity contract is exposed through the reviewed, redacted source view.
    return run_sql(f'SELECT user_id,username,first_name,last_name,role_name,is_active FROM {schema}.users',user)['rows']

def provision(user,source_user_id):
    admin(user)
    available=source_users(user)
    source=next((r for r in available if r['user_id']==source_user_id),None)
    if not source or not source['is_active']:raise HTTPException(422,'Choose an active user from the verified source directory.')
    if source['role_name'] not in ('Admin','Faculty','Student'):raise HTTPException(422,'The source user has an unsupported role.')
    if rows('SELECT id FROM insight_app.accounts WHERE tenant_id=:tenant AND user_id=:uid',{'tenant':user.tenant_id,'uid':source_user_id}):raise HTTPException(409,'This source user already has an account.')
    # No password is returned; an administrator shares a short-lived setup link.
    with engine().begin() as c:
        id=c.execute(text('INSERT INTO insight_app.accounts(tenant_id,user_id,username,password_hash,role_snapshot,name_snapshot) VALUES(:tenant,:uid,:username,:hash,:role,:name) RETURNING id'),{'tenant':user.tenant_id,'uid':source_user_id,'username':source['username'],'hash':ph.hash(secrets.token_urlsafe(60)),'role':source['role_name'],'name':source['first_name']+' '+(source['last_name'] or '')}).scalar()
    audit(user,'account_provisioned',{'target_account':id})
    return {'account_id':id,**issue_reset(user,id)}
