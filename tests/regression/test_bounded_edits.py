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
        return {'prompt_tokens':count,'context_size':2600,'effective_output_limit':max(0,min(max_tokens,2600-count)),
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
