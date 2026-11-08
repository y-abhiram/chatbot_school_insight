from unittest.mock import patch
from dataclasses import replace
import pytest
from product.agent import Intent,SQLProposal,ManualAnswer,graph,respond
from product.policy import welcome,deterministic_intent
from product.sql_engine import run_sql
from tests_product.test_security import identity

def state(question):return {'question':question,'identity':identity('fac_vijay'),'provider':'openai','model':'test','history':[]}

def test_faculty_onboarding_offers_permitted_student_reports():
    boot=welcome(identity('fac_vijay'))
    assert 'List students in my assigned sections' in boot['suggestions']
    assert any('marks' in q for q in boot['suggestions'])
    assert any('leave requests' in q for q in boot['suggestions'])
    assert any('students’ leave' in c for c in boot['cannot'])

@pytest.mark.parametrize('kind',['answer','clarification'])
@pytest.mark.parametrize('empty',['','   ','\n'])
def test_empty_model_reply_is_replaced_by_helpful_clarification(kind,empty):
    with patch('product.agent.structured',return_value=Intent(kind=kind,question='attendance',documentation_question='',answer=empty)):
        result=graph.invoke(state('I need help'))['response']
    assert result['answer'].strip()
    assert result['kind']=='clarification'
    assert 'assigned subjects' in result['answer'] and 'student list' in result['answer']

@pytest.mark.parametrize('question',['leaves and students marks','attendance and leave requests','Show all students records'])
def test_mixed_or_unrestricted_record_request_gets_clear_scope(question):
    with patch('product.agent.structured') as model,patch('product.agent.run_sql') as query:
        result=graph.invoke(state(question))['response']
    assert result['kind']=='clarification' and result['answer'].strip()
    assert 'assigned' in result['answer']
    model.assert_not_called();query.assert_not_called()

def test_student_leave_access_is_not_granted_to_faculty():
    intent=deterministic_intent('Show all students leave requests',identity('fac_vijay'))
    assert intent['kind']=='answer' and 'administrator' in intent['answer']
    assert run_sql('SELECT applicant,status FROM insight.leave_requests',identity('fac_vijay'))['rows']==[]

def test_faculty_own_leave_is_visible():
    data=run_sql('SELECT applicant,status FROM insight.leave_requests',identity('fac_anita'))['rows']
    assert data==[{'applicant':'Anita Sharma','status':'Rejected'}]

def test_faculty_report_queries_return_actual_scoped_data():
    user=identity('fac_vijay')
    students=run_sql('SELECT student_name FROM insight.students',user)['rows']
    assert {r['student_name'] for r in students}=={'Arjun Rao','Meera Iyer','Kiran Patel','Divya Nair'}
    marks=run_sql('SELECT student_name,subject_name,marks_obtained FROM insight.v_exam_report',user)['rows']
    assert {(r['student_name'],r['subject_name'],float(r['marks_obtained'])) for r in marks}=={('Kiran Patel','Science',76),('Divya Nair','Science',91)}
    attendance=run_sql('SELECT student_name,subject_name,status FROM insight.attendance',user)['rows']
    assert {(r['student_name'],r['subject_name'],r['status']) for r in attendance}=={('Arjun Rao','Science','Present'),('Meera Iyer','Science','Absent')}
    # The four-student sample happens to span both assigned sections; this is not unrestricted access.
    unassigned=replace(user,user_id=1,faculty_id=None)
    assert run_sql('SELECT student_name FROM insight.students',unassigned)['rows']==[]
    assert run_sql('SELECT student_name FROM insight.v_exam_report',unassigned)['rows']==[]

@pytest.mark.parametrize('question,sql',[('List all students','SELECT student_name,class_name,section_name FROM insight.students'),('attendence of all students','SELECT student_name,attendance_pct FROM insight.v_student_attendance_report'),('students marks','SELECT student_name,subject_name,marks_obtained FROM insight.v_exam_report')])
def test_clear_faculty_reports_execute_scoped_sql_with_scope_note(question,sql):
    outputs=[Intent(kind='sql',question=question,documentation_question='',answer=''),SQLProposal(sql=sql)]
    with patch('product.agent.structured',side_effect=outputs):result=graph.invoke(state(question))['response']
    assert result['report']['rows'] and result['answer'].strip()
    assert 'Scope:' in result['answer'] and 'assigned subjects' in result['answer']

def test_response_node_never_returns_blank_even_if_upstream_did():
    result=respond(state('help')|{'intent':{'kind':'clarification','answer':''},'started':0})['response']
    assert result['answer'].strip()


def test_blank_clarification_for_clear_attendance_request_recovers_sql():
    outputs=[Intent(kind='clarification',question='attendance',documentation_question='',answer=''),SQLProposal(sql='SELECT student_name,attendance_pct FROM insight.v_student_attendance_report')]
    with patch('product.agent.structured',side_effect=outputs):
        response=graph.invoke(state('attendence of all students'))['response']
    assert response['kind']=='sql' and response['report']['rows'] and response['answer'].strip()

def test_llm_context_skips_historical_blank_assistant_messages(monkeypatch):
    from product.llm import structured
    monkeypatch.setenv('OPENAI_API_KEY','test-key')
    output=Intent(kind='clarification',question='help',documentation_question='',answer='Which report would you like?')
    with patch('product.llm.ChatOpenAI') as factory:
        runnable=factory.return_value.with_structured_output.return_value
        runnable.invoke.return_value=output
        result=structured('openai','test-model',Intent,'Follow permissions.','students marks',[{'role':'assistant','content':' '},{'role':'user','content':'Show my assigned courses'}])
    assert result==output
    messages=runnable.invoke.call_args.args[0]
    assert all(m.content.strip() for m in messages)
    assert [m.type for m in messages]==['system','human','human']
