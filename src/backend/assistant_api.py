"""Authenticated management API for the assistant's memories, reminders and preferences.

Every route is under the private `/assistant` prefix, so the local boundary requires the
desktop token. Content from projects, previews or the model has no path to these writes.
"""
import asyncio
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.core.assistant_store import AssistantError


class MemoryText(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=500)


class ReminderCreate(BaseModel):
    model_config = ConfigDict(extra='forbid')
    text: str = Field(min_length=1, max_length=300)
    due: float = Field(gt=0)


class Preferences(BaseModel):
    model_config = ConfigDict(extra='forbid')
    city: str | None = Field(default=None, max_length=80)
    timezone: str | None = Field(default=None, max_length=80)
    desktop_notifications: bool | None = None
    speak_reminders: bool | None = None
    use_memory_in_chat: bool | None = None
    persona: str | None = Field(default=None, max_length=600)


class KnowledgeUpload(BaseModel):
    model_config = ConfigDict(extra='forbid')
    filename: str = Field(min_length=1, max_length=200)
    text: str = Field(min_length=1, max_length=2_000_000)


class MemoryImport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    format: str
    version: int
    memories: list[dict] = Field(max_length=200)


def attach_assistant(app, assistant):
    store = assistant.store

    def guarded(function, *args):
        try:
            return function(*args)
        except KeyError as exc:
            raise HTTPException(404, 'العنصر غير موجود') from exc
        except AssistantError as exc:
            raise HTTPException(exc.status, str(exc)) from exc

    @app.get('/assistant/memories')
    async def memories():
        return {'memories': await asyncio.to_thread(store.memories)}

    @app.post('/assistant/memories')
    async def add_memory(req: MemoryText):
        return await asyncio.to_thread(guarded, store.remember, req.text, 'user_settings')

    @app.put('/assistant/memories/{memory_id}')
    async def edit_memory(memory_id: str, req: MemoryText):
        return await asyncio.to_thread(guarded, store.update_memory, memory_id, req.text)

    @app.delete('/assistant/memories/{memory_id}')
    async def delete_memory(memory_id: str):
        return await asyncio.to_thread(guarded, store.forget, memory_id)

    @app.delete('/assistant/memories')
    async def delete_all_memories():
        return {'deleted': await asyncio.to_thread(store.forget_all)}

    @app.get('/assistant/memories/export')
    async def export_memories():
        return await asyncio.to_thread(store.export_memories)

    @app.post('/assistant/memories/import')
    async def import_memories(req: MemoryImport):
        return await asyncio.to_thread(guarded, store.import_memories, req.model_dump())

    @app.get('/assistant/reminders')
    async def reminders(include_done: bool = False):
        states = ('pending', 'fired', 'cancelled') if include_done else ('pending',)
        return {'reminders': await asyncio.to_thread(store.reminders, states), 'timezone': assistant.timezone,
                'notifications': assistant.notifier.available()}

    @app.post('/assistant/reminders')
    async def add_reminder(req: ReminderCreate):
        if req.due <= assistant.clock():
            raise HTTPException(400, 'وقت التذكير مضى بالفعل')
        return await asyncio.to_thread(guarded, store.add_reminder, req.text, req.due, assistant.timezone)

    @app.delete('/assistant/reminders/{reminder_id}')
    async def cancel_reminder(reminder_id: str):
        return await asyncio.to_thread(guarded, store.cancel_reminder, reminder_id)

    @app.get('/assistant/events')
    async def events(after: int = 0):
        await asyncio.to_thread(assistant.deliver_due)
        return await asyncio.to_thread(store.events, after)

    @app.get('/assistant/knowledge')
    async def knowledge():
        kb = assistant.knowledge
        return {'documents': await asyncio.to_thread(kb.documents) if kb else [], 'available': bool(kb and kb.embedder.available)}

    @app.post('/assistant/knowledge')
    async def add_knowledge(req: KnowledgeUpload):
        from src.core.knowledge import KnowledgeError, to_text
        if not assistant.knowledge:
            raise HTTPException(501, 'قاعدة المعرفة غير مفعّلة')
        def run():
            try:
                return assistant.knowledge.add(req.filename, to_text(req.filename, req.text), 'upload')
            except KnowledgeError as exc:
                raise HTTPException(exc.status, str(exc)) from exc
        return await asyncio.to_thread(run)

    @app.delete('/assistant/knowledge/{document_id}')
    async def delete_knowledge(document_id: str):
        if not assistant.knowledge:
            raise HTTPException(501, 'قاعدة المعرفة غير مفعّلة')
        return await asyncio.to_thread(guarded, assistant.knowledge.delete, document_id)

    @app.get('/assistant/preferences')
    async def preferences():
        return await asyncio.to_thread(store.preferences)

    @app.put('/assistant/preferences')
    async def update_preferences(req: Preferences):
        values = {k: v for k, v in req.model_dump().items() if v is not None}
        return await asyncio.to_thread(guarded, store.preferences, values)
