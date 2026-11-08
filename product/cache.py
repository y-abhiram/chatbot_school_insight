import json,hashlib
from functools import lru_cache
import redis
from fastapi.encoders import jsonable_encoder
from product.config import settings
@lru_cache
def client():return redis.Redis.from_url(settings()['redis_url'],socket_connect_timeout=1,socket_timeout=1,decode_responses=True)
def cache_key(kind,*parts):return 'insight:'+kind+':'+hashlib.sha256(json.dumps(parts,sort_keys=True,default=str).encode()).hexdigest()
def get(key):
    try:
        value=client().get(key)
        return json.loads(value) if value else None
    except (redis.RedisError,ValueError):return None

def put(key,value,seconds=30):
    try:client().setex(key,seconds,json.dumps(jsonable_encoder(value)))
    except redis.RedisError:pass
