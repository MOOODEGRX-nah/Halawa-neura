"""Controlled patch/model/token boundaries; real store/jobs, no model-quality claim."""
import json,threading,time
from pathlib import Path
import pytest
from src.core.bounded_edits import apply_exact
from src.core.project_files import ProjectError,Conflict
from src.core.project_store import ProjectStore,digest
from src.core.project_jobs import ProjectJobs
from tests.regression.test_project_jobs import wait

HTML='<html><body><h1>Original CV</h1><a href="#" id="login">Login</a><button id="theme">Theme</button></body></html>'
BASE={'index.html':HTML,'style.css':'body { color: black; background: white; }','script.js':'const value = 1;'}


def packet(path,source,*,before=None,after=None,revision=1):
    return json.dumps({'base_revision':revision,'path':path,'source_sha256':digest(source),
        'edits':[] if before is None else [{'before':before,'after':after}], 'new_content':None})


def fixture(system,files=BASE):
    store=ProjectStore(system.settings.data_dir);pid=store.create('CV','CV')['project_id'];store.commit(pid,files,0)
    return store,ProjectJobs(store,system),pid


def start(jobs,pid,files):
    return jobs.create({'project_id':pid,'expected_revision':1,'context_files':list(files),
       'user_request':'هل يمكنك ان تحسن الواجهه الموقع بجودة عالي و مبهر جدا','requirements':['Preserve Login and theme'],'max_tokens':4096})['job']['job_id']


@pytest.mark.parametrize('anchor',['x','absent'])
def test_ambiguous_and_missing_anchor_never_guessed(anchor):
    with pytest.raises(ProjectError):apply_exact({'x.txt':'x x'},'x.txt',[{'before':anchor,'after':'changed'}],'x x')


def test_scope_cannot_modify_unseen_source():
    with pytest.raises(ProjectError):apply_exact({'x.txt':'left right'},'x.txt',[{'before':'right','after':'changed'}],'left')


def test_multiple_related_files_promote_once(system):
    store,jobs,pid=fixture(system)
    system.backend.replies=[packet('index.html',HTML,before='</body>',after='<footer>Local preview</footer></body>'),
        packet('style.css',BASE['style.css'],before='black',after='#111'),packet('script.js',BASE['script.js'],before='1',after='2')]
    try:
        result=wait(jobs,start(jobs,pid,BASE));assert result['state']=='completed',result
        assert store.get(pid)['project_revision']==2
        assert set(result['execution']['changed_files'])==set(BASE)
        assert result['execution']['base_hashes']=={p:digest(v) for p,v in BASE.items()}
        assert store.read(pid,'index.html')['content'].count('Login')==1
        ops=next(s for s in result['stage_results'] if s['stage']=='generating')['result']['operations']
        assert len(ops)==3 and sum(x['output_limit'] for x in ops)<=3072
        calls=[c for c in system.backend.calls if c['messages'][0]['content'].startswith('Return a bounded file patch')]
        assert all(c['response_format']['schema']['properties']['new_content']=={'type':'null'} for c in calls)
        css_shapes=[c['response_format']['schema']['properties']['css_rules'] for c in calls]
        arrays=[shape['anyOf'][0] for shape in css_shapes if 'anyOf' in shape]
        assert arrays and all(shape['maxItems']==6 for shape in arrays)
    finally:jobs.shutdown();store.close()


@pytest.mark.parametrize('failure',['duplicate','stale_envelope','length','empty_output'])
def test_second_file_failure_cannot_commit_first_file(system,failure):
    base={'main.py':'VALUE = 1\n','other.py':'X = 1\nX = 2\n'};store,jobs,pid=fixture(system,base)
    first=packet('main.py',base['main.py'],before='1',after='3')
    second=packet('other.py',base['other.py'],before='X',after='Y',revision=9 if failure=='stale_envelope' else 1)
    if failure=='empty_output':second=''
    if failure=='length':second=packet('other.py',base['other.py'],before='X = 1',after='X = 4')
    system.backend.replies=[first,second];original=system.backend.generate;calls=0
    def generate(**options):
        nonlocal calls
        if options['messages'][0]['content'].startswith('Return a bounded file patch'):
            calls+=1
            if calls==2 and failure=='length':system.backend.finish='length'
        return original(**options)
    system.backend.generate=generate
    try:
        result=wait(jobs,start(jobs,pid,base));assert result['state']=='failed',result
        assert store.get(pid)['project_revision']==1
        assert store.committed_files(pid)==base
        assert not result['saved_files'] and not result['execution']
    finally:jobs.shutdown();store.close()


