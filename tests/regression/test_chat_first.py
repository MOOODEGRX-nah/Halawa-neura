"""Chat navigation resolves saved projects without creating jobs or granting desktop access."""
import pytest
from tests.regression.test_chat_dispatch import application,request_id


@pytest.mark.parametrize('text',['عدل مشروع السيرة الذاتية','عدّل موقع السيرة الذاتية واجعل العنوان أزرق','افتح مشروع السيرة الذاتية','edit project السيرة الذاتية'])
def test_named_existing_project_opens_workspace_without_generation(system,text):
    app,desktop,dispatch=application(system);store=app.state.project_store
    project=store.create('موقع السيرة الذاتية','CV')['project_id']
    store.commit(project,{'index.html':'<h1>CV</h1>'},0)
    rid=request_id();result=dispatch.dispatch(text,rid)
    assert result['kind']=='workspace' and result['project_id']==project
    assert dispatch.dispatch(text,rid)==result
    assert len(store.list())==1 and store.get(project)['project_revision']==1
    assert not desktop.calls and not system.backend.calls
    store.close()


def test_active_edit_and_ambiguous_saved_project_use_bound_choices(system):
    app,desktop,dispatch=application(system);store=app.state.project_store
    first=store.create('سيرة أولى','CV')['project_id'];second=store.create('سيرة ثانية','CV')['project_id']
    text='عدل هذا المشروع واجعل الخلفية زرقاء'
    assert dispatch.dispatch(text,request_id(),first)['project_id']==first
    rid=request_id();result=dispatch.dispatch('عدل المشروع',rid)
    assert result['kind']=='clarification' and len(result['choices'])==2
    selected=dispatch.choose(rid,result['choices'][1]['id'])
    assert selected['kind']=='workspace' and selected['project_id'] in (first,second)
    assert dispatch.choose(rid,result['choices'][1]['id'])==selected
    assert not desktop.calls and not system.backend.calls
    store.close()


@pytest.mark.parametrize('text',['كيف أعدل مشروع السيرة الذاتية؟','لا تعدل هذا المشروع','"عدل المشروع"','اشرح طريقة تعديل المشروع'])
def test_edit_explanations_remain_chat(system,text):
    app,desktop,dispatch=application(system)
    assert dispatch.dispatch(text,request_id())=={'kind':'chat'}
    assert not desktop.calls and not system.backend.calls
    app.state.project_store.close()


def test_empty_project_request_has_specific_response(system):
    app,desktop,dispatch=application(system)
    result=dispatch.dispatch('عدل المشروع',request_id())
    assert result['kind']=='action' and 'لا توجد مشاريع' in result['result']['message']
    app.state.project_store.close()
