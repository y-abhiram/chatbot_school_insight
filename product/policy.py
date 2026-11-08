"""Role capabilities and onboarding come from the authenticated identity and verified manual."""
import re
from product.auth import public
from product.storage import rows
from product.sql_engine import run_sql

POLICIES={
 'Student':{
  'scope':'Your own student records and your section’s shared schedules',
  'can':['View your profile, courses and teachers','Check your attendance and subject marks','View homework, assignments and submission status','See your section timetable and class exam schedule','Read your published progress reports, notifications and leave status','Ask about school procedures or prepare a draft request'],
  'cannot':['View another student’s private records','Change attendance or marks','Submit homework or leave requests through this read-only chatbot','Approve leave, manage users or change school settings'],
  'questions':['What is my attendance percentage?','Show my marks by subject','What homework do I still need to submit?','Show my timetable','What exams are scheduled for my section?','What can I do as a student?'],
  'manual_pages':[15,16,17,18],
 },
 'Faculty':{
  'scope':'Your assigned subjects and sections, plus your own staff records',
  'can':['List students in your assigned sections','View student marks, attendance and submissions for your assigned subjects','View your assigned courses and own timetable','Check your own attendance, leave status and notifications','Ask about teaching procedures or draft a parent message'],
  'cannot':['Read unassigned students’ private academic records or school-wide private reports','View or approve students’ leave requests','Change marks, mark attendance or submit requests through this read-only chatbot','Approve leave or manage accounts'],
  'questions':['List students in my assigned sections','Show students’ marks for my subjects','Show attendance for my assigned subjects','Show my leave requests','Show my timetable','Show homework for my assigned subjects','What exams are scheduled for my assigned sections?','What can I do as a faculty member?'],
  'manual_pages':[12,13,14,15],
 },
 'Admin':{
  'scope':'School-wide reporting within this school workspace',
  'can':['Explore student and faculty reports across the school','Review attendance, exams, homework, timetables and pending leaves','Consult the school manual with page citations','Prepare summaries and drafts; manage application access in Team management'],
  'cannot':['Change source school records through the chatbot','Approve leave or edit marks using chat','Access another school’s records'],
  'questions':['Which students have attendance below 75%?','Show pending leave requests','Compare marks by subject','Explain the leave approval process','Show pending homework submissions','Show the timetable for Grade 9-A','What exams are scheduled?','What can I do as an administrator?'],
  'manual_pages':[8,9,10,11,12],
 }
}

def policy_for(user):
    from product.sources import source_for
    source=source_for(user.tenant_id)
    if source['adapter']=='school':return POLICIES[user.role_name]
    policy=(source.get('policies') or {}).get(user.role_name)
    if not policy:raise ValueError('No access policy is configured for this role.')
    return policy


def access_help(user):
    p=policy_for(user)
    return f"You’re signed in as {user.name}, with {user.role_name.lower()} access.\n\nI can help you:\n"+'\n'.join('• '+item for item in p['can'])+'\n\nThis chatbot is read-only. '+('Your private records stay separate from other students’ records.' if user.role_name=='Student' else 'Your access follows your authenticated school role.')+'\n\nWhat would you like help with?'

def welcome(user):
    p=policy_for(user)
    from product.sources import source_for
    source=source_for(user.tenant_id)
    if source['adapter']!='school':
        return {'identity':public(user),'greeting':f"Hi {user.name.split()[0]}, I’m your {source['name']} assistant. I can help with your permitted records and documentation. What would you like to know?",'profile':None,'scope':p['scope'],'can':p['can'],'cannot':p['cannot'],'suggestions':p['questions'],'manual_pages':p.get('manual_pages',[]),'read_only':True,'workspace':source['name']}
    profile=None
    if user.role_name=='Student':
        result=run_sql('SELECT student_name,class_name,section_name FROM insight.students',user)['rows']
        profile=result[0] if result else None
    greeting=f"Hi {user.name.split()[0]}, I’m your school assistant."
    if profile:greeting+=f" You’re signed in as a {profile['class_name']}–{profile['section_name']} student."
    if user.role_name=='Student':greeting+=' I can help you check your attendance, marks, homework and timetable, or explain a school process from the manual.'
    elif user.role_name=='Faculty':greeting+=' I can help you review your assigned classes and subjects, check your timetable, or prepare teaching-related drafts.'
    else:greeting+=' I can help you explore school reports, review pending requests, and understand the procedures in your manual.'
    greeting+=' What would you like help with today?'
    return {'identity':public(user),'greeting':greeting,'profile':profile,'scope':p['scope'],'can':p['can'],'cannot':p['cannot'],'suggestions':p['questions'],'manual_pages':p['manual_pages'],'read_only':True}

