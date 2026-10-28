"""Additive authenticated workspace routes. Legacy /projects POST remains."""
import asyncio
import json
from pydantic import BaseModel, ConfigDict, Field
from fastapi import Request, HTTPException
from fastapi.responses import Response, StreamingResponse
from src.core.project_files import ProjectError
from src.core.project_jobs import TERMINAL
from src.core.project_contracts import ProjectMetadata,JobSnapshot,FileResponse


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=False)


class SaveFile(Strict):
    path: str = Field(min_length=1, max_length=240)
    content: str = Field(max_length=300_000)
    expected_revision: int = Field(ge=0)
    expected_sha256: str = Field(pattern=r'^[a-f0-9]{64}$')


class Revision(Strict):
    expected_revision: int = Field(ge=0)


class Question(Strict):
    question: str = Field(min_length=1, max_length=2000)


class Context(Strict):
    paths: list[str] = Field(min_length=1, max_length=8)


class Preferences(Strict):
    swapped: bool
    ratio: int = Field(ge=20, le=80)
    last_project: str | None = Field(default=None, pattern=r'^p_[a-f0-9]{32}$')


class LegacyImport(Strict):
    legacy_id:str=Field(pattern=r'^proj_[a-f0-9]{32}$')


def attach_projects(app, store, jobs, preview):
    from src.core.legacy_projects import LegacyProjects
    legacy=LegacyProjects(store)
    @app.get('/workspace/schema')
    async def public_schema():
        from src.core.project_contracts import JobEvent,ProjectCreated,APIError
        from src.core.project_jobs import WorkspaceRequest
        models=[WorkspaceRequest,SaveFile,Revision,Question,Context,ProjectMetadata,JobSnapshot,JobEvent,ProjectCreated,FileResponse,APIError]
        return {'version':1,'schemas':{model.__name__:model.model_json_schema() for model in models}}
    @app.get('/workspace/preferences')
    async def get_preferences():
        return await asyncio.to_thread(store.preferences)

    @app.put('/workspace/preferences')
    async def save_preferences(req: Preferences):
        return await asyncio.to_thread(store.preferences, req.model_dump())

    @app.exception_handler(ProjectError)
    async def project_error(request, exc):
        from src.backend.api import error_response
        return error_response(str(exc), exc.status, 'revision_conflict' if exc.status == 409 else 'project_error')

    @app.get('/projects')
    async def list_projects():
        return {'projects': await asyncio.to_thread(store.list)}

    @app.get('/projects/legacy')
    async def list_legacy():
        return {'projects':await asyncio.to_thread(legacy.list)}

    @app.post('/projects/import-legacy')
    async def import_legacy(req:LegacyImport):
        return await asyncio.to_thread(legacy.copy,req.legacy_id)

    @app.get('/projects/{project_id}',response_model=ProjectMetadata)
    async def get_project(project_id: str):
        return await asyncio.to_thread(store.get, project_id)

    @app.get('/projects/{project_id}/file',response_model=FileResponse)
    async def read_file(project_id: str, path: str):
        return await asyncio.to_thread(store.read, project_id, path)

    @app.put('/projects/{project_id}/file')
    async def save_file(project_id: str, req: SaveFile):
        return await asyncio.to_thread(store.save_file, project_id, req.path, req.content, req.expected_revision, req.expected_sha256)

    @app.post('/projects/{project_id}/reindex')
    async def rebuild(project_id: str, req: Revision):
        return await asyncio.to_thread(store.rebuild, project_id, req.expected_revision)

    @app.post('/projects/{project_id}/question')
    async def project_question(project_id: str, req: Question):
        return await asyncio.to_thread(store.answer, project_id, req.question)

    @app.post('/projects/{project_id}/context')
    async def project_context(project_id: str, req: Context):
        meta = await asyncio.to_thread(store.get, project_id)
        if meta['source_freshness'] != 'current':
            from src.core.project_files import Conflict
            raise Conflict('راجع تغييرات الملفات وحدّث الفهرس قبل استخدام السياق')
        files = [await asyncio.to_thread(store.read, project_id, path) for path in req.paths]
        if any(f['binary'] for f in files):raise HTTPException(422,'اختر ملفات مصدر نصية للسياق')
        if sum(len(f['content'].encode()) for f in files) > 60_000:
            raise HTTPException(413, 'اختر ملفات أقل للسياق')
        return {'project_id': project_id, 'revision': meta['project_revision'], 'files': files}

    @app.get('/projects/{project_id}/export')
    async def export_project(project_id: str):
        data = await asyncio.to_thread(store.export, project_id)
        return Response(data, media_type='application/zip', headers={'Content-Disposition': f'attachment; filename="{project_id}.zip"'})

    @app.post('/projects/{project_id}/preview')
    async def project_preview(project_id: str, req: Revision, request: Request):
        return await asyncio.to_thread(preview.issue, project_id, str(request.base_url).rstrip('/'), req.expected_revision)

    @app.get('/project-jobs/{job_id}',response_model=JobSnapshot)
    async def get_job(job_id: str):
        return await asyncio.to_thread(jobs.get, job_id)

    @app.post('/project-jobs/{job_id}/cancel')
    async def cancel_job(job_id: str):
        return await asyncio.to_thread(jobs.cancel, job_id)

    @app.get('/project-jobs/{job_id}/events')
    async def job_events(job_id: str, request: Request, after: int = 0):
        try: after = int(request.headers.get('last-event-id', after))
        except ValueError as exc: raise HTTPException(400, 'مؤشر أحداث غير صالح') from exc
        await asyncio.to_thread(jobs.events, job_id, after)
        async def stream():
            cursor = after
            heartbeat = 0
            while not await request.is_disconnected():
                events = await asyncio.to_thread(jobs.events, job_id, cursor)
                for event in events:
                    cursor = event['seq']
                    yield 'id: ' + str(cursor) + '\nevent: ' + event['type'] + '\ndata: ' + json.dumps(event, ensure_ascii=False) + '\n\n'
                job = await asyncio.to_thread(jobs.get, job_id)
                if job['state'] in TERMINAL and cursor >= job['last_seq']: break
                heartbeat += 1
                if heartbeat >= 150:
                    yield ': heartbeat\n\n'; heartbeat = 0
                await asyncio.sleep(.1)
        return StreamingResponse(stream(), media_type='text/event-stream', headers={'X-Accel-Buffering': 'no', 'Cache-Control': 'no-store'})
