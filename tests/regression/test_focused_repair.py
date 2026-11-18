"""Bounded repair of an edit candidate: only the candidate's own changes enter the prompt.

Derived from the recorded RX 580 7B failure (protected-large-1): a large saved style.css made
the full-candidate repair prompt exceed 4096 tokens, and the browser reported only that the
theme 'did not change' while the real cause was an unreachable toggle.
"""
import json
import threading
import time
import pytest
from src.core.project_files import ProjectError
from src.core.repair_targets import RepairTargets, changed_regions

ARCHIVE=''.join(f'/* Archived style note {i:03d}: retained source context, never discarded. */\n' for i in range(140))
BEFORE={'index.html':'<!doctype html>\n<html>\n<head>\n<title>CV</title>\n<link rel="stylesheet" href="style.css">\n</head>\n<body>\n<button id="dark-mode-toggle">Toggle Dark Mode</button>\n</body>\n</html>\n',
        'style.css':'body{color:#333}\nbody.dark-mode{color:#eee;background:#222}\n'+ARCHIVE,
        'script.js':"document.getElementById('dark-mode-toggle').addEventListener('click',()=>document.body.classList.toggle('dark-mode'));\n"}
CANDIDATE={'index.html':BEFORE['index.html'].replace('</head>','<style>\n.container{height:100vh;justify-content:center}\n</style>\n</head>'),
           'style.css':BEFORE['style.css']+'main{padding:1rem}\n'}


def test_changed_regions_cover_only_candidate_changes_with_context():
    focus,replaced=changed_regions(BEFORE,CANDIDATE,context_lines=1)
    assert set(focus)=={'index.html','style.css'}
    css=CANDIDATE['style.css'];start,end=focus['style.css'][0]
    assert css[start:end]=='/* Archived style note 139: retained source context, never discarded. */\nmain{padding:1rem}\n'
    html=CANDIDATE['index.html'];start,end=focus['index.html'][0]
    assert '<style>' in html[start:end] and '<!doctype' not in html[start:end]
    assert replaced==[]
    edited={'index.html':BEFORE['index.html'].replace('Toggle Dark Mode','Theme')}
    focus,replaced=changed_regions(BEFORE,edited)
    assert replaced==[{'path':'index.html','candidate_line':8,'saved_source':'<button id="dark-mode-toggle">Toggle Dark Mode</button>\n'}]
    assert changed_regions(BEFORE,{'new.js':'x=1\n'})[0]=={'new.js':[(0,4)]}
    assert changed_regions(BEFORE,{'script.js':BEFORE['script.js']})[0]=={}


def test_focused_targets_omit_unchanged_source_but_keep_it_hash_bound():
    focus,_=changed_regions(BEFORE,CANDIDATE)
    targets=RepairTargets(CANDIDATE,1,focus=focus)
    prompt=json.dumps(targets.source)
    assert 'Archived style note 000' not in prompt and 'Archived style note 139' in prompt
    omitted=[s for f in targets.source for s in f['spans'] if s['target_id'] is None]
    assert omitted and all(set(s)=={'target_id','omitted_unchanged_chars','sha256'} for s in omitted)
    css_target=next(t for t in targets.targets.values() if t.path=='style.css')
    result=targets.apply(CANDIDATE,[{'target_id':css_target.target_id,'after':CANDIDATE['style.css'][css_target.start:css_target.end].replace('main{padding:1rem}\n','')}],1)
    assert result['style.css']==BEFORE['style.css'] and result['index.html']==CANDIDATE['index.html']
    # Focus is part of the snapshot identity; full and focused targets never share IDs.
    assert targets.snapshot!=RepairTargets(CANDIDATE,1).snapshot
    assert not set(targets.targets)&set(RepairTargets(CANDIDATE,1).targets)
    with pytest.raises(ProjectError):RepairTargets(CANDIDATE,1,ranges={},focus=focus)
    with pytest.raises(ProjectError):targets.apply({**CANDIDATE,'style.css':CANDIDATE['style.css']+' '},[],1)


