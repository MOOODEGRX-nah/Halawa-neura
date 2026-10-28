import threading
import time
import pytest
from src.core.project_store import ProjectStore
from src.core.project_jobs import ProjectJobs, WorkspaceRequest, TERMINAL
from src.core.project_stream import FileStream
from src.core.project_files import ProjectError

GOOD='```python main.py\ndef add(a,b):\n    return a+b\n```'


def wait(jobs, job_id):
    deadline=time.monotonic()+4
    while time.monotonic()<deadline:
        job=jobs.get(job_id)
        if job['state'] in TERMINAL:return job
        time.sleep(.005)
    raise AssertionError('Job did not terminate')


def test_fragmented_fences_and_nested_fence_content():
    events=[];parser=FileStream(lambda kind,data:events.append((kind,data)))
    text='````markdown README.md\n# Example\n```python\nprint(1)\n```\n````\n```python main.py\ndef add(a,b):return a+b\n```'
    for character in text:parser.feed(character)
    files=parser.finish()
    assert '```python\nprint(1)\n```' in files['README.md']
    assert 'add' in files['main.py']
    assert any(kind=='file_delta' for kind,data in events)


def test_partial_lines_arrive_before_file_completion_with_utf8_offsets():
    events=[];parser=FileStream(lambda kind,data:events.append((kind,data)))
    parser.feed('```html index.html\r\n<h1>مرحبا 🌍')
    assert parser.files['index.html']['content']=='<h1>مرحبا 🌍'
    assert not parser.files['index.html']['complete']
    parser.feed('</h1>\r\n```\r');parser.feed('\n')
    assert parser.finish()['index.html']=='<h1>مرحبا 🌍</h1>\n'
    deltas=[data for kind,data in events if kind=='file_delta']
    assert deltas[1]['offset']==len('<h1>مرحبا 🌍'.encode())
    text='```python main.py\r\npass\r\n```\r\n'
    full=FileStream(lambda *args:None);full.feed(text)
    fragmented=FileStream(lambda *args:None)
    for char in text:fragmented.feed(char)
    assert full.finish()==fragmented.finish()


@pytest.mark.parametrize('text', ['no files', '```python main.py\npartial',
    '```python main.py\npass\n```\n```python main.py\npass\n```',
    '```python index.html\npass\n```', '```python ../escape.py\npass\n```',
    '```python main.py\n# filename: other.py\npass\n```'])
def test_invalid_file_streams(text):
    parser=FileStream(lambda *args:None)
    with pytest.raises(ProjectError):parser.feed(text);parser.finish()


def test_durable_events_reconnection_does_not_duplicate(system):
    store=ProjectStore(system.settings.data_dir);jobs=ProjectJobs(store,system)
    system.backend.text=GOOD
    created=jobs.create({'user_request':'create add','requirements':['add'],'background':True})
    job_id=created['job']['job_id'];p=created['project']['project_id']
    assert wait(jobs,job_id)['state']=='completed'
    a=jobs.events(job_id,0);b=jobs.events(job_id,0)
    assert a==b and len(system.backend.calls)==1
    assert [event['seq'] for event in a]==list(range(1,len(a)+1))
    assert all(event['job_id']==job_id and event['project_id']==p for event in a)
    assert any(e['type']=='file_delta' for e in a)
    assert store.read(p,'main.py')['content'].startswith('def add')
    jobs.shutdown();store.close()
    store=ProjectStore(system.settings.data_dir);jobs=ProjectJobs(store,system)
    assert jobs.get(job_id)['state']=='completed'
    assert len(system.backend.calls)==1
    jobs.shutdown();store.close()


def test_cancellation_releases_native_lock_and_preserves_good_revision(system):
    store=ProjectStore(system.settings.data_dir);jobs=ProjectJobs(store,system)
    p=store.create('old','old')['project_id'];store.commit(p,{'main.py':'pass\n'},0)
    system.backend.text=GOOD;system.backend.release=threading.Event()
    record=jobs.create({'user_request':'edit','requirements':['add'],'project_id':p,
                        'context_files':['main.py'],'expected_revision':1})
    job_id=record['job']['job_id']
    assert system.backend.entered.wait(2)
    jobs.cancel(job_id)
    assert wait(jobs,job_id)['state']=='cancelled'
    assert system.lock.acquire(blocking=False)
    system.lock.release()
    assert store.get(p)['project_revision']==1
    assert store.read(p,'main.py')['content']=='pass\n'
    jobs.shutdown();store.close()


def test_failed_draft_and_restart_interruption(system):
    store=ProjectStore(system.settings.data_dir);jobs=ProjectJobs(store,system)
    system.backend.text='```python main.py\ndef partial():\n'
    created=jobs.create({'user_request':'create','requirements':['a file']})
    jid=created['job']['job_id'];p=created['project']['project_id']
    assert wait(jobs,jid)['state']=='failed'
    assert jobs.get(jid)['draft_files']['main.py']['content']=='def partial():\n'
    assert not store.get(p)['files']
    jobs.shutdown()
    store.db.execute("UPDATE jobs SET state='generating' WHERE id=?",(jid,));store.db.commit()
    jobs=ProjectJobs(store,system)
    assert jobs.get(jid)['state']=='failed' and 'interrupted' in jobs.get(jid)['error']
    assert jobs.get(jid)['draft_files']
    jobs.shutdown();store.close()


def test_edit_cannot_overwrite_existing_file_from_summary_alone(system):
    store=ProjectStore(system.settings.data_dir);jobs=ProjectJobs(store,system)
    p=store.create('source selection','source selection')['project_id']
    store.commit(p,{'main.py':'pass\n','other.py':'original=1\n'},0)
    system.backend.text='```python other.py\noriginal=2\n```'
    created=jobs.create({'user_request':'edit current file','requirements':['edit'],
        'project_id':p,'expected_revision':1,'context_files':['main.py']})
    result=wait(jobs,created['job']['job_id'])
    assert result['state']=='failed' and 'other.py' in result['error']
    assert result['draft_files']['other.py']['content']=='original=2\n'
    assert store.get(p)['project_revision']==1
    assert store.read(p,'other.py')['content']=='original=1\n'
    jobs.shutdown();store.close()
