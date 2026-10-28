"""Public v1 response/event contracts; request contracts live beside their routes."""
from typing import Any,Literal
from pydantic import BaseModel,ConfigDict,Field


class FileIndex(BaseModel):
    model_config=ConfigDict(extra='allow')
    path:str
    role:str
    size:int=Field(ge=0)
    mtime_ns:int=Field(ge=0)
    sha256:str=Field(pattern=r'^[a-f0-9]{64}$')


class ProjectMetadata(BaseModel):
    model_config=ConfigDict(extra='allow')
    schema_version:Literal[1]
    project_id:str=Field(pattern=r'^p_[a-f0-9]{32}$')
    display_name:str
    type:Literal['auto','static_web','python','other']
    purpose:str
    languages:list[str]
    entry_point:str|None
    project_revision:int=Field(ge=0)
    summary_revision:int=Field(ge=0)
    files:list[FileIndex]
    preview:dict[str,Any]
    validation:dict[str,Any]
    generation_status:str
    summary:str=''
    source_freshness:Literal['current','stale','unsafe','invalid']|None=None


class DraftFile(BaseModel):
    content:str
    complete:bool


class JobSnapshot(BaseModel):
    job_id:str=Field(pattern=r'^j_[a-f0-9]{32}$')
    project_id:str=Field(pattern=r'^p_[a-f0-9]{32}$')
    state:Literal['queued','planning','generating','validating','completed','failed','cancelled']
    last_seq:int=Field(ge=0)
    cancellation_requested:bool
    draft_files:dict[str,DraftFile]
    error:str|None
    created_at:str
    updated_at:str


class JobEvent(BaseModel):
    job_id:str=Field(pattern=r'^j_[a-f0-9]{32}$')
    project_id:str=Field(pattern=r'^p_[a-f0-9]{32}$')
    seq:int=Field(ge=1)
    type:Literal['job_started','stage_changed','file_started','file_delta','file_draft_complete','file_saved',
                 'validation_result','job_completed','job_failed','job_cancelled','snapshot']
    revision:int=Field(ge=0)
    data:dict[str,Any]


class ProjectCreated(BaseModel):
    project:ProjectMetadata
    job:JobSnapshot


class FileResponse(BaseModel):
    path:str
    content:str|None
    binary:bool
    sha256:str
    project_revision:int
    source_freshness:str


class APIError(BaseModel):
    error:dict[str,str]
