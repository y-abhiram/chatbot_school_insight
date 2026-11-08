import sys,uuid,hashlib,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from product.config import ROOT,TENANT
from product.storage import rows,execute
from product.rag import ingest_document,reranker
source=ROOT/'School Management Database - User Manual.pdf'
digest=hashlib.sha256(source.read_bytes()).hexdigest()
existing=rows('SELECT id,status FROM insight_app.documents WHERE tenant_id=:tenant AND sha256=:hash',{'tenant':TENANT,'hash':digest})
if existing and existing[0]['status']=='ready':
    print('Manual is already indexed.');raise SystemExit()
id=str(existing[0]['id']) if existing else str(uuid.uuid4())
if not existing:execute('INSERT INTO insight_app.documents(id,tenant_id,name,sha256) VALUES(:id,:tenant,:name,:hash)',{'id':id,'tenant':TENANT,'name':source.name,'hash':digest})
folder=ROOT/'.runtime/uploads';folder.mkdir(exist_ok=True)
shutil.copyfile(source,folder/f'{id}.pdf')
print('Ingesting the supplied manual with page metadata and local embeddings...',flush=True)
print(ingest_document(id,folder/f'{id}.pdf',TENANT),flush=True)
print('Preparing cross-encoder...',flush=True)
reranker()
print('Manual retrieval and reranking ready.',flush=True)
