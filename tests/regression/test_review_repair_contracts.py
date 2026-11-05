"""Recorded native failures; controlled contract tests, not inference evidence."""
import json
from pathlib import Path
import threading,time
import pytest
from src.core.repair_targets import RepairTargets,RepairTarget,apply_spans
from src.core.project_files import ProjectError
from src.core.bounded_edits import apply_exact
from src.core.feature_intent import feature_intents,required_features
from src.core.required_interactions import compile_theme,needs_theme,theme_contract
from src.core.edit_preservation import require_preserved
from src.core.project_store import digest

FIXTURES=Path(__file__).parents[1]/'fixtures/ax07_review'


def test_target_ids_are_bound_to_candidate_revision_span_and_all_file_hashes():
    line='same'*150+'\n';files={'index.html':line+line,'other.js':'let a=1;'};targets=RepairTargets(files,7)
    first=next(iter(targets.targets));edit={'target_id':first,'after':'new\n'}
    assert targets.apply(files,[edit],7)['index.html']=='new\n'+line
    assert files['index.html']==line+line
    for altered,revision in [({**files,'other.js':'let a=2;'},7),(files,8),({**files,'index.html':'changed\nsame\n'},7)]:
        with pytest.raises(ProjectError):targets.apply(altered,[edit],revision)
    with pytest.raises(ProjectError):RepairTargets(files,8).apply(files,[edit],8)
    with pytest.raises(ProjectError):targets.apply(files,[edit,edit],7)
    with pytest.raises(ProjectError):targets.apply(files,[{'target_id':'t_'+'0'*16,'after':'x'}],7)


def test_overlaps_and_sequential_anchor_chaining_are_rejected_before_changes():
    source={'a.txt':'abcdef'}
    for edits in [[(0,3,'X'),(2,5,'Y')],[(0,6,'X'),(1,2,'Y')],[(0,3,'X'),(0,3,'Y')]]:
        with pytest.raises(ProjectError):apply_spans(source,{'a.txt':edits})
        assert source=={'a.txt':'abcdef'}
    with pytest.raises(ProjectError):apply_exact(source,'a.txt',[{'before':'abc','after':'new'},{'before':'new','after':'Q'}],'abcdef')
    assert apply_spans(source,{'a.txt':[(0,3,'X'),(3,6,'Y')]})=={'a.txt':'XY'}


@pytest.mark.parametrize('text', ['أضف الوضع الداكن إلى هذا المشروع','هل يمكنك أن تضيف الوضع الداكن؟','ممكن تضيف لي الوضع الليلي','أريد أن يدعم الموقع الوضع الداكن','الموقع يحتاج الوضع الداكن','فعل المظهر الداكن','Please enable dark mode','I want this website to support dark mode'])
def test_natural_user_intent_shared_with_dispatch(text):
    from src.core.chat_dispatch import active_edit_intent
    assert required_features([],text)=={'theme':True}
    assert active_edit_intent(text)
    assert needs_theme([],text)


@pytest.mark.parametrize('text',['لا تضف الوضع الداكن','ما ابغى الوضع الداكن','كيف أضيف الوضع الداكن؟','اشرح dark mode','"أضف الوضع الداكن"','مثال: أريد الوضع الداكن','```html\nأضف الوضع الداكن\n```','هل الوضع الداكن موجود؟'])
def test_quoted_negative_explanatory_or_ambiguous_text_cannot_require_feature(text):
    assert not feature_intents(text)


def test_only_user_origin_can_require_features_and_negation_does_not_delete_history():
    history=[{'origin':'user_request','text':'ممكن تضيف لي الوضع الليلي؟'},{'origin':'model','text':'add login'}]
    assert required_features(history,'لا تضف الوضع الداكن')=={'theme':True}
    assert required_features(history,'احذف الوضع الداكن')=={}
    assert required_features(history,'لا تحذف الوضع الداكن')=={'theme':True}
    assert required_features([], 'هل يمكنك أن تضيف زراً لتسجيل الدخول؟')=={'login':True}


@pytest.mark.parametrize('name',['preserve-1','preserve-2','preserve-3'])
def test_recorded_failures_are_full_fixtures_and_compilation_preserves_base(name):
    data=json.loads((FIXTURES/(name+'.json')).read_text());base=data['base']
    assert data['error'] and 'theme' in data['error']
    targets=RepairTargets(data['rejected'],2)
    # Every original candidate byte is available, even duplicate source lines.
    assert {v['path']:''.join(s['source'] for s in v['spans']) for v in targets.source}==data['rejected']
    candidate,contract=compile_theme(base,'index.html')
    assert contract['base_sha256']==digest(base['index.html'])
    assert contract['compiled_sha256']==digest(candidate['index.html'])
    assert require_preserved(base,candidate,data['request'])['status']=='passed'
    assert 'localStorage' not in candidate['index.html'][len(base['index.html']):]
    with pytest.raises(ProjectError):compile_theme(candidate,'index.html')


def test_repair_schema_only_permits_server_issued_targets(system):
    from src.core.invoice_orchestrator import InvoiceOrchestrator,ProjectRequest
    files={'index.html':'<p>Original</p>\n'};targets=RepairTargets(files)
    system.backend.text=json.dumps({'edits':[{'target_id':next(iter(targets.targets)),'after':'<p>Corrected</p>\n'}]})
    result,receipt=InvoiceOrchestrator(system).repair_candidate(files,ProjectRequest(user_request='Fix text',requirements=['Keep controls']),'fixture',{},cancel=threading.Event(),deadline=time.monotonic()+3,max_tokens=256)
    assert result['index.html']=='<p>Corrected</p>\n'
    assert receipt['repair_targets']==targets.manifest()
    assert system.backend.calls[-1]['response_format']['schema']['$defs']['CandidatePatch']['properties']['target_id']['enum']==list(targets.targets)
