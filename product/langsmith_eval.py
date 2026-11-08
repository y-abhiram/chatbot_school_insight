"""Explicit opt-in publication of reproducible acceptance results and per-case feedback."""
import os,uuid
from datetime import datetime,timezone
from langsmith import Client

def publish(report,client=None):
    if client is None and not os.getenv('LANGSMITH_API_KEY'):raise ValueError('Set LANGSMITH_API_KEY locally before publishing an evaluation.')
    client=client or Client(auto_batch_tracing=False)
    dataset_name='school-insight-acceptance-'+report['run_id'][:8]
    dataset=client.create_dataset(dataset_name,description='Original 17-question SQL/RAG/hybrid benchmark. Reference SQL executed independently; cited chunks checked against the manual.')
    example_ids={case['id']:str(uuid.uuid4()) for case in report['cases']}
    client.create_examples(dataset_id=dataset.id,examples=[{'id':example_ids[c['id']],'inputs':{'question':c['question'],'case_id':c['id']},'outputs':{'expected':c.get('expected'),'checks':c.get('checks',{})}} for c in report['cases']])
    project=os.getenv('LANGSMITH_PROJECT','school-insight-evaluation')+'-'+report['run_id'][:8]
    for case in report['cases']:
        run_id=uuid.uuid4();start=datetime.now(timezone.utc)
        client.create_run(name='acceptance-'+str(case['id']),inputs={'question':case['question']},run_type='chain',id=run_id,project_name=project,start_time=start,reference_example_id=example_ids[case['id']],extra={'metadata':{'provider':case.get('provider',report['provider']),'model':case.get('model',report['model']),'case_id':case['id']}})
        client.update_run(run_id,outputs=case.get('response',{'error_type':case.get('error_type')}),end_time=datetime.now(timezone.utc),reference_example_id=example_ids[case['id']])
        for key,value in case.get('checks',{}).items():client.create_feedback(run_id,key,score=1 if value else 0)
        client.create_feedback(run_id,'acceptance_pass',score=1 if case['passed'] else 0)
    return {'dataset':dataset_name,'dataset_id':str(dataset.id),'project':project,'cases':len(report['cases'])}
