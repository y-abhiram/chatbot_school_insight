"""Page-aware PDF ingestion, pgvector + lexical retrieval, and local cross-encoder reranking."""
import hashlib,json,re,uuid
from pathlib import Path
from functools import lru_cache
import numpy as np
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from pypdf import PdfReader
from product.config import ROOT
from product.storage import engine,rows,execute
from sqlalchemy import text
EMBEDDING_MODEL='sentence-transformers/all-MiniLM-L6-v2'
RERANKER_MODEL='cross-encoder/ms-marco-MiniLM-L6-v2'

def model_path(name):
    base=Path.home()/'.cache/huggingface/hub'/('models--'+name.replace('/','--'))
    ref=base/'refs/main'
    if ref.exists():
        snapshot=base/'snapshots'/ref.read_text().strip()
        if snapshot.exists():return str(snapshot)
    return name

class LocalEmbeddings(Embeddings):
    def __init__(self):
        from sentence_transformers import SentenceTransformer
        self.model=SentenceTransformer(model_path(EMBEDDING_MODEL),device='cpu',cache_folder=str(ROOT/'.runtime/models'))
    def embed_documents(self,texts):return self.model.encode(texts,normalize_embeddings=True,batch_size=32).tolist()
    def embed_query(self,text):return self.embed_documents([text])[0]
@lru_cache
def embeddings():return LocalEmbeddings()
@lru_cache
def reranker():
    from sentence_transformers import CrossEncoder
    return CrossEncoder(model_path(RERANKER_MODEL),device='cpu',cache_folder=str(ROOT/'.runtime/models'),max_length=512)

def ingest_document(document_id,path,tenant):
    try:
        reader=PdfReader(path)
        if reader.is_encrypted or len(reader.pages)>300:raise ValueError('Use an unencrypted PDF with at most 300 pages.')
        splitter=RecursiveCharacterTextSplitter(chunk_size=1400,chunk_overlap=220)
        docs=[]
        for number,page in enumerate(reader.pages,1):
            content=(page.extract_text() or '').replace('\x00','')
            content=re.sub(r'School Management Database - User Manual\s*','',content)
            sections=re.findall(r'(?m)^\s*(\d+(?:\.\d+)?[a-z]?\.?\s+[A-Z][^\n]{3,90})',content)
            section=sections[0].strip() if sections else 'Manual reference'
            docs+=splitter.split_documents([Document(page_content=content,metadata={'page':number,'section':section})])
        if not docs:raise ValueError('No extractable text was found. Scanned PDFs need OCR before ingestion.')
        vectors=embeddings().embed_documents([d.page_content for d in docs])
        with engine().begin() as conn:
            conn.execute(text('DELETE FROM insight_app.chunks WHERE document_id=:id AND tenant_id=:tenant'),{'id':document_id,'tenant':tenant})
            for doc,vector in zip(docs,vectors):
                conn.execute(text('INSERT INTO insight_app.chunks(id,document_id,tenant_id,page,section,content,embedding) VALUES(:id,:doc,:tenant,:page,:section,:content,CAST(:embedding AS public.vector))'),{'id':str(uuid.uuid4()),'doc':document_id,'tenant':tenant,'page':doc.metadata['page'],'section':doc.metadata['section'],'content':doc.page_content,'embedding':json.dumps(vector)})
            conn.execute(text("UPDATE insight_app.documents SET status='ready',pages=:pages,error=NULL WHERE id=:id AND tenant_id=:tenant"),{'id':document_id,'tenant':tenant,'pages':len(reader.pages)})
        return {'pages':len(reader.pages),'chunks':len(docs)}
    except Exception:
        execute("UPDATE insight_app.documents SET status='failed',error='Ingestion failed; check worker logs and PDF format.' WHERE id=:id AND tenant_id=:tenant",{'id':document_id,'tenant':tenant})
        raise

def retrieve(question,tenant):
    vector=json.dumps(embeddings().embed_query(question[:2000]))
    # Use OR keyword retrieval and independent vector candidates; a long question must not
    # require every filler word to occur in a procedural paragraph.
    stop={'what','when','where','which','does','how','the','and','are','can','you','please','explain','manual','school','process','procedure','about','from','work','works','say','says','show','using','this','that','with','into','there','their','they','generate','generated'}
    terms=[t for t in re.findall(r'[a-zA-Z]{3,}',question.lower()) if t not in stop][:12]
    keywords=' OR '.join(dict.fromkeys(terms)) or question[:200]
    parameters={'tenant':tenant,'vector':vector,'question':keywords}
    candidates=rows('''WITH eligible AS (
        SELECT c.id,c.document_id,c.page,c.section,c.content,c.embedding,c.search,d.name
        FROM insight_app.chunks c JOIN insight_app.documents d ON d.id=c.document_id
        WHERE c.tenant_id=:tenant AND d.tenant_id=:tenant AND d.status='ready'
    ),semantic AS (
        SELECT *,row_number() OVER(ORDER BY embedding <=> CAST(:vector AS public.vector)) AS position
        FROM eligible ORDER BY embedding <=> CAST(:vector AS public.vector) LIMIT 20
    ),lexical AS (
        SELECT *,row_number() OVER(ORDER BY ts_rank_cd(search,websearch_to_tsquery('english',:question)) DESC) AS position
        FROM eligible WHERE search @@ websearch_to_tsquery('english',:question)
        ORDER BY ts_rank_cd(search,websearch_to_tsquery('english',:question)) DESC LIMIT 20
    ),scores AS (
        SELECT id,1.0/(40+position) AS score FROM semantic
        UNION ALL SELECT id,1.2/(40+position) AS score FROM lexical
    ) SELECT e.id,e.document_id,e.page,e.section,e.content,e.name,sum(s.score) AS retrieval_score,
       ts_rank_cd(e.search,websearch_to_tsquery('english',:question)) AS lexical
       FROM eligible e JOIN scores s USING(id)
       GROUP BY e.id,e.document_id,e.page,e.section,e.content,e.name,e.search
       ORDER BY retrieval_score DESC LIMIT 20''',parameters)
    return candidates

def rerank(question,candidates):
    if not candidates:return []
    scores=reranker().predict([(question,c['content']) for c in candidates])
    ordered=sorted(zip(candidates,scores),key=lambda pair:float(pair[1]),reverse=True)
    return [dict(c,rerank_score=float(score)) for c,score in ordered[:5]]
