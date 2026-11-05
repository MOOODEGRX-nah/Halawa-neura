"""Exact user wording, durable jobs, actual-source edits; inference is fake."""
import os
import time
import pytest
from tests.regression.test_chat_dispatch import application, request_id

WEB='```html index.html\n<link rel="stylesheet" href="style.css"><h1>QA CV</h1>\n```\n```css style.css\nbody{background:white}\n```'

def terminal(jobs,job,seconds=4):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        result=jobs.get(job)
        if result['state'] in ('completed','failed','cancelled'):return result
        time.sleep(.005)
    raise AssertionError('job did not terminate within bounded fixture deadline')

@pytest.mark.parametrize('text',[
    'برمج لي موقع للcv', 'برمج لي موقع للـ CV',
    'أنشئ موقع سيرة ذاتية باستخدام HTML وCSS وJavaScript',
    'اكتب برنامج Python لحساب المصروفات',
])
def test_exact_creation_requests_enter_workspace_job_not_chat(system,text):
    system.backend.text=WEB if 'موقع' in text else '```python main.py\nprint("QA expense")\n```'
    app,desktop,dispatch=application(system);jobs=app.state.project_jobs;store=app.state.project_store
    try:
        rid=request_id();created=dispatch.dispatch(text,rid,session_id='cv_chat')
        assert created['kind']=='project',created
        pid=created['project']['project_id'];job=created['job']['job_id']
        assert dispatch.dispatch(text,rid,session_id='cv_chat')['job']['job_id']==job
        result=terminal(jobs,job);assert result['state']=='completed',result
        assert len(store.list())==1 and len(system.backend.calls)==2
        assert result['invoice']['user_request']==text and text in result['invoice']['requirements']
        assert store.get(pid)['validation']['executed'] is False
        assert store.get(pid)['preview']['supported']==('موقع' in text)
        assert not desktop.calls
    finally:jobs.shutdown();store.close()


def test_followup_edit_reuses_current_source_and_preserves_other_files(system):
    app,desktop,dispatch=application(system);store=app.state.project_store;jobs=app.state.project_jobs
    pid=store.create('QA CV','CV')['project_id']
    store.commit(pid,{'index.html':'<link rel="stylesheet" href="style.css"><h1>CV</h1>', 'style.css':'body{background:white}'},0)
    system.backend.text='```css style.css\nbody{background:blue}\n```'
    try:
        text='غيّر لون الخلفية إلى الأزرق'
        result=dispatch.dispatch(text,request_id(),pid,session_id='cv_chat')
        assert result['kind']=='project' and result['operation']=='edit'
        assert result['project']['project_id']==pid
        job=terminal(jobs,result['job']['job_id']);assert job['state']=='completed',job
        assert len(store.list())==1 and store.get(pid)['project_revision']==2
        invoice=job['invoice'];assert 'body{background:white}' in invoice['context_summary']
        assert 'index.html' in invoice['context_summary'] and invoice['user_request']==text
        assert 'blue' in store.read(pid,'style.css')['content']
        assert '<h1>CV</h1>' in store.read(pid,'index.html')['content']
        system.backend.text='not a named file'
        failed=dispatch.dispatch(text,request_id(),pid,session_id='cv_chat')
        assert terminal(jobs,failed['job']['job_id'])['state']=='failed'
        assert store.get(pid)['project_revision']==2 and 'blue' in store.read(pid,'style.css')['content']
    finally:jobs.shutdown();store.close()


def test_dirty_editor_and_explanation_do_not_start_edit(system):
    app,desktop,dispatch=application(system);store=app.state.project_store
    pid=store.create('QA CV','CV')['project_id'];store.commit(pid,{'index.html':'<h1>CV</h1>'},0)
    assert dispatch.dispatch('اشرح هذا الكود',request_id(),pid,session_id='cv_chat')=={'kind':'chat'}
    result=dispatch.dispatch('غيّر لون الخلفية إلى الأزرق',request_id(),pid,session_id='cv_chat',workspace_dirty=True)
    assert result['kind']=='workspace' and result['edit_request']=='غيّر لون الخلفية إلى الأزرق'
    assert not system.backend.calls and store.get(pid)['project_revision']==1
    store.close()


def test_same_stat_edit_marks_metadata_stale_and_reindex_refreshes(system):
    app,desktop,dispatch=application(system);store=app.state.project_store
    pid=store.create('QA metadata','same stat')['project_id'];store.commit(pid,{'main.py':'print(1)\n'},0)
    path=store.directory(pid)/'main.py';stat=path.stat();path.write_text('print(2)\n');os.utime(path,ns=(stat.st_atime_ns,stat.st_mtime_ns))
    unchecked=store.get(pid,freshness=False)
    assert unchecked['source_freshness'] is None and 'Source freshness: not_checked' in unchecked['summary']
    assert store.get(pid)['source_freshness']=='stale'
    assert store.answer(pid,'ما هي لغات المشروع؟')['stale']
    rebuilt=store.rebuild(pid,1)
    assert rebuilt['source_freshness']=='current' and rebuilt['project_revision']==rebuilt['summary_revision']==2
    assert not system.backend.calls
    store.close()


