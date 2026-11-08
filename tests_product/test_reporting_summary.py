"""Report summaries preserve the identity of each comparison group."""
from types import SimpleNamespace
from product.narrative import summarize_report


def test_section_attendance_comparison_labels_each_result():
    result = {
        'sql': 'SELECT class_name, section_name, attendance_pct FROM insight.v_student_attendance_report',
        'rows': [
            {'class_name': 'Grade 10', 'section_name': 'A', 'attendance_pct': 100},
            {'class_name': 'Grade 9', 'section_name': 'A', 'attendance_pct': 50},
        ],
    }
    answer = summarize_report(result, SimpleNamespace(role_name='Admin'))
    assert 'Grade 10-A attendance is 100%' in answer
    assert 'Grade 9-A attendance is 50%' in answer
    assert 'Recorded’s' not in answer


def test_grouped_attendance_without_names_uses_neutral_label():
    result = {'sql': 'SELECT attendance_pct, total_periods FROM insight.v_student_attendance_report',
              'rows': [{'attendance_pct': 75, 'total_periods': 4}]}
    answer = summarize_report(result, SimpleNamespace(role_name='Admin'))
    assert 'Recorded attendance is 75%' in answer
