"""Additive control-plane migration; never alters source school records."""
import sys,json
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from dotenv import dotenv_values
from sqlalchemy import create_engine,text
from product.config import ROOT,admin_database_url
e=create_engine(admin_database_url(),hide_parameters=True)
statements=[
'''CREATE TABLE IF NOT EXISTS insight_app.sources(tenant_id text PRIMARY KEY,name text NOT NULL,adapter text NOT NULL DEFAULT 'school',view_schema text NOT NULL DEFAULT 'insight',source_schema text NOT NULL DEFAULT 'school',policies jsonb NOT NULL DEFAULT '{}',overview jsonb NOT NULL DEFAULT '[]',catalog jsonb,created_at timestamptz NOT NULL DEFAULT now())''',
'''ALTER TABLE insight_app.accounts ADD COLUMN IF NOT EXISTS role_snapshot text''',
'''ALTER TABLE insight_app.accounts ADD COLUMN IF NOT EXISTS name_snapshot text''',
'''ALTER TABLE insight_app.accounts ADD COLUMN IF NOT EXISTS student_id_snapshot integer''',
'''ALTER TABLE insight_app.accounts ADD COLUMN IF NOT EXISTS faculty_id_snapshot integer''',
'''CREATE TABLE IF NOT EXISTS insight_app.password_resets(token_hash text PRIMARY KEY,account_id bigint NOT NULL REFERENCES insight_app.accounts(id),expires_at timestamptz NOT NULL,used_at timestamptz,created_by bigint REFERENCES insight_app.accounts(id))''',
'''CREATE TABLE IF NOT EXISTS insight_app.audit_events(id bigserial PRIMARY KEY,tenant_id text NOT NULL,account_id bigint,event text NOT NULL,detail jsonb NOT NULL DEFAULT '{}',created_at timestamptz NOT NULL DEFAULT now())''',
'''CREATE INDEX IF NOT EXISTS audit_events_tenant_date ON insight_app.audit_events(tenant_id,created_at)''',
'''CREATE OR REPLACE VIEW insight_app.identities AS SELECT a.id,a.tenant_id,a.username,a.password_hash,
 a.active AND CASE WHEN a.tenant_id='school-demo' THEN coalesce(u.is_active,false) ELSE true END AS active,a.user_id,
 CAST(coalesce(r.role_name,a.role_snapshot) AS varchar(30)) AS role_name,
 coalesce(u.first_name||' '||coalesce(u.last_name,''),a.name_snapshot) AS name,
 coalesce(s.student_id,a.student_id_snapshot) AS student_id,coalesce(f.faculty_id,a.faculty_id_snapshot) AS faculty_id
 FROM insight_app.accounts a LEFT JOIN school.users u ON u.user_id=a.user_id AND a.tenant_id='school-demo'
 LEFT JOIN school.roles r ON r.role_id=u.role_id LEFT JOIN school.students s ON s.user_id=u.user_id LEFT JOIN school.faculty f ON f.user_id=u.user_id''',
'''INSERT INTO insight_app.sources(tenant_id,name,adapter,catalog) SELECT 'school-demo','School management','school',source FROM insight_app.schema_catalog WHERE id=1 ON CONFLICT(tenant_id) DO NOTHING''',
'''GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA insight_app TO insight_service''',
'''GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA insight_app TO insight_service''',
]
with e.begin() as c:
 for statement in statements:c.execute(text(statement))
print('Control-plane migration complete. Source school records unchanged.')
