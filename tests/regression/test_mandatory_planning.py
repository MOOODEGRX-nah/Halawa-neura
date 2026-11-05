"""Server-side planning is required before all project code generation.

Inference is controlled in these tests; none claim real model or GPU quality.
"""
import json
import threading
import time

import pytest

from src.core.invoice_orchestrator import InvoiceOrchestrator, ProjectRequest
from src.core.project_jobs import ProjectJobs
from src.core.project_store import ProjectStore
from tests.regression.test_chat_dispatch import application, request_id
from tests.regression.test_project_jobs import wait


GOOD = '```python main.py\ndef add(a,b):\n    return a+b\n```'
PLAN = {'steps': ['Read the actual requirements.', 'Implement addition.', 'Check the result.'],
        'files': ['main.py']}


def request(flag=None):
    value = {'user_request': 'Implement addition', 'requirements': ['Add two numbers'],
             'required_files': ['main.py']}
    if flag is not None:
        value['plan'] = flag
    return value


@pytest.mark.parametrize('flag', [None, False, True])
def test_legacy_clients_cannot_disable_request_planning(flag):
    parsed = ProjectRequest.model_validate(request(flag))
    assert parsed.plan is True
    assert parsed.model_dump()['plan'] is True


@pytest.mark.parametrize('flag', [None, False, True])
def test_synchronous_generation_requires_and_passes_validated_plan(system, flag):
    system.backend.plan_replies = [json.dumps(PLAN)]
    system.backend.text = GOOD
    result = InvoiceOrchestrator(system).process_request(request(flag))
    assert result['success'], result
    assert [stage['stage'] for stage in result['stages']] == ['plan', 'execution_0']
    assert result['stages'][0]['result']['accepted'] is True
    assert len(system.backend.calls) == 2
    generated_prompt = system.backend.calls[1]['messages'][1]['content']
    passed = json.loads(generated_prompt.split('\nValidated implementation plan:\n')[1])
    assert passed == PLAN


@pytest.mark.parametrize('flag', [None, False, True])
@pytest.mark.parametrize('editing', [False, True])
def test_background_creation_and_edit_plan_before_generation(system, flag, editing):
    store = ProjectStore(system.settings.data_dir)
    jobs = ProjectJobs(store, system)
    system.backend.text = GOOD
    payload = request(flag)
    if editing:
        project = store.create('Existing project', 'Owned fixture')['project_id']
        store.commit(project, {'main.py': '# ORIGINAL_SOURCE\npass\n'}, 0)
        payload.update(project_id=project, expected_revision=1, context_files=['main.py'])
    try:
        created = jobs.create(payload)
        job_id = created['job']['job_id']
        result = wait(jobs, job_id)
        assert result['state'] == 'completed', result
        stages = result['stage_results']
        names = [stage['stage'] for stage in stages]
        assert names.index('planning') < names.index('generating') < names.index('validating')
        planning = next(stage for stage in stages if stage['stage'] == 'planning')
        assert planning['status'] == 'completed' and planning['result']['accepted'] is True
        assert len(system.backend.calls) == 2
        stored = json.loads(store.db.execute('SELECT request FROM jobs WHERE id=?', (job_id,)).fetchone()['request'])
        assert stored['plan'] is True
        if editing:
            assert 'ORIGINAL_SOURCE' in system.backend.calls[0]['messages'][1]['content']
            assert 'ORIGINAL_SOURCE' in system.backend.calls[1]['messages'][1]['content']
        before = len(system.backend.calls)
        jobs.events(job_id, 0)
        jobs.get(job_id)
        assert len(system.backend.calls) == before
    finally:
        jobs.shutdown()
        store.close()


