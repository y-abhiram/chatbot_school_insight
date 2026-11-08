from functools import lru_cache
from sqlalchemy import create_engine,text
from sqlalchemy.pool import QueuePool
from product.config import settings
@lru_cache
def engine(kind='app',tenant='school-demo'):
    if kind=='query':
        from product.sources import query_url
        url=query_url(tenant)
    else:url=settings()[kind+'_url']
    if not url:raise RuntimeError('Run scripts/bootstrap_product.py first.')
    return create_engine(url,poolclass=QueuePool,pool_size=5,max_overflow=5,pool_pre_ping=True,hide_parameters=True,connect_args={'connect_timeout':5})
def rows(statement,params=None):
    with engine().connect() as conn:return [dict(r) for r in conn.execute(text(statement),params or {}).mappings()]
def execute(statement,params=None):
    with engine().begin() as conn:conn.execute(text(statement),params or {})
