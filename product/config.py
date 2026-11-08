import json
import os
from pathlib import Path
from functools import lru_cache
from dotenv import load_dotenv
ROOT=Path(__file__).resolve().parents[1]
load_dotenv(ROOT/'.env')
STATE=ROOT/'.runtime/product.json'
TENANT='school-demo'

def env_value(name, default=''):
    """Read runtime Compose secrets, with local environment compatibility."""
    filename=os.getenv(name+'_FILE')
    if filename:
        if os.getenv(name):raise ValueError(f'Set either {name} or {name}_FILE, not both.')
        return Path(filename).read_text().strip()
    return os.getenv(name,default)

def database_url(username,password):
    from sqlalchemy.engine import URL
    return URL.create('postgresql+psycopg2',username=username,password=password,
        host=os.getenv('PRODUCT_DATABASE_HOST','127.0.0.1'),port=int(os.getenv('PRODUCT_DATABASE_PORT','55433')),
        database=os.getenv('POSTGRES_DB','school_ai'))

def admin_database_url():
    explicit=env_value('PRODUCT_ADMIN_DATABASE_URL')
    if explicit:return explicit
    password=env_value('POSTGRES_PASSWORD')
    if not password:
        from dotenv import dotenv_values
        password=dotenv_values(ROOT/'.runtime/services.env')['PRODUCT_POSTGRES_PASSWORD']
    return database_url('postgres',password)

for _name in ('OPENAI_API_KEY','GEMINI_API_KEY','GROQ_API_KEY','LANGSMITH_API_KEY'):
    if os.getenv(_name+'_FILE'):os.environ[_name]=env_value(_name)

@lru_cache
def settings():
    local=json.loads(STATE.read_text()) if STATE.exists() else {}
    return {'app_url':(env_value('PRODUCT_APP_DATABASE_URL') or (database_url('insight_service',env_value('PRODUCT_APP_PASSWORD')).render_as_string(hide_password=False) if os.getenv('PRODUCT_DATABASE_HOST') else local.get('app_url',''))),
            'query_url':(env_value('PRODUCT_QUERY_DATABASE_URL') or (database_url('insight_query',env_value('PRODUCT_QUERY_PASSWORD')).render_as_string(hide_password=False) if os.getenv('PRODUCT_DATABASE_HOST') else local.get('query_url',''))),
            'redis_url':(os.getenv('PRODUCT_REDIS_URL') or 'redis://127.0.0.1:56379/0')}
