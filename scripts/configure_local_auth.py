"""Configure peer mapping only for the dedicated cluster owned by this checkout."""
from pathlib import Path
import getpass
ROOT=Path(__file__).resolve().parents[1]
cluster=ROOT/'.runtime/postgres'
user=getpass.getuser()
if not (cluster/'PG_VERSION').exists():raise SystemExit('Initialize the local cluster first; see README.md.')
hba=cluster/'pg_hba.conf'
rule='local school_demo school_app peer map=schooldemo'
if rule not in hba.read_text():hba.write_text(rule+'\n'+hba.read_text())
ident=cluster/'pg_ident.conf'
rule=f'schooldemo {user} school_app'
if rule not in ident.read_text():ident.write_text(ident.read_text()+'\n'+rule+'\n')
print('Local peer mapping ready. Reload the dedicated PostgreSQL cluster.')
