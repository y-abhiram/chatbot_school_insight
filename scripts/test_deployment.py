"""Exercise the running production containers without printing credentials."""
import argparse
import hashlib
import http.cookiejar
import json
import os
import subprocess
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def compose(*args):
    result = subprocess.run(['bash', 'scripts/production.sh', *args], cwd=ROOT,
                            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    return result.stdout


def check(condition, label):
    if not condition:
        raise AssertionError(label)
    print('PASS:', label, flush=True)
    checks.append(label)


def request(path, body=None, client=None, origin=None):
    headers = {'Content-Type': 'application/json'} if body is not None else {}
    if origin:
        headers['Origin'] = origin
    req = urllib.request.Request(base + path, data=json.dumps(body).encode() if body is not None else None, headers=headers)
    try:
        response = (client or urllib.request.build_opener(urllib.request.ProxyHandler({}))).open(req, timeout=150)
        return response.status, response.read(), response.headers
    except urllib.error.HTTPError as error:
        return error.code, error.read(), error.headers


def school_fingerprint():
    dump = compose('exec', '-T', 'postgres', 'pg_dump', '-U', 'postgres', '-d', 'school_ai',
                   '--schema=school', '--no-owner', '--no-privileges', '--column-inserts')
    # pg_dump adds a random psql restriction token; it is not database content.
    lines = [line for line in dump.splitlines() if not line.startswith((b'\\restrict', b'\\unrestrict'))]
    return hashlib.sha256(b'\n'.join(lines)).hexdigest()


def ask(question, client):
    status, body, _ = request('/api/chat/stream', {'question': question, 'provider': 'auto'}, client)
    check(status == 200, 'Streaming endpoint accepted: ' + question)
    events = []
    for block in body.decode().split('\n\n'):
        lines = block.splitlines()
        kind = next((line[7:] for line in lines if line.startswith('event: ')), '')
        data = next((line[6:] for line in lines if line.startswith('data: ')), None)
        if data:
            events.append((kind, json.loads(data)))
    check(not any(kind == 'error' for kind, _ in events), 'No provider or workflow error: ' + question)
    result = next((data for kind, data in events if kind == 'result'), None)
    check(bool(result), 'Final SSE result arrived: ' + question)
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', default='http://localhost:3080')
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--restart', action='store_true', help='Recreate this production stack while retaining its volumes.')
    parser.add_argument('--output', default='docs/deployment-verification.json')
    args = parser.parse_args()
    base = args.url.rstrip('/')
    checks = []
    report = {'verified_at': datetime.now(timezone.utc).isoformat(), 'url': base, 'checks': checks,
              'live_ai_requested': args.live, 'restart_requested': args.restart,
              'public_https_verified': False, 'aws_deployed': False}
    try:
        config = json.loads(compose('config', '--format', 'json'))
        for name in ('postgres', 'redis', 'backend'):
            check(not config['services'][name].get('ports'), name + ' has no published host ports')
        check(all(port['host_ip'] == '127.0.0.1' for port in config['services']['frontend']['ports']),
              'Frontend binds only to loopback')
        for name in ('backend', 'frontend', 'worker'):
            info = json.loads(subprocess.run(['docker', 'inspect', compose('ps', '-q', name).decode().strip()],
                                            check=True, capture_output=True).stdout)[0]
            check(info['State']['Health']['Status'] == 'healthy', name + ' container is healthy')
            check(info['Config'].get('User') not in ('', 'root', '0'), name + ' runs as a non-root user')
        status, body, _ = request('/api/health')
        check(status == 200 and json.loads(body)['database'] and json.loads(body)['redis'],
              'Frontend proxies API readiness to PostgreSQL and Redis')
        check(request('/chat')[0] == 200, 'Existing chat UI is served')
        check(request('/api/team')[0] == 401, 'Anonymous private data request is rejected')
        accounts = json.loads(compose('exec', '-T', 'backend', 'cat', '.runtime/demo-accounts.json'))
        jar = http.cookiejar.CookieJar()
        client = urllib.request.build_opener(urllib.request.ProxyHandler({}), urllib.request.HTTPCookieProcessor(jar))
        admin = next(account for account in accounts if account['role'] == 'Admin')
        status, _, headers = request('/api/auth/login', {'username': admin['username'], 'password': admin['password']}, client, base)
        check(status == 200 and 'HttpOnly' in headers.get('Set-Cookie', ''), 'Admin login and HttpOnly session cookie work through proxy')
        status, body, _ = request('/api/overview', client=client)
        overview = json.loads(body)
        check(status == 200 and overview.get('counts', {}).get('students') == 4, 'Dashboard returns four actual sample students')
        check(request('/api/auth/logout', {}, client, 'https://untrusted.example')[0] == 403,
              'Cross-origin mutation is rejected')
        docs = json.loads(request('/api/documents', client=client)[1])
        check(any(doc['status'] == 'ready' and doc['pages'] == 24 for doc in docs), '24-page manual is indexed and ready')
        student = next(account for account in accounts if account['username'] == 'stu_arjun')
        student_client = urllib.request.build_opener(urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        check(request('/api/auth/login', {'username': student['username'], 'password': student['password']}, student_client, base)[0] == 200,
              'Student login works')
        check(request('/api/team', client=student_client)[0] == 403, 'Student cannot access admin team data')
        probe = '''
from product.auth import Identity
from product.storage import rows
from product.sql_engine import run_sql,validate_sql,UnsafeSQL
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from product.storage import engine
r=rows("SELECT * FROM insight_app.identities WHERE username='stu_arjun'")[0]
u=Identity(**{k:r[k] for k in Identity.__dataclass_fields__})
assert run_sql('SELECT student_name FROM insight.students',u,use_cache=False)['rows']==[{'student_name':'Arjun Rao'}]
try:validate_sql('DELETE FROM school.students')
except UnsafeSQL:pass
else:raise AssertionError('Write query was accepted')
with engine('query').connect() as c:
    try:c.execute(text('SELECT password_hash FROM school.users'))
    except DBAPIError:pass
    else:raise AssertionError('Raw password access was accepted')
print('permission checks passed')
'''
        check('permission checks passed' in compose('exec', '-T', 'backend', 'python', '-c', probe).decode(),
              'Actual database enforces student scope and rejects raw-table access and writes')
        if args.live:
            result = ask('How many students are there?', client)
            data = result.get('report', {}).get('rows', [])
            check(len(data) == 1 and list(data[0].values()) == [4], 'Live AI count matches four database students')
            result = ask('Explain the leave approval process from the manual.', client)
            check(bool((result.get('documentation') or {}).get('citations')), 'Live manual answer includes page citations')
            result = ask("Show Kiran's marks", student_client)
            check(result.get('report') is None, 'Student chat refuses another student’s private marks')
        before = school_fingerprint()
        compose('run', '--rm', '--no-deps', 'bootstrap')
        check(school_fingerprint() == before, 'Repeat bootstrap preserves complete school schema and data')
        if args.restart:
            compose('down')
            compose('up', '-d', '--wait', '--wait-timeout', '300')
            check(school_fingerprint() == before, 'School schema and every sample row survive full container recreation')
            check(request('/api/auth/me', client=client)[0] == 200, 'App accounts and existing login session persist after recreation')
            check(any(doc['status'] == 'ready' for doc in json.loads(request('/api/documents', client=client)[1])),
                  'Indexed manual persists after recreation')
        report['school_fingerprint'] = before
        report['passed'] = True
    except Exception as error:
        report['passed'] = False
        report['error_type'] = type(error).__name__
        print('FAILED:', type(error).__name__, flush=True)
        raise
    finally:
        report['checks_passed'] = len(checks)
        (ROOT / args.output).write_text(json.dumps(report, indent=2) + '\n')
