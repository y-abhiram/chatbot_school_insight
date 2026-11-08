"""Structured, content-free operational logging and administrator metrics."""
import json,logging,time,uuid
from pathlib import Path
from logging.handlers import RotatingFileHandler
from threading import Lock
from collections import Counter
from product.config import ROOT
ROOT.joinpath('.runtime/logs').mkdir(exist_ok=True,parents=True,mode=0o700)
ROOT.joinpath('.runtime/logs').chmod(0o700)
logger=logging.getLogger('insight.operations');logger.setLevel(logging.INFO);logger.propagate=False
if not logger.handlers:
    handler=RotatingFileHandler(ROOT/'.runtime/logs/operations.jsonl',maxBytes=2_000_000,backupCount=5)
    Path(handler.baseFilename).chmod(0o600)
    logger.addHandler(handler)
lock=Lock();counts=Counter();started=time.time()
def record(event,**fields):
    # Never log bodies, questions, SQL, tokens, passwords or provider exception messages.
    safe={k:v for k,v in fields.items() if k in {'request_id','route','status','duration_ms','error_type','tenant','role','account','success','count'}}
    logger.info(json.dumps({'time':time.time(),'event':event,**safe},default=str))
    with lock:counts[event]+=1

def metrics():
    with lock:return {'uptime_seconds':round(time.time()-started),'events':dict(counts)}

def audit(user,event,detail=None):
    from product.storage import execute
    # Audit metadata is intentionally narrow. Never accept arbitrary provider text here.
    execute('INSERT INTO insight_app.audit_events(tenant_id,account_id,event,detail) VALUES(:tenant,:account,:event,CAST(:detail AS jsonb))',{'tenant':user.tenant_id,'account':user.id,'event':event,'detail':json.dumps(detail or {})})
