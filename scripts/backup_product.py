"""Back up the control/school database and PDFs; optionally verify a restore into a NEW database."""
import argparse,hashlib,json,os,subprocess,sys,tarfile,time,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
from dotenv import load_dotenv
load_dotenv(ROOT/'.env')
def run(args,**kwargs):return subprocess.run(args,check=True,stderr=subprocess.PIPE,**kwargs)
def backup(verify=False,output=None):
    folder=Path(output) if output else Path(os.getenv('PRODUCT_BACKUP_DIRECTORY') or str(ROOT/'.runtime/backups'))/time.strftime('%Y%m%d-%H%M%S')
    folder.mkdir(parents=True,exist_ok=False,mode=0o700)
    dump=folder/'database.dump'
    # Capture reference counts and the dump from the same MVCC snapshot, even if
    # users submit requests or school data changes while a backup is running.
    import psycopg2
    from dotenv import dotenv_values
    secret=dotenv_values(ROOT/'.runtime/services.env')['PRODUCT_POSTGRES_PASSWORD']
    connection=psycopg2.connect(dbname='school_ai',user='postgres',password=secret,host='127.0.0.1',port=55433)
    query="SELECT json_build_object('users',(SELECT count(*) FROM school.users),'students',(SELECT count(*) FROM school.students),'documents',(SELECT count(*) FROM insight_app.documents),'accounts',(SELECT count(*) FROM insight_app.accounts));"
    try:
        with connection.cursor() as cursor:
            cursor.execute('BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
            cursor.execute('SELECT pg_export_snapshot()');snapshot=cursor.fetchone()[0]
            cursor.execute(query);expected=cursor.fetchone()[0]
            with dump.open('wb') as f:run(['docker','exec','chat_postgres_1','pg_dump','-U','postgres','--format=custom','--no-password','--snapshot='+snapshot,'school_ai'],stdout=f)
    finally:connection.rollback();connection.close()
    dump.chmod(0o600)
    archive=folder/'documents.tar.gz'
    with tarfile.open(archive,'w:gz') as tar:
        uploads=ROOT/'.runtime/uploads'
        if uploads.exists():tar.add(uploads,arcname='uploads')
    archive.chmod(0o600)
    manifest={'created_at':time.strftime('%Y-%m-%dT%H:%M:%S%z'),'files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [dump,archive]},'restore_verified':False,'scope':'school_ai control/source database and uploaded PDFs; connection/API secrets excluded'}
    if verify:
        database='insight_restore_verify_'+uuid.uuid4().hex[:12]
        run(['docker','exec','chat_postgres_1','createdb','-U','postgres',database],stdout=subprocess.DEVNULL)
        try:
            with dump.open('rb') as f:run(['docker','exec','-i','chat_postgres_1','pg_restore','-U','postgres','--no-owner','--exit-on-error','-d',database],stdin=f,stdout=subprocess.DEVNULL)
            restored=json.loads(run(['docker','exec','chat_postgres_1','psql','-U','postgres','-d',database,'-At','-c',query],stdout=subprocess.PIPE,text=True).stdout)
            if expected!=restored:raise RuntimeError('Restored row counts do not match.')
            manifest['restore_verified']=True;manifest['verified_counts']=restored
        finally:
            # Only this script's randomly named verification database is removed.
            run(['docker','exec','chat_postgres_1','dropdb','-U','postgres',database],stdout=subprocess.DEVNULL)
    path=folder/'manifest.json';path.write_text(json.dumps(manifest,indent=2));path.chmod(0o600)
    return {'path':str(folder),'restore_verified':manifest['restore_verified']}
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--verify-restore',action='store_true');parser.add_argument('--output');args=parser.parse_args()
    try:print(backup(args.verify_restore,args.output))
    except Exception as error:raise SystemExit('Backup failed ('+type(error).__name__+'). Check local Docker services and backup directory permissions. Original databases were not replaced.')