def test_completed_project_metadata_uses_source_facts_without_model(system):
    app,desktop,dispatch=application(system);store=app.state.project_store
    pid=store.create('QA source facts','CV')['project_id']
    meta=store.commit(pid,{'index.html':'<button onclick="this.textContent=1">QA</button>'},0)
    assert meta['features_provenance']=='static_source_observations'
    assert any('Buttons: 1' in feature for feature in meta['features'])
    assert any('not run' in limit for limit in meta['limitations'])
    assert meta['summary_revision']==meta['project_revision']==1 and len(meta['summary'])<3500
    assert store.answer(pid,'ما هي لغات هذا المشروع؟')['model_called'] is False
    canonical=store._canonical(pid);canonical.pop('features');canonical.pop('features_provenance')
    import json
    store.db.execute('UPDATE projects SET metadata=? WHERE id=?',(json.dumps(canonical),pid));store.db.commit()
    restored=store.get(pid)
    assert restored['features'] and store._canonical(pid)['features'] and restored['project_revision']==1
    assert not system.backend.calls
    store.close()


def test_chat_cancel_retry_and_later_request_are_bounded(system):
    import threading
    app,desktop,dispatch=application(system);jobs=app.state.project_jobs;store=app.state.project_store
    system.backend.text=WEB;system.backend.release=threading.Event()
    try:
        rid=request_id();created=dispatch.dispatch('برمج لي موقع للcv',rid,session_id='cancel_chat')
        assert system.backend.entered.wait(1)
        assert dispatch.dispatch('برمج لي موقع للcv',rid,session_id='cancel_chat')['job']['job_id']==created['job']['job_id']
        assert len(store.list())==1
        jobs.cancel(created['job']['job_id']);system.backend.release.set()
        assert terminal(jobs,created['job']['job_id'])['state']=='cancelled'
        system.backend.release=None
        later=dispatch.dispatch('برمج لي موقع للـ CV',request_id(),session_id='cancel_chat')
        assert terminal(jobs,later['job']['job_id'])['state']=='completed'
        assert len(system.backend.loads)==1 and not desktop.calls
    finally:system.backend.release=None;jobs.shutdown();store.close()


@pytest.mark.parametrize('output',['','إليك التعليمات فقط دون ملفات'])
def test_invalid_first_generation_is_failed_without_chat_tutorial_fallback(system,output):
    app,desktop,dispatch=application(system);store=app.state.project_store;jobs=app.state.project_jobs
    system.backend.text=output
    try:
        created=dispatch.dispatch('برمج لي موقع للcv',request_id(),session_id='failed_chat')
        assert created['kind']=='project',created
        job=terminal(jobs,created['job']['job_id']);assert job['state']=='failed' and job['error']
        project=store.get(created['project']['project_id'])
        assert project['project_revision']==0 and not project['files'] and not project['preview']['supported']
        assert len(system.backend.calls)==2 and not desktop.calls
    finally:jobs.shutdown();store.close()


def test_real_model_style_language_only_fences_use_unambiguous_contract_and_references(system):
    # Reproduces the real Coder failure without claiming this fixture is inference.
    system.backend.text='```html\n<link rel="stylesheet" href="assets/cv.css"><h1>CV</h1><script src="assets/cv.js"></script>\n```\n```css\nbody{background:white}\n```\n```javascript\nconsole.log("QA");\n```'
    app,desktop,dispatch=application(system);store=app.state.project_store;jobs=app.state.project_jobs
    try:
        created=dispatch.dispatch('برمج لي موقع للcv',request_id(),session_id='cv_chat')
        job=terminal(jobs,created['job']['job_id']);assert job['state']=='completed',job
        project=store.get(created['project']['project_id'])
        assert {f['path'] for f in project['files']}=={'index.html','assets/cv.css','assets/cv.js'}
        assert project['preview']['supported']
        result=next(stage['result'] for stage in job['stage_results'] if stage['stage']=='generating')
        assert result['filename_resolutions']=={'index.html':'hint','assets/cv.css':'reference','assets/cv.js':'reference'}
        system.backend.text='```css\nbody{background:blue}\n```'
        changed=dispatch.dispatch('غيّر لون الخلفية إلى الأزرق',request_id(),project['project_id'],session_id='cv_chat')
        assert terminal(jobs,changed['job']['job_id'])['state']=='completed'
        assert 'blue' in store.read(project['project_id'],'assets/cv.css')['content']
    finally:jobs.shutdown();store.close()


def test_ambiguous_or_unsafe_filename_hints_never_guess_or_generate(system):
    from src.core.project_stream import FileStream
    from src.core.invoice_orchestrator import ProjectRequest
    from src.core.project_files import ProjectError
    parser=FileStream(lambda *args:None,expected_files=['a.html','b.html'])
    with pytest.raises(ProjectError):parser.feed('```html\n<h1>ambiguous</h1>\n```\n')
    with pytest.raises(ValueError):ProjectRequest(user_request='QA',requirements=['QA'],filename_hints=['../escape.html'])
    assert not system.backend.calls
