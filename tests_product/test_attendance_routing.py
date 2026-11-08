"""Personal student attendance must agree with the same live dashboard records."""
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from product.agent import graph, validate, generate_sql, SQLProposal
from product.narrative import summarize_report
from product.personal_reports import personal_attendance_sql
from tests_product.test_security import identity


@pytest.mark.parametrize('question',[
    'What is my attendance percentage?', 'Show my attendance',
    'show my overall attendance percentage', 'Tell me my attendence percentage!',
])
def test_personal_attendance_uses_verified_student_plan(question):
    user=identity('stu_kiran')
    with patch('product.agent.structured') as model:
        response=graph.invoke({'question':question,'identity':user,'provider':'gemini','model':'test','history':[]})['response']
    assert response['source']=='SQL'
    assert response['report']['rows']==[{'student_name':'Kiran Patel','attendance_pct':100,'total_periods':2,'attended':2}]
    assert '100%' in response['answer'] and '2 of 2' in response['answer']
    assert 'faculty' not in response['answer'].lower()
    model.assert_not_called()


@pytest.mark.parametrize('question',[
    'What is my attendance percentage in October?', 'Show my attendance for Science',
    'Show my attendance by subject', 'How is my attendance calculated?',
    'Show everyone’s attendance', 'Change my attendance',
])
def test_filtered_process_and_write_requests_are_not_overridden(question):
    assert personal_attendance_sql(question,SimpleNamespace(role_name='Student')) is None


def test_wrong_staff_attendance_query_is_rejected_for_student():
    state={'identity':identity('stu_kiran'),'sql':'SELECT COUNT(*) AS total FROM insight.faculty_attendance'}
    assert 'student attendance' in validate(state)['error']


@pytest.mark.parametrize('sql',[
    'SELECT COUNT(*) AS total FROM insight.faculty',
    'SELECT COUNT(*) AS total FROM insight.attendance',
])
def test_percentage_question_cannot_execute_people_or_record_count(sql):
    state={'identity':identity('stu_kiran'),'question':'Show my attendance percentage for November','sql':sql}
    assert validate(state)['error']


def test_general_sql_prompt_receives_authenticated_role_and_profile():
    user=identity('stu_kiran')
    state={'identity':user,'provider':'gemini','model':'test','schema':{},'question':'Show my Science attendance','intent':{'question':'Show my Science attendance'}}
    with patch('product.agent.structured',return_value=SQLProposal(sql='SELECT status FROM insight.attendance')) as model:
        generate_sql(state)
    prompt=model.call_args.args[3]
    assert 'Kiran Patel' in prompt and '"role": "Student"' in prompt
    assert '"student_id": 3' in prompt


def test_percentage_with_count_denominator_is_not_described_as_record_count():
    report={'sql':'SELECT 100.0 * COUNT(*) / 2 AS attendance_pct FROM insight.attendance','rows':[{'attendance_pct':100}]}
    assert summarize_report(report,SimpleNamespace(role_name='Student'))=='Your recorded attendance is 100%.'


def test_null_aggregate_is_not_a_count_of_unrecorded_people():
    report={'sql':'SELECT AVG(marks_obtained) AS total_marks FROM insight.v_exam_report','rows':[{'total_marks':None}]}
    answer=summarize_report(report,SimpleNamespace(role_name='Student'))
    assert 'has not been recorded' in answer and 'There are' not in answer


def test_sum_alias_total_does_not_mean_count_of_records():
    report={'sql':'SELECT SUM(marks_obtained) AS total FROM insight.v_exam_report','rows':[{'total':250}]}
    assert summarize_report(report,SimpleNamespace(role_name='Student'))=='Total: 250.'


def test_dashboard_attendance_queries_bypass_report_cache():
    from product.api import overview
    from product.sql_engine import run_sql as real_run
    user=identity('stu_kiran')
    with patch('product.api.run_sql',side_effect=real_run) as runner:
        data=overview(user)
    assert data['attendance_pct']==100
    assert all(call.kwargs.get('use_cache') is False for call in runner.call_args_list)
