import copy
import json
import os
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
TARGET = Path(os.environ.get('NEURA_TEST_TARGET_ROOT', ROOT)).resolve()
sys.path.insert(0, str(ROOT))  # Test helpers only; selected application comes first.
sys.path.insert(0, str(TARGET))
from src.runtime import Settings
from src.core.neura_loop import NeuraLoop


def pytest_sessionstart(session):
    """Refuse accidental source imports during an installed-target contract run."""
    import src.runtime
    origin = Path(src.runtime.__file__).resolve()
    if not origin.is_relative_to(TARGET):
        raise RuntimeError('Application import escaped the selected target: '+str(origin))
    report = os.environ.get('NEURA_VERIFY_IMPORT_REPORT')
    if report:
        Path(report).write_text(json.dumps({'executable':sys.executable,'runtime':str(origin),
            'target':str(TARGET),'test_source':str(ROOT)},indent=2))


@pytest.fixture(autouse=True)
def controlled_sensors(monkeypatch):
    """Complete controlled boundary: never read live sensors or initialize Vulkan.

    Individual sensor-policy tests may explicitly override these fixtures.
    This affects tests only, not the shipped application or real-model suites.
    """
    import psutil
    monkeypatch.setattr('src.core.project_jobs.check_candidate',lambda *a,**k:{'status':'fixture_not_run','environment':'fake browser boundary in deterministic tests'})
    monkeypatch.setattr('src.backends.residency.gpu_memory',lambda:None)
    if 'src.backend.api' in sys.modules:
        monkeypatch.setattr('src.backend.api.gpu_memory',lambda:None)
    monkeypatch.setattr(psutil,'cpu_percent',lambda *a,**k:0.0)
    monkeypatch.setattr(psutil,'virtual_memory',lambda:SimpleNamespace(
        total=32_000_000_000,used=8_000_000_000,available=24_000_000_000,
        free=24_000_000_000,percent=25.0))
    monkeypatch.setattr(psutil,'process_iter',lambda *a,**k:iter(()))
    def forbidden_probe():
        raise AssertionError('Controlled tests must not initialize Vulkan')
    monkeypatch.setattr('src.backends.devices.probe_devices',forbidden_probe)