@pytest.mark.parametrize('editing', [False, True])
def test_composer_dispatch_starts_one_planned_job(system, editing):
    app, desktop, dispatcher = application(system)
    store, jobs = app.state.project_store, app.state.project_jobs
    system.backend.text = GOOD
    project = None
    if editing:
        project = store.create('Existing', 'Owned fixture')['project_id']
        store.commit(project, {'main.py': 'pass\n'}, 0)
    try:
        text = 'أضف دالة للجمع' if editing else 'برمج لي لعبة XO'
        rid = request_id()
        result = dispatcher.dispatch(text, rid, project)
        assert result['kind'] == 'project'
        job_id = result['job']['job_id']
        assert wait(jobs, job_id)['state'] == 'completed'
        replay = dispatcher.dispatch(text, rid, project)
        assert replay['job']['job_id'] == job_id
        assert len(system.backend.calls) == 2 and not desktop.calls
        assert jobs.get(job_id)['stage_results'][1]['stage'] == 'planning'
    finally:
        jobs.shutdown()
        store.close()


@pytest.mark.parametrize('raw,finish', [
    (json.dumps(PLAN), 'length'),
    ('This is a plan, but not structured.', 'stop'),
    (json.dumps({**PLAN, 'steps': ['One step']}), 'stop'),
    (json.dumps({**PLAN, 'files': ['../escape.py']}), 'stop'),
    (json.dumps({**PLAN, 'files': ['other.py']}), 'stop'),
])
@pytest.mark.parametrize('legacy', [False, True])
def test_invalid_mandatory_plan_blocks_coder_and_preserves_files(system, raw, finish, legacy):
    system.backend.plan_replies = [raw]
    system.backend.plan_finish = finish
    system.backend.text = GOOD
    payload = request(False)
    if legacy:
        result = InvoiceOrchestrator(system).process_request(payload)
        assert not result['success'] and result['files'] == []
        assert result['error_code'] == 'incomplete_plan'
        assert result['stages'][0]['status'] == 'failed'
    else:
        store = ProjectStore(system.settings.data_dir)
        jobs = ProjectJobs(store, system)
        project = store.create('Last good project', 'Owned fixture')['project_id']
        store.commit(project, {'main.py': 'ORIGINAL = 42\n'}, 0)
        before = store.get(project)
        payload.update(project_id=project, expected_revision=1, context_files=['main.py'])
        try:
            created = jobs.create(payload)
            result = wait(jobs, created['job']['job_id'])
            assert result['state'] == 'failed' and not result['saved_files']
            assert not result['draft_files']
            assert store.get(project)['files'] == before['files']
            assert store.get(project)['project_revision'] == 1
            planning = next(stage for stage in result['stage_results'] if stage['stage'] == 'planning')
            assert planning['status'] == 'failed' and not planning['result']['accepted']
        finally:
            jobs.shutdown()
            store.close()
    assert len(system.backend.calls) == 1, 'Invalid planning must not invoke the coder'
    assert system.backend.calls[0]['stream'] is False


@pytest.mark.parametrize('legacy', [False, True])
def test_constructed_false_object_cannot_bypass_server_invariant(system, legacy):
    # model_copy deliberately bypasses Pydantic validation; runtime must still plan.
    parsed = ProjectRequest.model_validate(request()).model_copy(update={'plan': False})
    system.backend.text = GOOD
    orchestrator = InvoiceOrchestrator(system)
    if legacy:
        assert orchestrator.process_request(parsed)['success']
    else:
        events = list(orchestrator.stream_files(parsed, cancel=threading.Event(),
                                               deadline=time.monotonic() + 5))
        stages = [event['stage'] for event in events if event['kind'] == 'stage']
        assert stages == ['planning', 'generating']
    assert len(system.backend.calls) == 2


def test_short_code_output_budget_cannot_truncate_the_planner_budget(system):
    system.backend.text = GOOD
    result = InvoiceOrchestrator(system).process_request({**request(), 'max_tokens': 64})
    assert result['success']
    assert [call['max_tokens'] for call in system.backend.calls] == [768, 64]


def test_explanation_dispatch_does_not_start_planning_or_generation(system):
    app, desktop, dispatcher = application(system)
    try:
        assert dispatcher.dispatch('اشرح كيف أبرمج لعبة XO', request_id()) == {'kind': 'chat'}
        assert not system.backend.calls and not desktop.calls
        assert not app.state.project_store.list()
    finally:
        app.state.project_jobs.shutdown()
        app.state.project_store.close()
