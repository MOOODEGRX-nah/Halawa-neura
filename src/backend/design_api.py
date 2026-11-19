"""Authenticated design studio API (under the private /designs prefix)."""
import asyncio
import threading
import time

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from src.core.design_store import DesignError, Document, TEMPLATES, ai_messages, apply_ai_changes, export_site


class Create(BaseModel):
    model_config = ConfigDict(extra='forbid')
    template: str = Field(pattern=r'^[a-z-]{2,20}$')
    title: str | None = Field(default=None, max_length=120)


class Save(BaseModel):
    model_config = ConfigDict(extra='forbid')
    base_revision: int = Field(ge=1)
    document: dict


class AIEdit(BaseModel):
    model_config = ConfigDict(extra='forbid')
    base_revision: int = Field(ge=1)
    node_ids: list[str] = Field(min_length=1, max_length=30)
    instruction: str = Field(min_length=2, max_length=1000)


class Restore(BaseModel):
    model_config = ConfigDict(extra='forbid')
    base_revision: int = Field(ge=1)
    revision: int = Field(ge=1)


class Export(BaseModel):
    model_config = ConfigDict(extra='forbid')
    base_revision: int = Field(ge=1)
    new_project: bool = False


def attach_designs(app, designs, projects, coordinator):
    def guarded(function, *args):
        try:
            return function(*args)
        except KeyError as exc:
            raise HTTPException(404, 'التصميم غير موجود') from exc
        except DesignError as exc:
            raise HTTPException(exc.status, str(exc)) from exc
        except ValidationError as exc:
            raise HTTPException(422, 'التصميم غير صالح: ' + '; '.join(e['msg'] for e in exc.errors()[:3])) from exc

    @app.get('/designs')
    async def list_designs():
        return {'designs': await asyncio.to_thread(designs.list), 'templates': TEMPLATES}

    @app.post('/designs')
    async def create(req: Create):
        return await asyncio.to_thread(guarded, designs.create, req.template, req.title)

    @app.get('/designs/{design_id}')
    async def get(design_id: str):
        return await asyncio.to_thread(guarded, designs.get, design_id)

    @app.put('/designs/{design_id}')
    async def save(design_id: str, req: Save):
        return await asyncio.to_thread(guarded, designs.save, design_id, req.document, req.base_revision)

    @app.delete('/designs/{design_id}')
    async def delete(design_id: str):
        return await asyncio.to_thread(guarded, designs.delete, design_id)

    @app.get('/designs/{design_id}/revisions')
    async def revisions(design_id: str):
        return {'revisions': await asyncio.to_thread(guarded, designs.revisions, design_id)}

    @app.post('/designs/{design_id}/restore')
    async def restore(design_id: str, req: Restore):
        return await asyncio.to_thread(guarded, designs.restore, design_id, req.revision, req.base_revision)

    @app.post('/designs/{design_id}/ai')
    async def ai_edit(design_id: str, req: AIEdit):
        def run():
            current = designs.get(design_id)
            if current['revision'] != req.base_revision:
                error = DesignError('تغير التصميم منذ التحديد؛ لم يُرسل طلب للنموذج.'); error.status = 409; raise error
            document = Document.model_validate(current['document'])
            ids = {n.id for n in document.nodes}
            if not set(req.node_ids) <= ids:
                raise DesignError('بعض العناصر المحددة غير موجودة')
            reply = coordinator.complete(ai_messages(document, set(req.node_ids), req.instruction), tier='daily', max_tokens=900, temperature=.3, top_p=.9,
                                         response_format={'type': 'json_object'}, cancel=threading.Event(), deadline=time.monotonic() + 180)
            choice = reply['choices'][0]
            if choice.get('finish_reason') != 'stop':
                raise DesignError('رد النموذج غير مكتمل؛ لم يتغير التصميم')
            updated, touched, note = apply_ai_changes(document, set(req.node_ids), choice['message']['content'])
            saved = designs.save(design_id, updated.model_dump(), req.base_revision, 'ai')
            return {**saved, 'changed_nodes': touched, 'note': note, 'model': reply.get('model')}
        return await asyncio.to_thread(guarded, run)

    @app.post('/designs/{design_id}/export-site')
    async def export(design_id: str, req: Export):
        def run():
            current = designs.get(design_id)
            if current['revision'] != req.base_revision:
                error = DesignError('احفظ التصميم أولًا؛ المراجعة المعروضة ليست الأحدث.'); error.status = 409; raise error
            files = export_site(current['document'], design_id, current['revision'])
            project_id = None if req.new_project else current['project_id']
            if project_id:
                try:
                    revision = projects.get(project_id)['project_revision']
                except Exception:
                    project_id = None
            if project_id and revision != current['project_revision']:
                # The site was edited after the last export: never overwrite that code silently.
                error = DesignError('عُدّل كود الموقع بعد آخر تصدير (المراجعة ' + str(revision) + '). لم أكتب فوقه؛ صدّر كمشروع جديد أو انسخ تعديلاتك أولًا.')
                error.status = 409
                raise error
            if not project_id:
                project_id = projects.create(current['title'], 'موقع مُصدَّر من استوديو التصميم')['project_id']
                revision = 0
            committed = projects.commit(project_id, files, revision)
            new_revision = committed.get('project_revision', revision + 1) if isinstance(committed, dict) else revision + 1
            designs.link_project(design_id, project_id, new_revision)
            return {'project_id': project_id, 'project_revision': new_revision, 'files': sorted(files), 'design_revision': current['revision'],
                    'message': 'صُدّر التصميم كموقع في مشاريعك (المراجعة ' + str(new_revision) + '). التعديلات اليدوية على كود الموقع لا تعود إلى التصميم، ولن يُكتب فوقها.'}
        return await asyncio.to_thread(guarded, run)