def test_unfocused_snapshot_identity_is_unchanged_for_existing_callers():
    # Saved receipts bind the previous snapshot formula; it must not drift.
    import hashlib
    from src.core.project_store import digest
    files={'index.html':'<p>Original</p>\n'}
    expected=hashlib.sha256(json.dumps({'revision':3,'files':{'index.html':digest(files['index.html'])},'binding':{},'ranges':None},sort_keys=True).encode()).hexdigest()
    assert RepairTargets(files,3).snapshot==expected


def test_edit_repair_prompt_contains_only_changes_and_saved_replacements(system):
    from src.core.invoice_orchestrator import InvoiceOrchestrator,ProjectRequest
    focus,_=changed_regions(BEFORE,CANDIDATE)
    target=RepairTargets(CANDIDATE,None,focus=focus)
    html_target=next(t for t in target.targets.values() if t.path=='index.html')
    fixed=CANDIDATE['index.html'][html_target.start:html_target.end].replace('.container{height:100vh;justify-content:center}\n','')
    system.backend.text=json.dumps({'edits':[{'target_id':html_target.target_id,'after':fixed}]})
    result,receipt=InvoiceOrchestrator(system).repair_candidate(CANDIDATE,ProjectRequest(user_request='Improve the interface',requirements=['Keep theme']),
        'light 480px theme control could not be clicked: control rendered outside the reachable scrolled viewport',{},cancel=threading.Event(),deadline=time.monotonic()+3,max_tokens=256,before=BEFORE)
    sent=system.backend.calls[-1]['messages'][1]['content']
    assert 'Archived style note 000' not in sent and 'saved_source_replaced_by_candidate' in sent
    assert 'omitted spans are unchanged saved source' in system.backend.calls[-1]['messages'][0]['content']
    assert receipt['repair_scope']['mode']=='candidate_changes' and receipt['repair_scope']['editable_chars']<receipt['repair_scope']['candidate_chars']
    assert result['style.css']==CANDIDATE['style.css'] and '100vh' not in result['index.html']
    assert system.backend.calls[-1]['response_format']['schema']['$defs']['CandidatePatch']['properties']['target_id']['enum']==list(target.targets)


def test_overflowing_repair_records_measured_preflight_without_model_call(system,monkeypatch):
    from src.core.invoice_orchestrator import InvoiceOrchestrator,ProjectRequest
    monkeypatch.setattr(system.backend,'measure_messages',lambda messages,max_tokens=1024,**o:{'prompt_tokens':6799,'context_size':4096,'requested_output_limit':max_tokens,'effective_output_limit':0,'measurement':'fixture'})
    calls=len(system.backend.calls)
    with pytest.raises(ProjectError) as caught:
        InvoiceOrchestrator(system).repair_candidate(CANDIDATE,ProjectRequest(user_request='Improve',requirements=['Keep']),'failure',{},cancel=threading.Event(),deadline=time.monotonic()+3,max_tokens=1024,before=BEFORE)
    receipt=caught.value.repair_receipt
    assert receipt['model_called'] is False and receipt['preflight']['prompt_tokens']==6799 and receipt['repair_scope']['mode']=='candidate_changes'
    assert len(system.backend.calls)==calls
    with pytest.raises(ProjectError):
        InvoiceOrchestrator(system).repair_candidate(BEFORE,ProjectRequest(user_request='Improve',requirements=['Keep']),'failure',{},cancel=threading.Event(),deadline=time.monotonic()+3,max_tokens=64,before=BEFORE)


def test_toggle_failure_reports_measured_unreachable_control():
    from src.core.candidate_browser import toggle_failure
    assert toggle_failure(json.dumps({'clicked':True}),'light',480) is None
    message=toggle_failure(json.dumps({'clicked':False,'reason':'control rendered outside the reachable scrolled viewport','control':'button#dark-mode-toggle','rect':[115,-450,170,38],'viewport':[465,800],'hit':'p'}),'dark',480)
    assert message.startswith('dark 480px theme control could not be clicked') and '[115, -450, 170, 38]' in message and 'button#dark-mode-toggle' in message
    assert 'not activated' in toggle_failure(False,'light',1280)
    assert 'unreadable' in toggle_failure('not json','light',1280)
