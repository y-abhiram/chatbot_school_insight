"""Readable answers computed from permitted result rows, without another model guessing facts."""
from decimal import Decimal
from datetime import date,datetime,time
import sqlglot
from sqlglot import exp

def is_count_report(sql):
    """COUNT in a percentage denominator does not make the result a row count."""
    try:
        tree=sqlglot.parse_one(sql,read='postgres')
        if not isinstance(tree,exp.Select) or len(tree.expressions)!=1:return False
        expression=tree.expressions[0]
        while isinstance(expression,(exp.Alias,exp.Cast,exp.Paren)):
            expression=expression.this
        return isinstance(expression,exp.Count)
    except sqlglot.errors.ParseError:
        return False

def display(value):
    if value is None:return 'not recorded'
    if isinstance(value,(float,Decimal)):return f'{float(value):,.2f}'.rstrip('0').rstrip('.')
    if isinstance(value,(date,datetime,time)):return value.isoformat()
    return str(value)
def summarize_report(result,user):
    data=result.get('rows',[])
    if not data:return 'I couldn’t find matching records within your access and the filters you requested. This can mean the data has not been recorded yet. I won’t infer a zero, a fail, or an absence from missing data.'
    sql=result.get('sql','').lower();mine=user.role_name=='Student';lines=[]
    if len(data)==1 and len(data[0])==1:
        key,value=next(iter(data[0].items()))
        label=key.replace('_',' ')
        if value is None:return f'{label.capitalize()} has not been recorded for the requested filters. Missing data does not mean zero.'
        if is_count_report(sql):
            topic=next((label for table,label in [('insight"."students','student records'),('insight.students','student records'),('faculty','faculty records'),('homework','homework records'),('leave','leave requests')] if table in sql),'matching records')
            return f'There are {display(value)} {topic} visible to your account under the requested filters.'
        if any(part in key for part in ['attendance_pct','attendance_percentage','pct']):return f'Your recorded attendance is {display(value)}%.' if mine else f'The recorded attendance is {display(value)}%.'
        return f'{label.capitalize()}: {display(value)}.'
    if 'v_student_attendance_report' in sql:
        for row in data[:6]:
            pct=next((row[k] for k in ['attendance_pct','pct','attendance_percentage'] if k in row),None)
            if pct is not None:
                if mine:
                    label='Your attendance'
                elif row.get('student_name'):
                    label=display(row['student_name'])+"’s attendance"
                elif row.get('class_name'):
                    section='-'+display(row['section_name']) if row.get('section_name') else ''
                    label=display(row['class_name'])+section+' attendance'
                elif row.get('section_name'):
                    label='Section '+display(row['section_name'])+' attendance'
                else:
                    label='Recorded attendance'
                line=f'{label} is {display(pct)}%'
                if 'attended' in row and 'total_periods' in row:line+=f" ({display(row['attended'])} of {display(row['total_periods'])} recorded periods attended)"
                lines.append(line+'.')
        if lines:lines.append('Present and Late count as attended. This uses recorded periods, not an assumed full school year.')
    elif 'v_exam_report' in sql:
        lines.append('Here are your recorded exam results:' if mine else 'Here are the matching recorded exam results:')
        for row in data[:8]:
            label=display(row.get('subject_name','Result'))
            if not mine and row.get('student_name'):label=display(row['student_name'])+' · '+label
            if 'marks_obtained' in row:
                label+=': '+display(row['marks_obtained'])
                if row.get('max_marks') is not None:label+='/'+display(row['max_marks'])
                if row.get('grade') is not None:label+=' · Grade '+display(row['grade'])
                lines.append(label)
            else:lines.append(' · '.join(k.replace('_',' ')+': '+display(v) for k,v in row.items()))
    elif 'homework_submissions' in sql or 'assignment_submissions' in sql:
        lines.append('Here is the recorded submission status:')
        for row in data[:6]:
            label=display(row.get('title','Task'))
            if not mine and row.get('student_name'):label+=' · '+display(row['student_name'])
            if 'status' in row:label+=' — '+display(row['status'])
            if row.get('due_date'):label+=' · Due '+display(row['due_date'])
            lines.append(label)
    if not lines:
        lines.append('Here is what I found in your permitted records:')
        for row in data[:6]:
            selected=[(k,v) for k,v in row.items() if not k.endswith('_id')]
            lines.append(' · '.join(k.replace('_',' ').capitalize()+': '+display(v) for k,v in selected[:7]))
    if len(data)>8:lines.append(f'The report contains {len(data)} returned rows. Expand the records to explore the complete returned result.')
    if result.get('truncated'):lines.append(f"Only the first {result.get('limit',200)} rows are shown. Narrow your filters before drawing conclusions about the full dataset.")
    return '\n'.join(lines)
