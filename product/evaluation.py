"""Independent ground-truth checks for the original 17-question acceptance dataset."""
import json,math
from decimal import Decimal
from datetime import date,datetime,time
from pathlib import Path
from product.config import ROOT

CASES=[
 {'id':1,'kind':'sql','question':'How many students are there?','reference_sql':'SELECT COUNT(*) AS total FROM school.students'},
 {'id':2,'kind':'sql','question':'How many users are registered?','reference_sql':'SELECT COUNT(*) AS total FROM school.users'},
 {'id':3,'kind':'sql','question':'How many faculty members are there?','reference_sql':'SELECT COUNT(*) AS total FROM school.faculty'},
 {'id':4,'kind':'sql','question':'List all students and their sections.','reference_sql':"SELECT u.first_name||' '||u.last_name AS student_name,c.class_name,sec.section_name FROM school.students s JOIN school.users u USING(user_id) JOIN school.sections sec USING(section_id) JOIN school.classes c USING(class_id)",'columns':['student_name','class_name','section_name']},
 {'id':5,'kind':'sql','question':'Who has the lowest attendance?','reference_sql':'SELECT student_name,attendance_pct FROM school.v_student_attendance_report ORDER BY attendance_pct LIMIT 1','columns':['student_name','attendance_pct']},
 {'id':6,'kind':'sql','question':'Show students below 75% attendance.','reference_sql':'SELECT student_name,attendance_pct FROM school.v_student_attendance_report WHERE attendance_pct<75','columns':['student_name','attendance_pct']},
 {'id':7,'kind':'sql','question':'Show pending leave requests.','reference_sql':'SELECT applicant,type_name,from_date,to_date FROM school.v_pending_leaves','columns':['applicant','type_name','from_date','to_date']},
 {'id':8,'kind':'sql','question':'Show the timetable for Grade 9-A.','reference_sql':"SELECT day_of_week,period_no,subject_name FROM school.v_timetable WHERE section='Grade 9-A'",'columns':['day_of_week','period_no','subject_name']},
 {'id':9,'kind':'sql','question':"Show Arjun's attendance.",'reference_sql':"SELECT student_name,attendance_pct,total_periods,attended FROM school.v_student_attendance_report WHERE student_name='Arjun Rao'",'columns':['student_name','attendance_pct','total_periods','attended']},
 {'id':10,'kind':'sql','question':"Show Kiran's examination results.",'reference_sql':"SELECT student_name,subject_name,marks_obtained,grade FROM school.v_exam_report WHERE student_name='Kiran Patel'",'columns':['student_name','subject_name','marks_obtained','grade']},
 {'id':11,'kind':'sql','question':'How many students passed and failed Mathematics?','reference_sql':"SELECT SUM(CASE WHEN result='Pass' THEN 1 ELSE 0 END) AS passed,SUM(CASE WHEN result='Fail' THEN 1 ELSE 0 END) AS failed FROM school.v_exam_report WHERE subject_name='Mathematics'",'columns':['passed','failed']},
 {'id':12,'kind':'sql','question':'Which students have pending homework?','reference_sql':"SELECT u.first_name||' '||u.last_name AS student_name,h.title FROM school.homework_submissions hs JOIN school.students s USING(student_id) JOIN school.users u USING(user_id) JOIN school.homework h USING(homework_id) WHERE hs.status='Pending'",'columns':['student_name','title']},
 {'id':13,'kind':'rag','question':'Explain the leave approval process.','pages':[10,15,18],'terms':['pending','admin','approved','rejected']},
 {'id':14,'kind':'rag','question':'What are the allowed student attendance statuses?','pages':[13],'terms':['present','absent','late','excused']},
 {'id':15,'kind':'rag','question':'How are progress reports generated?','pages':[11,12],'terms':['marks','percentage','grade','rank','publish']},
 {'id':16,'kind':'sql','question':'Compare attendance between the two sections.','reference_sql':'SELECT class_name,section_name,ROUND(100.0*SUM(attended)/SUM(total_periods),2) AS attendance_pct FROM school.v_student_attendance_report GROUP BY class_name,section_name','columns':['class_name','section_name','attendance_pct']},
 {'id':17,'kind':'hybrid','question':'Explain the result of the students with low attendance using the manual.','reference_sql':'SELECT student_name,attendance_pct FROM school.v_student_attendance_report WHERE attendance_pct<75','columns':['student_name','attendance_pct'],'pages':[9,10,13,16,19],'terms':['present','late','period']},
]

def serial(value):
    if isinstance(value,Decimal):return float(value)
    if isinstance(value,(date,datetime,time)):return value.isoformat()
    if isinstance(value,dict):return {k:serial(v) for k,v in value.items()}
    if isinstance(value,(tuple,list)):return [serial(v) for v in value]
    return value

def compare_rows(actual,expected,columns=None):
    """Compare result values independently of row order; require the requested projection."""
    if len(actual)!=len(expected):return False
    if not expected:return True
    if len(expected)==1 and len(expected[0])==1 and len(actual[0])==1:
        return list(serial(actual[0]).values())==list(serial(expected[0]).values())
    def signature(row):
        values=serial(row)
        if columns:
            if not all(c in values for c in columns):return None
            values={c:values[c] for c in columns}
        return json.dumps(values,sort_keys=True)
    left=[signature(row) for row in actual];right=[signature(row) for row in expected]
    return None not in left and sorted(left)==sorted(right)

def verify(case,response,expected,connection):
    checks={'intent':response.get('kind')==case['kind'],'nonempty_answer':bool(response.get('answer','').strip())}
    if 'reference_sql' in case:
        checks['sql_result']=bool(response.get('report')) and compare_rows(response['report']['rows'],expected,case.get('columns'))
    if case.get('pages'):
        doc=response.get('documentation') or {};citations=doc.get('citations') or []
        checks['citations_present']=bool(citations)
        checks['retrieval_relevance']=bool(set(c.get('page') for c in citations)&set(case['pages']))
        valid=True
        for citation in citations:
            from sqlalchemy import text
            row=connection.execute(text('SELECT page,content FROM insight_app.chunks WHERE id=:id'),{'id':citation['id']}).mappings().first()
            if not row or row['page']!=citation['page'] or row['content']!=citation['excerpt']:valid=False
        checks['citation_integrity']=valid and bool(citations)
        text=(response.get('answer','')+' '+doc.get('answer','')).lower()
        checks['required_concepts']=all(term in text for term in case['terms'])
    return checks
