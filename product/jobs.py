from celery import Celery
from product.config import settings,ROOT
from product.rag import ingest_document
celery=Celery('school_insight',broker=settings()['redis_url'],backend=settings()['redis_url'])
celery.conf.update(task_serializer='json',accept_content=['json'],result_serializer='json',task_soft_time_limit=300,task_time_limit=330,worker_concurrency=1,timezone='Asia/Kolkata',broker_connection_retry_on_startup=True)
@celery.task(name='insight.ingest_pdf')
def ingest_pdf(document_id,tenant):
    # Never accept arbitrary filesystem paths from queue messages or the browser.
    path=ROOT/'.runtime/uploads'/f'{document_id}.pdf'
    return ingest_document(document_id,path,tenant)

from celery.schedules import crontab
celery.conf.beat_schedule={'daily-local-backup':{'task':'insight.backup_daily','schedule':crontab(hour=2,minute=0)}}
@celery.task(name='insight.backup_daily')
def backup_daily():
    from scripts.backup_product import backup
    return backup(verify=True)
