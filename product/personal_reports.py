"""Verified report plans for unfiltered personal attendance questions."""
import re


def personal_attendance_sql(question, user):
    if user.role_name != 'Student':
        return None
    normalized = re.sub(r'[?.!]+$', '', question.lower().strip()).strip()
    if not re.fullmatch(
        r'(?:(?:what is|what\'s|show|show me|tell me|give me|check)\s+)?'
        r'my\s+(?:(?:overall|recorded)\s+)?attend[ae]nce'
        r'(?:\s+(?:percentage|percent|summary))?(?:\s+please)?', normalized
    ):
        return None
    # These views enforce the authenticated identity at execution time. No sample
    # names, dates, percentages or user-supplied identities are inserted here.
    return ('SELECT student_name,attendance_pct,total_periods,attended '
            'FROM insight.v_student_attendance_report ORDER BY student_name')
