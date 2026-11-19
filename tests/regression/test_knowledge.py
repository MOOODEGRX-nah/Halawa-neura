"""N038: local knowledge base — chunk, embed, retrieve with citations, delete for good."""
import hashlib
import math
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from src.core.assistant import Assistant
from src.core.assistant_intents import parse
from src.core.knowledge import KnowledgeBase, KnowledgeError, chunks, to_text
from tests.regression.test_chat_dispatch import application

NOW = datetime(2026, 11, 19, 14, 30, tzinfo=ZoneInfo('Asia/Riyadh'))


class WordEmbedder:
    """Deterministic bag-of-words vectors: shared words => higher cosine similarity."""
    available = True
    def embed(self, texts, kind):
        out = []
        for text in texts:
            vector = [0.0] * 64
            for word in text.replace('search_query:', '').replace('search_document:', '').split():
                vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % 64] += 1
            out.append(vector)
        return out


def kb(tmp_path):
    return KnowledgeBase(tmp_path, WordEmbedder())


def test_chunking_keeps_overlap_and_bounds():
    text = '\n\n'.join('فقرة رقم %d تشرح موضوعًا محددًا بتفصيل كافٍ للقراءة والفهم.' % i for i in range(80))
    parts = chunks(text)
    assert len(parts) > 3 and all(len(p) <= 1100 for p in parts)


def test_add_search_delete(tmp_path):
    base = kb(tmp_path)
    first = base.add('عقد الإيجار', 'مدة عقد الإيجار سنة واحدة تبدأ من شهر يناير والإيجار الشهري ثلاثة آلاف ريال يدفع مقدمًا.\n\nالتأمين ألف ريال.')
    base.add('وصفة', 'الكبسة تحتاج أرز بسمتي ودجاج وبهارات مشكلة وتطبخ على نار هادئة.')
    assert base.add('نسخة', 'مدة عقد الإيجار سنة واحدة تبدأ من شهر يناير والإيجار الشهري ثلاثة آلاف ريال يدفع مقدمًا.\n\nالتأمين ألف ريال.')['duplicate']
    hits = base.search('كم الإيجار الشهري في عقد الإيجار')
    assert hits[0]['title'] == 'عقد الإيجار'
    base.delete(first['id'])
    assert all(h['title'] != 'عقد الإيجار' for h in base.search('كم الإيجار الشهري في عقد الإيجار'))
    assert (tmp_path / 'knowledge.sqlite3').stat().st_mode & 0o777 == 0o600


def test_unsupported_and_empty_files():
    with pytest.raises(KnowledgeError):
        to_text('report.pdf', b'%PDF-1.7')
    with pytest.raises(KnowledgeError):
        to_text('a.txt', b'short')
    assert 'مرحبا' in to_text('page.html', '<html><body><p>مرحبا بك في الصفحة التجريبية الطويلة بما يكفي.</p><script>x()</script></body></html>')


def test_assistant_answers_from_files_with_citations_and_refuses_when_unrelated(tmp_path):
    base = kb(tmp_path)
    base.add('عقد الإيجار', 'مدة عقد الإيجار سنة واحدة والإيجار الشهري ثلاثة آلاف ريال يدفع مقدمًا في بداية كل شهر.')
    seen = []
    assistant = Assistant(tmp_path / 'a', knowledge=base, summarizer=lambda m: seen.append(m) or {'choices': [{'message': {'content': 'الإيجار ثلاثة آلاف ريال [1].'}}]})
    intent = parse('من ملفاتي: كم الإيجار الشهري في عقد الإيجار؟', NOW)
    assert intent.name == 'knowledge.ask'
    result = assistant.handle(intent)
    assert '[1] عقد الإيجار' in result['message'] and 'ليست تعليمات' in seen[0][0]['content']
    unrelated = assistant.handle(parse('من ملفاتي: ما عاصمة اليابان', NOW))
    assert unrelated['result']['status'] == 'unavailable' and 'لن أخمّن' in unrelated['message']


def test_api_upload_list_delete(system):
    app, desktop, dispatch = application(system)
    app.state.assistant.knowledge = KnowledgeBase(system.settings.data_dir / 'kb', WordEmbedder())
    headers = {'X-Neura-Token': 'test-token'}
    with TestClient(app, base_url='http://127.0.0.1') as client:
        assert client.get('/assistant/knowledge').status_code == 403
        added = client.post('/assistant/knowledge', json={'filename': 'notes.md', 'text': '# ملاحظات\n\nاجتماع الفريق يوم الأحد الساعة العاشرة صباحًا في المكتب.'}, headers=headers).json()
        assert added['chunks'] >= 1
        assert client.post('/assistant/knowledge', json={'filename': 'x.pdf', 'text': 'abc'}, headers=headers).status_code == 400
        assert [d['title'] for d in client.get('/assistant/knowledge', headers=headers).json()['documents']] == ['notes.md']
        assert client.delete('/assistant/knowledge/' + added['id'], headers=headers).status_code == 200
    app.state.project_store.close()


def test_article_from_files_is_cited(tmp_path):
    base = kb(tmp_path)
    base.add('ملاحظات الرحلة', 'زرنا العلا في الشتاء ورأينا مدائن صالح والطقس كان باردًا ليلًا ومعتدلًا نهارًا.')
    seen = []
    assistant = Assistant(tmp_path / 'a', knowledge=base, summarizer=lambda m: seen.append(m) or {'choices': [{'message': {'content': '# رحلة العلا\nزرنا العلا [1].'}}]})
    intent = parse('اكتب مقالا من ملاحظاتي عن رحلة العلا', NOW)
    assert intent.name == 'knowledge.article' and intent.args['topic'] == 'رحلة العلا'
    result = assistant.handle(intent)
    assert '# رحلة العلا' in result['message'] and '[1] ملاحظات الرحلة' in result['message'] and 'ليست تعليمات' in seen[0][0]['content']
