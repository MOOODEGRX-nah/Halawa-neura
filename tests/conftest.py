import copy
import sys
import threading
import time
from pathlib import Path
import pytest
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.runtime import Settings
from src.core.neura_loop import NeuraLoop


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
        text = self.replies.pop(0) if self.replies else self.text
        if stream:
            def chunks():
                yield {'id': 'test', 'object': 'chat.completion.chunk', 'choices': [{'index':0,'delta':{'role':'assistant'},'finish_reason':None}]}
                for piece in [text[:3], text[3:]]:
                    if criteria and criteria(None, None):
                        return
                    yield {'id': 'test', 'object': 'chat.completion.chunk', 'choices': [{'index':0,'delta':{'content':piece},'finish_reason':None}]}
                yield {'id': 'test', 'object': 'chat.completion.chunk', 'choices': [{'index':0,'delta':{},'finish_reason':self.finish}]}
            return chunks()
        return {'id':'test', 'object':'chat.completion', 'created':1, 'model':'internal',
                'choices':[{'index':0,'message':{'role':'assistant','content':text},'finish_reason':self.finish}],
                'usage':{'prompt_tokens':5,'completion_tokens':3,'total_tokens':8}}


@pytest.fixture
def system(tmp_path):
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