def test_supplied_stale_hashes_rejected_at_admission(system):
    store,jobs,pid=fixture(system)
    try:
        with pytest.raises(Conflict):jobs.create({'project_id':pid,'expected_revision':1,'context_files':['index.html'],
            'source_hashes':{'index.html':'0'*64},'user_request':'Edit','requirements':['Edit']})
        assert not system.backend.calls
    finally:jobs.shutdown();store.close()


def test_external_change_during_generation_is_not_overwritten(system):
    base={'main.py':'VALUE = 1\n'};store,jobs,pid=fixture(system,base)
    system.backend.replies=[packet('main.py',base['main.py'],before='1',after='2')]
    system.backend.release=threading.Event()
    try:
        jid=start(jobs,pid,base);assert system.backend.entered.wait(2)
        (store.directory(pid)/'main.py').write_text('VALUE = 9\n')
        system.backend.release.set();result=wait(jobs,jid)
        assert result['state']=='failed' and not result['saved_files']
        assert (store.directory(pid)/'main.py').read_text()=='VALUE = 9\n'
        assert store.get(pid)['project_revision']==1
    finally:system.backend.release.set();jobs.shutdown();store.close()


def test_large_source_is_partitioned_without_discarding_bytes(system):
    from src.core.bounded_edits import BoundedEditor
    from src.core.invoice_orchestrator import InvoiceOrchestrator,ProjectRequest
    source='/* token fixture */\n'*800+'body { color: black; }\n';seen=[]
    def measure(messages,max_tokens=1024,**options):
        # Deliberate toy word-token fixture, NOT an estimate of real inference.
        count=len(messages[1]['content'].split())
        return {'prompt_tokens':count,'context_size':4000,'effective_output_limit':max(0,min(max_tokens,4000-count)),
                'measurement':'controlled toy vocabulary boundary'}
    system.backend.measure_messages=measure
    original=system.backend.generate
    def generate(**options):
        messages=options['messages']
        if messages[0]['content'].startswith('Return a bounded file patch'):
            d=json.loads(messages[1]['content']);scope=d['source_scope'];seen.append(scope)
            system.backend.replies=[packet(d['path'],source,before='black' if 'black' in scope else None,after='#111')]
        return original(**options)
    system.backend.generate=generate
    request=ProjectRequest(user_request='Improve the existing site',requirements=['Keep content'],max_tokens=3072)
    events=list(BoundedEditor(InvoiceOrchestrator(system)).generate(request,{'style.css':source},['style.css'],1,
        source,'p_test','j_test',threading.Event(),time.monotonic()+5))
    assert len(seen)>1 and ''.join(seen)==source
    assert events[-1]['kind']=='finished'
    assert [e for e in events if e['kind']=='candidate_file'][-1]['content']==source.replace('black','#111')


def test_opening_tag_replaced_with_closed_block_cannot_promote():
    from src.core.project_validation import inspect_files
    source='<html><style>body{color:black}</style><body>CV</body></html>'
    broken=apply_exact({'index.html':source},'index.html',[{'before':'<style>','after':'<style>body{color:blue}</style>'}],source)
    assert any('Unmatched' in e for e in inspect_files(broken)[2]['errors'])


def test_structured_html_insertions_have_valid_server_owned_wrappers():
    from src.core.bounded_edits import FilePatch,apply_sections
    from src.core.project_validation import inspect_files
    source='<html><head></head><body><p>Original</p></body></html>'
    patch=FilePatch(base_revision=1,path='index.html',source_sha256=digest(source),edits=[],
        css_rules='p { color: #111; }',html_fragment='<button id="details">Details</button>',
        script_code='document.getElementById("details").addEventListener("click",()=>{});')
    result=apply_sections({'index.html':source},'index.html',patch,source,True)
    assert not inspect_files(result)[2]['errors']
    assert result['index.html'].count('</script>')==result['index.html'].count('<script>')==1
    assert 'Original' in result['index.html']


def test_structured_insert_cannot_guess_missing_or_ambiguous_boundary():
    from src.core.bounded_edits import FilePatch,apply_sections
    source='<head></head><head></head><body></body>'
    patch=FilePatch(base_revision=1,path='index.html',source_sha256=digest(source),edits=[],css_rules='body { color: black; }')
    with pytest.raises(ProjectError):apply_sections({'index.html':source},'index.html',patch,source,True)
    with pytest.raises(ProjectError):apply_sections({'index.html':source},'index.html',patch,'<body>',False)


