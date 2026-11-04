"""Authenticated, user-only dispatch; no client-supplied skill names or grants."""
import asyncio
from pydantic import BaseModel,ConfigDict,Field


class Dispatch(BaseModel):
    model_config=ConfigDict(extra='forbid')
    text:str=Field(min_length=1,max_length=30_000)
    request_id:str=Field(pattern=r'^r_[0-9]{13}_[a-f0-9]{32}$')
    active_project_id:str|None=Field(default=None,pattern=r'^p_[a-f0-9]{32}$')
    session_id:str|None=Field(default=None,pattern=r'^[A-Za-z0-9_-]{1,80}$')
    workspace_dirty:bool=False


class Choice(BaseModel):
    model_config=ConfigDict(extra='forbid')
    request_id:str=Field(pattern=r'^r_[0-9]{13}_[a-f0-9]{32}$')
    choice_id:str=Field(pattern=r'^o_[a-f0-9]{32}$')
    session_id:str|None=Field(default=None,pattern=r'^[A-Za-z0-9_-]{1,80}$')


class ProjectContext(BaseModel):
    model_config=ConfigDict(extra='forbid')
    session_id:str=Field(pattern=r'^[A-Za-z0-9_-]{1,80}$')
    project_id:str=Field(pattern=r'^p_[a-f0-9]{32}$')


def attach_chat(app,dispatcher):
    @app.post('/chat/context')
    async def bind(req:ProjectContext):
        return await asyncio.to_thread(dispatcher.bind_project,req.session_id,req.project_id)

    @app.get('/chat/status/{session_id}')
    async def status(session_id:str):
        dispatcher.targets.validate(session_id)
        return await asyncio.to_thread(dispatcher.conversations.status,session_id,dispatcher.jobs)

    @app.get('/chat/context/{session_id}')
    async def context(session_id:str):
        dispatcher.targets.validate(session_id)
        return dispatcher.conversations.get(session_id) or {}

    @app.post('/chat/dispatch')
    async def dispatch(req:Dispatch):
        return await asyncio.to_thread(dispatcher.dispatch,req.text,req.request_id,req.active_project_id,req.session_id,req.workspace_dirty)

    @app.post('/chat/choose')
    async def choose(req:Choice):
        return await asyncio.to_thread(dispatcher.choose,req.request_id,req.choice_id,req.session_id)

    @app.get('/chat/requests/{request_id}')
    async def snapshot(request_id:str,session_id:str|None=None):
        return await asyncio.to_thread(dispatcher.get,request_id,session_id)
