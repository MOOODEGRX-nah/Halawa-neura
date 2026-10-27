"""Explicit task handoff using the same coordinator as normal chat.

Generated code is validated as data, never executed with user privileges.
A passing artifact means the requested static checks passed, not runtime QA.
"""
import ast
import json
import re
import threading
import time
import uuid
from pathlib import Path, PurePosixPath
from pydantic import BaseModel, ConfigDict, Field
from src.core.neura_loop import InferenceError


class TaskInvoice(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    task_id: str
    task_type: str = 'coding'
    user_request: str = Field(min_length=1, max_length=30_000)
    language: str = 'auto'
    requirements: list[str] = Field(min_length=1, max_length=30)
    constraints: list[str] = Field(default_factory=list, max_length=30)
    context_summary: str = ''
    expected_output: str = 'Complete files in fenced blocks: ```python path/file.py'
    target_model: str


class ProjectRequest(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)
    user_request: str = Field(min_length=1, max_length=30_000)
    requirements: list[str] = Field(min_length=1, max_length=30)
    required_files: list[str] = Field(default_factory=list, max_length=30)
    required_python_symbols: list[str] = Field(default_factory=list, max_length=30)
    plan: bool = False
    max_tokens: int = Field(default=2000, ge=64, le=4096)


def extract_and_validate(text, request):
    files = {}
    for header, code in re.findall(r'^```([^\n]*)\n(.*?)^```\s*$', text, re.M | re.S):
        tokens = header.strip().split()
        name = tokens[-1] if tokens else ''
        if '.' not in name:
            name = {'python': 'main.py', 'javascript': 'main.js', 'html': 'index.html', 'css': 'style.css'}.get(name, '')
        path = PurePosixPath(name)
        if (not name or '\\' in name or path.is_absolute() or '..' in path.parts
                or any(part.startswith('.') for part in path.parts) or ':' in name):
            raise ValueError('Missing or unsafe generated file path')
        if name in files:
            raise ValueError(f'Duplicate generated file: {name}')
        if len(files) >= 40 or len(code.encode()) > 300_000:
            raise ValueError('Generated artifact exceeds limits')
        if not code.strip():
            raise ValueError(f'Empty file: {name}')
        files[name] = code.rstrip() + '\n'
    if not files:
        raise ValueError('No named code files were returned')
    symbols = set()
    for name, code in files.items():
        if name.endswith('.py'):
            tree = ast.parse(code, filename=name)
            symbols.update(node.name for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)))
        elif name.endswith('.json'):
            json.loads(code)
    missing_files = set(request.required_files) - files.keys()
    missing_symbols = set(request.required_python_symbols) - symbols
    if missing_files or missing_symbols:
        raise ValueError(f'Missing required files: {sorted(missing_files)}; symbols: {sorted(missing_symbols)}')
    return files


class InvoiceOrchestrator:
    def __init__(self, coordinator, max_fix_retries=1):
        self.coordinator = coordinator
        self.max_fix_retries = min(max(max_fix_retries, 0), 1)
        self.output_dir = coordinator.settings.data_dir / 'projects'

    def process_request(self, request, *, cancel=None, deadline=None):
        request = ProjectRequest.model_validate(request)
        cancel = cancel or threading.Event()
        deadline = deadline or time.monotonic() + self.coordinator.settings.timeout_s
        task_id = 'proj_' + uuid.uuid4().hex
        project_dir = self.output_dir / task_id
        project_dir.mkdir(parents=True, mode=0o700)
        invoice = TaskInvoice(task_id=task_id, user_request=request.user_request,
                              requirements=request.requirements,
                              constraints=['Do not run code or install dependencies', 'No paths outside the artifact directory'],
                              target_model=self.coordinator.router.get_model_id_for_tier('coder'))
        (project_dir / 'invoice.json').write_text(invoice.model_dump_json(indent=2), encoding='utf-8')
        result = {'project_id': task_id, 'success': False, 'validation': 'static', 'executed': False,
                  'stages': [], 'files': [], 'project_dir': str(project_dir)}
        started = time.monotonic()
        with self.coordinator.exclusive():
            try:
                plan_text = ''
                if request.plan:
                    plan = self.coordinator.complete([
                        {'role': 'system', 'content': 'Create a concise implementation plan for the supplied task invoice. Preserve all user requirements.'},
                        {'role': 'user', 'content': invoice.model_dump_json()}], tier='expert', cancel=cancel, deadline=deadline,
                        max_tokens=min(request.max_tokens, 1000), temperature=0.2)
                    plan_text = plan['choices'][0]['message']['content']
                    self._save_stage(project_dir, 'plan', plan, result)
                messages = [
                    {'role': 'system', 'content': 'Implement the task invoice. Return complete files only in fenced code blocks with language and relative filename on the opening line. Preserve code identifiers. Never claim to have run tests.'},
                    {'role': 'user', 'content': invoice.model_dump_json() + '\nImplementation plan:\n' + plan_text},
                ]
                for attempt in range(self.max_fix_retries + 1):
                    completion = self.coordinator.complete(messages, tier='coder', cancel=cancel, deadline=deadline,
                                                           max_tokens=request.max_tokens, temperature=0.2, top_p=0.9)
                    raw = completion['choices'][0]['message']['content']
                    self._save_stage(project_dir, f'execution_{attempt}', completion, result)
                    try:
                        if completion['choices'][0].get('finish_reason') == 'length':
                            raise ValueError('Completion was truncated; artifact not accepted')
                        files = extract_and_validate(raw, request)
                        for name, code in files.items():
                            destination = (project_dir / 'files' / name).resolve()
                            if not destination.is_relative_to((project_dir / 'files').resolve()):
                                raise ValueError('Generated path escaped artifact directory')
                            destination.parent.mkdir(parents=True, exist_ok=True)
                            destination.write_text(code, encoding='utf-8')
                        result.update(success=True, files=sorted(files), acceptance={
                            'syntax': 'passed', 'required_files': 'passed', 'required_python_symbols': 'passed',
                            'behavior': 'not_run', 'requirements': request.requirements})
                        break
                    except (ValueError, SyntaxError) as exc:
                        result['error'] = str(exc)
                        if attempt < self.max_fix_retries:
                            messages.extend([{'role': 'assistant', 'content': raw},
                                             {'role': 'user', 'content': f'Correct this validation failure and return every file completely: {exc}'}])
                if result['success']:
                    result.pop('error', None)
            except InferenceError as exc:
                result['error'] = str(exc)
                result['error_code'] = exc.code
                result['http_status'] = exc.status
            finally:
                result['total_time_s'] = round(time.monotonic() - started, 3)
                (project_dir / 'result.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return result

    @staticmethod
    def _save_stage(directory, stage, completion, result):
        message = completion['choices'][0]['message']
        raw = (message.get('reasoning_content', '') + '\n</think>\n' if message.get('reasoning_content') else '') + message['content']
        (directory / f'{stage}.txt').write_text(raw, encoding='utf-8')
        metadata = {k:v for k,v in completion.items() if k != 'choices'}
        metadata['finish_reason'] = completion['choices'][0].get('finish_reason')
        metadata['chat_template'] = 'gguf'
        (directory / f'{stage}.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
        result['stages'].append({'stage': stage, 'model': completion['model'], **metadata})
