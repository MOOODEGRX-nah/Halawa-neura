import asyncio
from pydantic import BaseModel,ConfigDict,Field,ValidationError
from fastapi import HTTPException


class SkillCall(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=1,max_length=80)
    args:dict=Field(default_factory=dict)


class Authorize(SkillCall):
    remember:bool=False


class Execute(SkillCall):
    permission_id:str=Field(pattern=r'^g_[a-f0-9]{32}$')


class Permission(BaseModel):
    model_config=ConfigDict(extra='forbid')
    permission_id:str=Field(pattern=r'^g_[a-f0-9]{32}$')


def attach_skills(app,registry):
    async def invoke(function,*args):
        try:return await asyncio.to_thread(function,*args)
        except ValidationError as exc:raise HTTPException(422,'مدخلات المهارة غير صالحة') from exc

    @app.post('/skills/authorize')
    async def authorize(req:Authorize):
        return await invoke(registry.authorize,req.name,req.args,req.remember)

    @app.post('/skills/execute')
    async def execute(req:Execute):
        return await invoke(registry.execute,req.name,req.args,req.permission_id)

    @app.post('/skills/revoke')
    async def revoke(req:Permission):
        return await invoke(registry.revoke,req.permission_id)

    @app.get('/skills/grants')
    async def grants():return {'grants':await invoke(registry.grants)}

    @app.get('/skills/history')
    async def history():return {'history':await invoke(registry.history),'scope':'Neura-only'}

    @app.post('/projects/{project_id}/open-folder')
    async def open_project_folder(project_id:str,req:Permission):
        return await invoke(registry.execute,'open_folder',{'project_id':project_id},req.permission_id)
