"""N079: authenticated management of user-configured MCP servers (private `/mcp` prefix)."""
import asyncio

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from src.core.mcp_client import McpError


class ServerAdd(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=32)
    command: list[str] = Field(min_length=1, max_length=40)
    env: dict[str, str] = Field(default_factory=dict, max_length=20)
    timeout_s: float = 20


class ToolToggle(BaseModel):
    model_config = ConfigDict(extra='forbid')
    enabled: bool


class ToolCall(BaseModel):
    model_config = ConfigDict(extra='forbid')
    tool: str = Field(min_length=1, max_length=64)
    arguments: dict = Field(default_factory=dict)


def attach_mcp(app, registry):
    def guarded(function, *args):
        try:
            return function(*args)
        except KeyError as exc:
            raise HTTPException(404, 'خادم MCP غير موجود') from exc
        except McpError as exc:
            raise HTTPException(exc.status, str(exc)) from exc

    @app.get('/mcp')
    async def listing():
        return {'servers': await asyncio.to_thread(registry.listing)}

    @app.post('/mcp/servers')
    async def add(req: ServerAdd):
        return await asyncio.to_thread(guarded, registry.add, req.name, req.command, req.env, req.timeout_s)

    @app.delete('/mcp/servers/{name}')
    async def remove(name: str):
        return await asyncio.to_thread(guarded, registry.remove, name)

    @app.post('/mcp/servers/{name}/connect')
    async def connect(name: str):
        return await asyncio.to_thread(guarded, registry.connect, name)

    @app.post('/mcp/servers/{name}/tools/{tool}')
    async def toggle(name: str, tool: str, req: ToolToggle):
        return await asyncio.to_thread(guarded, registry.set_enabled, name, tool, req.enabled)

    @app.post('/mcp/servers/{name}/call')
    async def call(name: str, req: ToolCall):
        return await asyncio.to_thread(guarded, registry.call, name, req.tool, req.arguments)
