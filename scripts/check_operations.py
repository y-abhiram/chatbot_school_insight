"""Content-free local readiness check: API, Redis, worker, database and recent backup."""
import json,sys,os,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from product.cache import client
from product.storage import rows
from product.config import ROOT
result={}
try:result['database']=rows('SELECT 1 AS ok')[0]['ok']==1
except Exception:result['database']=False
try:result['redis']=client().ping()
except Exception:result['redis']=False
try:
 from product.jobs import celery
 result['worker']=bool(celery.control.inspect(timeout=3).ping())
except Exception:result['worker']=False
try:result['api']=httpx.get('http://127.0.0.1:8100/api/health',timeout=5,trust_env=False).status_code==200
except Exception:result['api']=False
backups=sorted(Path(os.getenv('PRODUCT_BACKUP_DIRECTORY') or str(ROOT/'.runtime/backups')).glob('*/manifest.json'))
result['latest_backup']=str(backups[-1].parent) if backups else None
result['restore_verified']=bool(backups and json.loads(backups[-1].read_text()).get('restore_verified'))
result['backup_age_hours']=round((time.time()-backups[-1].stat().st_mtime)/3600,2) if backups else None
result['backup_fresh']=bool(backups and result['backup_age_hours']<36)
print(json.dumps(result,indent=2))
raise SystemExit(0 if all(result[k] for k in ['database','redis','worker','api','restore_verified','backup_fresh']) else 1)
