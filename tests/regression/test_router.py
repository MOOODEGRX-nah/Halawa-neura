import pytest

@pytest.mark.parametrize('text,intent', [('مرحبا','daily'),('happy day','daily'),('اكتب دالة Python','coder'),('اقرأ الصورة','vision'),('تحليل شامل','expert'),('ابحث عن الطقس','tool_search')])
def test_intent(system,text,intent):
    assert system.router.detect_intent(text)==intent


def test_real_tier_model(system):
    result=system.router.route('اكتب دالة Python')
    assert len(result)==4
    assert result[:2]==('coder','qwen3.5-9b-claude-distilled-q4')


def test_manual_tier(system):
    assert system.router.route('اكتب دالة Python',requested_tier='fast')[0]=='fast'


def test_unknown_tier_rejected(system):
    with pytest.raises(ValueError,match='Unknown tier'):
        system.router.route('hello',requested_tier='root')


def test_fallback_is_rechecked(system):
    system.residency.models_config['models']['qwen3.5-9b-claude-distilled-q4']['enabled']=False
    selected=system.router.route('تحليل شامل')
    assert selected[0]=='daily' and 'Fallback' in selected[2]
    system.residency.models_config['models']['qwen3.5-9b-q4']['enabled']=False
    selected=system.router.route('تحليل شامل')
    assert selected[0]=='expert'
    assert system.residency.can_load(selected[1])[0] is False


def test_explicit_selection_never_falls_back(system):
    system.residency.models_config['models']['qwen3.5-9b-claude-distilled-q4']['enabled']=False
    assert system.router.route('hello',requested_tier='expert')[0]=='expert'


def test_conflicting_model(system):
    with pytest.raises(ValueError,match='Conflicting'):
        system.router.route('hello',requested_tier='fast',requested_model='qwen3.5-9b-q4')


def test_image_must_use_vision(system):
    assert system.router.route('hello',has_image=True)[0]=='vision'
    with pytest.raises(ValueError,match='VISION'):
        system.router.route('hello',has_image=True,requested_tier='fast')
