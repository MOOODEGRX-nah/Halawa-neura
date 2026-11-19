"""N048: researcher/writer/reviewer stages on one model, traceable to sources, with measured cost."""
import json

from src.core.research_roles import clean_citations, staged_report

SOURCES = [{'title': 'مكة', 'text': 'مكة مدينة في الحجاز.', 'language': 'ar'}, {'title': 'الكعبة', 'text': 'الكعبة في المسجد الحرام.', 'language': 'ar'}]


def scripted(*replies):
    calls = []
    def complete(messages):
        calls.append(messages)
        return {'choices': [{'message': {'content': replies[len(calls) - 1]}}]}
    return complete, calls


def test_reviewer_issues_trigger_one_revision_and_bad_citations_are_dropped():
    complete, calls = scripted('مكة في الحجاز [1]. عدد سكانها 9 ملايين [2]. وفيها برج [7].',
                               json.dumps({'verdict': 'fix', 'issues': [{'quote': 'عدد سكانها 9 ملايين', 'problem': 'غير موجود في المصادر'}]}),
                               'مكة في الحجاز [1]. الكعبة في المسجد الحرام [2]. [9]')
    result, trace, count = staged_report('مكة', SOURCES, complete)
    assert count == 3 and [t['role'] for t in trace] == ['researcher', 'writer', 'reviewer', 'reviser', 'citations']
    assert result['verdict'] == 'fixed' and '9 ملايين' not in result['report'] and '[9]' not in result['report'] and result['dropped_citations'] == 1
    assert 'غير موجود في المصادر' in calls[2][1]['content'] and 'المصادر' in calls[1][1]['content']


def test_ok_review_keeps_draft_with_two_calls_and_unreadable_review_is_reported():
    complete, _ = scripted('تقرير [1].', '{"verdict":"ok"}')
    result, trace, count = staged_report('مكة', SOURCES, complete)
    assert count == 2 and result['verdict'] == 'ok' and result['report'] == 'تقرير [1].'
    complete, _ = scripted('تقرير [2].', 'لا أعرف')
    result, _, count = staged_report('مكة', SOURCES, complete)
    assert count == 2 and result['verdict'] == 'unavailable'
    assert all('ms' in t for t in trace)


def test_clean_citations():
    assert clean_citations('أ [1] ب [3] ج [0]', 2) == ('أ [1] ب  ج ', 2)
