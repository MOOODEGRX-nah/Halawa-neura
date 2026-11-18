"""Ordinary chat must never leave an unsupported 'files were updated' claim uncorrected.

Observed 2026-11-16 (web-services-2): DAILY replied «تم تحديث الكود في index.html و script.js …
الحالة: تم التحديث بنجاح» while no job ran and revision 1 stayed unchanged.
"""
import json
import pytest
from src.core.chat_claims import unsupported_action_claim, NOTICE
from tests.regression.test_api import run

OBSERVED = ('أُضيفت فئة "النقل" مع خدمتي "تاكسي" و "شركة نقل" إلى البيانات التجريبية. تم تحديث الكود في index.html و script.js '
            'لتضمين هذه الفئة والخدمتين الجديدتين، مع الحفاظ على هيكلية التصفية الحالية.ملفات محدثة: index.html, script.jsالحالة: تم التحديث بنجاح.')


@pytest.mark.parametrize('text', [OBSERVED, 'لقد عدلت ملف style.css', 'قمت بإضافة زر في الصفحة', 'تمت إضافة القسم إلى الموقع',
                                  'I have updated index.html to add a dark mode.', 'The file has been saved.', "I've added the button to the project."])
def test_completed_file_or_project_claims_are_detected(text):
    assert unsupported_action_claim(text)


@pytest.mark.parametrize('text', ['يمكنك تحديث الملف index.html بإضافة هذا السطر', 'هذا هو الكود المحدث لملف style.css:', 'Here is the updated code for index.html',
                                  'تم تحديث معلوماتي حتى 2024', 'You can update the file by adding this line.', 'I recommend that you edit the file', 'لتعديل المشروع اكتب عدّل هذا المشروع'])
def test_advice_code_and_unrelated_statements_are_not_flagged(text):
    assert unsupported_action_claim(text) is None


def test_streamed_fabricated_edit_gets_truthful_notice_in_the_same_reply(system, messages):
    system.backend.text = OBSERVED
    async def check(client, app):
        response = await client.post('/v1/chat/completions', json={'messages': messages, 'stream': True})
        events = [line[6:] for line in response.text.splitlines() if line.startswith('data: ')]
        assert events[-1] == '[DONE]'
        chunks = [json.loads(e) for e in events[:-1]]
        text = ''.join(c['choices'][0]['delta'].get('content', '') for c in chunks)
        assert text == OBSERVED + NOTICE and chunks[-1]['neura_claim_guard']['notice_appended']
    run(system, check)


def test_non_stream_fabricated_edit_gets_notice_and_ordinary_answers_are_untouched(system, messages):
    system.backend.text = 'I have updated index.html and saved the project.'
    async def check(client, app):
        result = (await client.post('/v1/chat/completions', json={'messages': messages})).json()
        assert result['choices'][0]['message']['content'].endswith(NOTICE) and result['neura_claim_guard']['unsupported_action_claim']
        system.backend.text = 'answer'
        plain = (await client.post('/v1/chat/completions', json={'messages': messages})).json()
        assert plain['choices'][0]['message']['content'] == 'answer' and 'neura_claim_guard' not in plain
    run(system, check)