def deterministic_intent(question,user,previous_result=None):
    """Only capability/refusal/verified-summary routes are deterministic; new facts always use SQL/RAG."""
    from product.sources import source_for
    if source_for(user.tenant_id)['adapter']!='school':return None
    q=question.lower().strip()
    q=re.sub(r'[’‘]',"'",q)
    if re.search(r'\b(what (can|am|do) i (do|allowed|access|control)|what (can|do) (you|the (chatbot|assistant)) (do|help)|my (permissions|restrictions)|what.*my role|what.*student.*(control|access|do)|what.*faculty.*(access|do))\b',q):
        return {'kind':'answer','question':question,'documentation_question':'','answer':access_help(user)}
    if q.rstrip('!.? ') in ('hi','hello','hey','good morning','good evening'):
        return {'kind':'answer','question':question,'documentation_question':'','answer':welcome(user)['greeting']}
    if re.search(r'\b(passwords?|api[ _-]?keys?|access tokens?|database credentials)\b',q) and re.search(r'\b(show|give|reveal|list|tell|print)\b',q):
        return {'kind':'answer','question':question,'documentation_question':'','answer':'I can’t reveal passwords, API keys or access tokens. I can help you understand the documented sign-in or account support process.'}
    if re.search(r'\b(ignore|bypass|override|disable)\b.*\b(permissions|restrictions|access|rules|role)\b|\b(act as|pretend|make me|switch.*role|i am (an? )?admin|i am (an? )?administrator)\b',q):
        return {'kind':'answer','question':question,'documentation_question':'','answer':f'I can’t change your access through chat. You’re signed in with {user.role_name.lower()} access. I can help with records permitted to that account.'}
    # Refuse actual write requests; still allow questions about how a manual workflow works and requests for drafts.
    policy_question=bool(re.search(r'\b(how|explain|procedure|process|manual|draft|prepare|write a|help.*write|can i|can you|what.*do)\b',q))
    if not policy_question and re.search(r'^\s*(please\s+)?(approve|reject|delete|drop|update|edit|change|mark|submit|send|create a user|add a student|grant|set my)\b',q):
        return {'kind':'answer','question':question,'documentation_question':'','answer':'I can help you view records, explain the documented process, or prepare a draft. I can’t change school records, submit requests, or send messages. Please use the appropriate school workflow for that action.'}
    if user.role_name=='Faculty':
        school_records=bool(re.search(r'\b(attend[ae]nce|marks?|grades?|results?|submissions?)\b',q))
        leave=bool(re.search(r'\bleaves?\b',q))
        process=bool(re.search(r'\b(manual|procedure|process|policy|how)\b',q))
        if school_records and leave and not process:
            return {'kind':'clarification','question':question,'documentation_question':'','answer':'I can show student marks and attendance for your assigned subjects and sections, or your own leave requests. Student leave review and approval are administrator functions. Which would you like first: student marks, attendance, or your leave status?'}
        if re.search(r'\b(all|every|school[ -]wide)\b.*\bstudents?.*\b(private )?records?\b',q):
            return {'kind':'clarification','question':question,'documentation_question':'','answer':'I can list students in your assigned sections and show their marks, attendance or submissions for your assigned subjects. I can’t give unrestricted school-wide private records. Which record would you like to see?'}
        if leave and re.search(r'\b(students?|everyone|all applicants?)\b',q) and not process:
            return {'kind':'answer','question':question,'documentation_question':'','answer':'Student leave review is an administrator function in your school manual. With faculty access I can show your own leave status, or help explain the approval process. I can’t show other applicants’ private leave records.'}
    if user.role_name=='Student':
        documentation=bool(re.search(r'\b(manual|example|procedure|process|policy|how.*works|how.*work)\b',q))
        private_topic=bool(re.search(r'\b(marks?|grades?|results?|attendance|profile|progress|homework|submissions?|address|phone|password|records?|leaves?)\b',q))
        others=bool(re.search(r'\b(other students?|all students?|everyone|classmates?|other candidates?)\b|\bstudents? (with|below|above|have|has|attendance|marks)\b|\bwhich students?\b|\b(class|section|school)[ -]wide\b|\b(class|section|school) averages?\b|\baverages? .*(class|section|school)\b|\brank me (against|with)\b',q))
        if private_topic and not documentation:
            # Identify names internally; other students’ identity information is never sent to the model.
            names=rows("SELECT name,username FROM insight_app.identities WHERE tenant_id=:tenant AND role_name='Student' AND user_id<>:uid",{'tenant':user.tenant_id,'uid':user.user_id})
            for person in names:
                tokens=[person['username']]+[t for t in person['name'].lower().split() if len(t)>=3]
                if any(re.search(r'(?<!\w)'+re.escape(token.lower())+r'(?!\w)',q) for token in tokens):others=True
            if others:
                return {'kind':'answer','question':question,'documentation_question':'','answer':'I can help with your own attendance, marks, homework and progress reports, but I can’t show another student’s private records or class-wide personal reports. Would you like to see your own records instead?'}
    if re.search(r'\b(summari[sz]e|summary|key points|make (it|that) shorter|explain (this|that|the (previous|last)) report|what does (that|this) mean)\b',q) and not re.search(r'\b(manual|policy|procedure)\b',q):
        if previous_result:return {'kind':'summary','question':question,'documentation_question':'','answer':''}
        return {'kind':'clarification','question':question,'documentation_question':'','answer':'Which result would you like me to summarize? Ask for a report first, such as “Show my attendance”, and I can explain the verified result.'}
    return None


def clarification_prompt(user,question=''):
    """A model omission must never become an empty chat bubble."""
    from product.sources import source_for
    if source_for(user.tenant_id)['adapter']!='school':
        return 'Which permitted report or document would you like help with? For example: '+ '; '.join(policy_for(user)['questions'][:3])
    if user.role_name=='Faculty':
        return 'Would you like the student list for your assigned sections, marks or attendance for your assigned subjects, or your own leave status? I can help with those records using your faculty access.'
    if user.role_name=='Student':
        return 'Would you like help with your own attendance, marks, homework, timetable or leave status? I can also explain a school process from the manual.'
    return 'Which school report or process would you like help with—for example student attendance, exam marks, pending leave requests or a procedure from the manual?'


def recover_empty_intent(user,question):
    q=question.lower().strip()
    if user.role_name=='Faculty' and not re.search(r'\b(how|why|explain|manual|procedure|process|draft|write|change|update|approve|delete|submit|send|can i|can you)\b',q):
        if re.search(r'\b(attend[ae]nce|marks?|grades?|results?)\b|\blist (all )?students?\b|\bshow (all )?students?\b',q):
            return {'kind':'sql','question':question,'documentation_question':'','answer':''}
    return {'kind':'clarification','question':question,'documentation_question':'','answer':clarification_prompt(user,question)}
