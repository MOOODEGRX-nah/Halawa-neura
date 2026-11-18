"""Opening well-known sites by name, site search engines and the «شغل/ادخل على» phrasings (fake desktop only)."""
from urllib.parse import parse_qs, urlsplit
import pytest
from tests.regression.test_application_followups import Applications
from tests.regression.test_chat_dispatch import application, request_id


def opened(desktop):
    urls = [str(c[-1]) for c in desktop.calls if c and c[0] == 'browser']
    return urls[-1] if urls else None


@pytest.mark.parametrize('text,url', [
    ('افتح جوجل', 'https://www.google.com/'), ('افتح موقع جوجل', 'https://www.google.com/'), ('افتح لي فيسبوك', 'https://www.facebook.com/'),
    ('هل يمكنك ان تفتح لي موقع تويتر', 'https://x.com/'), ('افتح موقع الجزيرة', 'https://www.aljazeera.net/'), ('افتح ويكيبيديا', 'https://www.wikipedia.org/'),
    ('افتح gmail', 'https://mail.google.com/'), ('افتح خرائط جوجل', 'https://www.google.com/maps'), ('افتح شات جي بي تي', 'https://chatgpt.com/'),
    ('شغل لي يوتيوب', 'https://www.youtube.com/'), ('ادخل على جوجل', 'https://www.google.com/'), ('خذني الى ويكيبيديا', 'https://www.wikipedia.org/'),
    ('افتح موقع ديسكورد', 'https://discord.com/app'),
])
def test_known_site_names_open_their_fixed_address(system, text, url):
    app, desktop, dispatch = application(system, Applications())
    result = dispatch.dispatch(text, request_id(), session_id='chat_a')
    assert result['kind'] == 'action' and result['skill'] == 'open_website' and opened(desktop) == url
    app.state.project_store.close()


@pytest.mark.parametrize('text,app_id', [('افتح ديسكورد', 'discord.desktop'), ('افتح ستيم', 'steam.desktop'), ('شغل steam', 'steam.desktop')])
def test_installed_app_wins_over_its_website(system, text, app_id):
    apps = Applications(); apps.apps = apps.apps + [{'id': 'steam.desktop', 'name': 'Steam'}, {'id': 'google-chrome.desktop', 'name': 'Google Chrome'}]
    app, desktop, dispatch = application(system, apps)
    result = dispatch.dispatch(text, request_id(), session_id='chat_a')
    assert result['skill'] == 'open_application' and desktop.calls[-1][1] == app_id
    app.state.project_store.close()


def test_site_name_never_partially_matches_an_app(system):
    apps = Applications(); apps.apps = apps.apps + [{'id': 'google-chrome.desktop', 'name': 'Google Chrome'}]
    app, desktop, dispatch = application(system, apps)
    assert dispatch.dispatch('افتح جوجل', request_id(), session_id='chat_a')['skill'] == 'open_website'
    app.state.project_store.close()


@pytest.mark.parametrize('text,host,param,query', [
    ('ابحث في جوجل عن سعر الذهب', 'www.google.com', 'q', 'سعر الذهب'),
    ('ابحث في ويكيبيديا عن ابن سينا', 'ar.wikipedia.org', 'search', 'ابن سينا'),
    ('search on amazon for headphones', 'www.amazon.com', 'k', 'headphones'),
])
def test_site_search_engines_encode_only_the_query(system, text, host, param, query):
    app, desktop, dispatch = application(system, Applications())
    result = dispatch.dispatch(text, request_id(), session_id='chat_a')
    url = urlsplit(opened(desktop))
    assert result['skill'] == 'open_website' and url.scheme == 'https' and url.hostname == host and parse_qs(url.query)[param] == [query]
    app.state.project_store.close()


def test_unknown_explicit_site_searches_instead_of_guessing(system):
    app, desktop, dispatch = application(system, Applications())
    result = dispatch.dispatch('افتح موقع مدرستي', request_id(), session_id='chat_a')
    assert result['skill'] == 'search_web' and 'بدل تخمين' in result['result']['message']
    app.state.project_store.close()


def test_unknown_bare_name_offers_search_and_opens_nothing(system):
    app, desktop, dispatch = application(system, Applications())
    result = dispatch.dispatch('افتح زبطاطا', request_id(), session_id='chat_a')
    assert result['kind'] == 'clarification' and len(result['choices']) == 1 and not desktop.calls
    app.state.project_store.close()


@pytest.mark.parametrize('text', ['شغل الكود', 'شغل موسيقى هادئة', 'لا تفتح جوجل', 'كيف افتح جوجل؟', '"افتح جوجل"', 'ابحث في جوجل'])
def test_non_actions_and_missing_queries_open_nothing(system, text):
    app, desktop, dispatch = application(system, Applications())
    result = dispatch.dispatch(text, request_id(), session_id='chat_a')
    assert not desktop.calls and (result['kind'] == 'chat' or result['result']['status'] == 'error')
    app.state.project_store.close()


@pytest.mark.parametrize('text', ['افتح ملف', 'افتح مجلد', 'افتح موقع', 'افتح تطبيق', 'open a file', 'افتح شي'])
def test_bare_generic_nouns_ask_instead_of_searching(system, text):
    app, desktop, dispatch = application(system, Applications())
    result = dispatch.dispatch(text, request_id(), session_id='chat_a')
    assert not desktop.calls and result.get('skill') != 'search_web'
    assert not any('ابحث في الويب' in c['label'] for c in result.get('choices', []))
    app.state.project_store.close()