def test_appending_css_requires_exact_end_of_file_operation():
    from src.core.bounded_edits import FilePatch,apply_sections
    source='body{color:black}'
    patch=FilePatch(base_revision=1,path='style.css',source_sha256=digest(source),edits=[],css_rules='body { padding: 1rem; }')
    with pytest.raises(ProjectError):apply_sections({'style.css':source},'style.css',patch,source,False)
    assert apply_sections({'style.css':source},'style.css',patch,source,True)['style.css'].startswith(source)


def test_user_feature_requirements_follow_successful_requests_and_explicit_removal():
    from src.core.edit_preservation import requested_web_features
    from src.core.feature_intent import build_contract
    def checked(history,text):return requested_web_features(build_contract(text,history,{'intent':'project.edit'}))
    history=[{'origin':'user_request','text':'أضف زر تسجيل دخول'},{'origin':'user_request','text':'أضف الوضع الداكن إلى هذا المشروع'}]
    assert checked(history,'حسن واجهة الموقع')=={'login':True,'theme':True}
    assert checked(history,'احذف Login')=={'theme':True}
    assert checked([], 'Explain dark mode')=={}


def test_worker_row_reads_share_the_store_lock(system):
    store,jobs,pid=fixture(system);entered=threading.Event();finished=threading.Event();rows=[]
    # Insert a queued fixture without starting an inference worker.
    jid='j_'+'a'*32
    store.db.execute('INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?)',(jid,pid,'queued','{}','{}',0,0,None,'QA','QA'));store.db.commit()
    def read():
        entered.set();rows.append(jobs._row(jid));finished.set()
    try:
        with store.lock:
            thread=threading.Thread(target=read);thread.start();assert entered.wait(1)
            assert not finished.wait(.03)
        thread.join(1);assert finished.is_set() and rows[0]['draft']=='{}'
    finally:jobs.shutdown();store.close()


def test_measured_contrast_repair_scopes_dark_host_without_changing_light():
    from src.core.contrast_repair import repair_contrast
    source='<html><body><p>Original</p></body></html>'
    def sample(scheme,background):
        return {'color_scheme':scheme,'mode':'initial','width':1280,'body_classes':[],
            'checks':[{'selector':'body > p:nth-of-type(1)','foreground':[0,0,0],
                'background':background,'background_selector':'body','minimum':4.5,
                'ratio':21 if background==[255,255,255] else 1.112}]}
    report={'errors':['dark initial low text contrast: fixture'],'samples':[sample('light',[255,255,255]),sample('dark',[17,17,17])]}
    fixed,receipt=repair_contrast({'index.html':source},'index.html',report,'Improve readability')
    assert source=='<html><body><p>Original</p></body></html>'
    assert len(receipt['rules'])==1
    assert receipt['rules'][0].startswith('@media (prefers-color-scheme: dark)')
    assert 'color:#fff!important' in receipt['rules'][0]
    assert all(c['color_scheme']=='dark' for c in receipt['changes'])
    assert 'Original' in fixed['index.html']


def test_structured_css_serializes_bounded_rules_and_rejects_duplicates():
    from src.core.bounded_edits import FilePatch,css_text,apply_sections
    from pydantic import ValidationError
    source='<html><head></head><body><p>Original</p></body></html>'
    rule={'selector':'body','declarations':[{'name':'color','value':'#eee'},{'name':'background-color','value':'#111'}],'scheme':'dark'}
    patch=FilePatch(base_revision=1,path='index.html',source_sha256=digest(source),edits=[],css_rules=[rule])
    changed=apply_sections({'index.html':source},'index.html',patch,source,True)
    assert '@media (prefers-color-scheme: dark){body{color:#eee;background-color:#111;}}' in changed['index.html']
    assert 'Original' in changed['index.html']
    with pytest.raises(ProjectError):css_text([rule,rule])
    with pytest.raises(ValidationError):FilePatch(base_revision=1,path='index.html',source_sha256=digest(source),edits=[],css_rules=[rule]*7)
    with pytest.raises(ValidationError):css_text([{**rule,'declarations':[{'name':'color','value':'red'},{'name':'COLOR','value':'blue'}]}])
    with pytest.raises(ProjectError):css_text([{**rule,'declarations':[{'name':'color','value':'red; background: black'}]}])
