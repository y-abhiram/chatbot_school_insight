"""Organisation-specific source configuration; connection secrets never leave the server."""
import json,re
from pathlib import Path
from product.config import ROOT,TENANT,settings
from product.storage import rows

def source_for(tenant=TENANT):
    found=rows('SELECT tenant_id,name,adapter,view_schema,source_schema,policies,overview,catalog FROM insight_app.sources WHERE tenant_id=:tenant',{'tenant':tenant})
    if not found:raise ValueError('This organisation is not configured.')
    return found[0]

def query_url(tenant=TENANT):
    if tenant==TENANT:return settings()['query_url']
    path=ROOT/'.runtime/tenants.json'
    sources=json.loads(path.read_text()) if path.exists() else {}
    if tenant not in sources:raise ValueError('This organisation’s database connection is not configured.')
    return sources[tenant]['query_url']

def safe_tenant(tenant):
    if not re.fullmatch(r'[a-z0-9][a-z0-9-]{1,62}',tenant):raise ValueError('Use a valid organisation ID.')
    return tenant
