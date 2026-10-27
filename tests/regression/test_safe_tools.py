import pytest
from pydantic import ValidationError
from src.tools.safe_actions import SafeActions


def test_search_success_failure_and_argument_validation():
    tool=SafeActions(search_provider=lambda *a,**kw:[{'title':'Source','href':'https://example.com','body':'Result'}])
    assert tool.search_web('test')['results'][0]['title']=='Source'
    def offline(*a,**kw):raise OSError('offline')
    tool.search_provider=offline
    assert tool.search_web('test')['status']=='error'
    with pytest.raises(ValidationError):tool.search_web('test',99)


def test_email_is_only_a_draft():
    result=SafeActions().draft_email('test@example.com','Title','Body')
    assert result['status']=='drafted'
    assert 'not implemented' in result['message']


def test_unknown_and_system_tools_never_report_execution():
    tool=SafeActions()
    assert tool.launch_app('calc')['status']=='blocked'
    assert tool.dispatch('terminal',{'command':'rm -rf /'})['status']=='unavailable'