class FakeBackend:
    def __init__(self):
        self.model = None
        self.loads = []
        self.calls = []
        self.unloads = 0
        self.text = 'answer'
        self.finish = 'stop'
        self.delay = 0
        self.failure = None
        self.replies = []
        self.plan_replies = []
        self.plan_finish = None
        self.entered = threading.Event()
        self.release = None

    def load(self, path, **kwargs):
        self.loads.append((path, kwargs))
        self.model = object()

    def unload(self):
        if self.model is not None:
            self.unloads += 1
        self.model = None

    def health_check(self):
        return {'status': 'loaded' if self.model is not None else 'unloaded'}

    def measure_messages(self,messages,max_tokens=1024,**options):
        return {'prompt_tokens':200,'context_size':4096,'requested_output_limit':max_tokens,
                'effective_output_limit':min(max_tokens,3896),'measurement':'controlled fixed token fixture, NOT native metrics'}

    def generate(self, *, messages, stream=False, **kwargs):
        self.calls.append({'messages': copy.deepcopy(messages), 'stream': stream, **kwargs})
        self.entered.set()
        if self.failure:
            raise self.failure
        criteria = kwargs.get('stopping_criteria')
        if self.release is not None:
            while not self.release.wait(.005):
                if criteria and criteria(None, None):
                    break
        if self.delay:
            end = time.monotonic() + self.delay
            while time.monotonic() < end:
                if criteria and criteria(None, None):
                    break
                time.sleep(.005)
        planning = messages[0]['content'].startswith('Return ONLY a compact JSON implementation plan')
        if planning:
            invoice = json.loads(messages[1]['content'])
            paths = invoice['expected_files'] or invoice['filename_hints'] or ['main.py']
            text = self.plan_replies.pop(0) if self.plan_replies else json.dumps({
                'steps': ['Inspect requirements and actual source.',
                          'Implement the requested changes.',
                          'Check source syntax and preserved requirements.'],
                'files': paths})
        else:
            text = self.replies.pop(0) if self.replies else self.text
        if callable(text):text=text(messages,kwargs)
        if messages[0]['content'].startswith('Return a bounded file patch'):
            import re
            packet=json.loads(messages[1]['content']);path=packet['path'];scope=packet.get('source_scope','')
            from src.core.project_stream import FileStream
            supplied={}
            if '```' in text:
                parser=FileStream(lambda *a:None,filename_hints=[i['path'] for i in packet['inventory']])
                try:parser.feed(text);supplied=parser.finish()
                except Exception:pass
            if path in supplied:
                replacement=supplied[path]
                text=json.dumps({'base_revision':packet['base_revision'],'path':path,'source_sha256':packet['source_sha256'],
                    'edits':[] if packet['new_file'] or replacement==scope.rstrip('\n') else [{'before':scope,'after':replacement}],
                    'new_content':replacement if packet['new_file'] else None})
            elif supplied and all(any(i['path']==p and i['selected'] for i in packet['inventory']) for p in supplied):
                text=json.dumps({'base_revision':packet['base_revision'],'path':path,'source_sha256':packet['source_sha256'],'edits':[],'new_content':None})
            elif supplied:
                wrong=next(iter(supplied))
                text=json.dumps({'base_revision':packet['base_revision'],'path':wrong,'source_sha256':packet['source_sha256'],'edits':[],'new_content':None})
        finish = self.plan_finish if planning and self.plan_finish is not None else self.finish
        if stream:
            def chunks():
                yield {'id': 'test', 'object': 'chat.completion.chunk', 'choices': [{'index':0,'delta':{'role':'assistant'},'finish_reason':None}]}
                for piece in [text[:3], text[3:]]:
                    if criteria and criteria(None, None):
                        return
                    yield {'id': 'test', 'object': 'chat.completion.chunk', 'choices': [{'index':0,'delta':{'content':piece},'finish_reason':None}]}
                yield {'id': 'test', 'object': 'chat.completion.chunk', 'choices': [{'index':0,'delta':{},'finish_reason':finish}]}
            return chunks()
        return {'id':'test', 'object':'chat.completion', 'created':1, 'model':'internal',
                'choices':[{'index':0,'message':{'role':'assistant','content':text},'finish_reason':finish}],
                'usage':{'prompt_tokens':5,'completion_tokens':3,'total_tokens':8}}


@pytest.fixture
def system(tmp_path,monkeypatch):
    # Fake inference must not depend on another application's live VRAM usage.
    # Tests exercising memory policy explicitly supply their own sensor samples.
    monkeypatch.setattr('src.backends.residency.gpu_memory',lambda:None)
    models = tmp_path / 'models'; models.mkdir()
    config = tmp_path / 'configs'; config.mkdir()
    registry = yaml.safe_load((ROOT / 'configs/models.yaml').read_text())
    for mid, info in registry['models'].items():
        if info.get('enabled'):
            (models / info['file']).write_bytes(b'GGUF')
            info['size_bytes'] = 4
            if info.get('projector'):
                (models / info['projector']).write_bytes(b'GGUF')
    (config / 'models.yaml').write_text(yaml.safe_dump(registry))
    (config / 'tiers.yaml').write_text((ROOT / 'configs/tiers.yaml').read_text())
    settings = Settings(config_dir=config, models_dir=models, data_dir=tmp_path / 'data', n_ctx=4096, token='test-token')
    backend = FakeBackend()
    loop = NeuraLoop(settings=settings, backend=backend)
    yield loop
    loop.shutdown()


@pytest.fixture
def messages():
    return [{'role':'system','content':'Keep technical names unchanged'},
            {'role':'user','content':'My name is Sami'},
            {'role':'assistant','content':'Hello Sami'},
            {'role':'user','content':'What is my name?'}]
