import pytest
from src.backends.llama_cpp_backend import LlamaCppBackend


class HandlerFixture:
    def n_ctx(self):return 4096
    def create_completion(self,**kwargs):raise AssertionError('Measurement must never generate')
    def create_chat_completion(self,**kwargs):return self.create_completion(prompt=[10,20,30])


def test_formatter_token_measurement_restores_completion_method():
    backend=LlamaCppBackend();backend.model=HandlerFixture();original=backend.model.create_completion
    measured=backend.measure_messages([{'role':'user','content':'Not counted as characters'}],max_tokens=4096)
    assert measured['prompt_tokens']==3 and measured['effective_output_limit']==4093
    assert backend.model.create_completion==original
    assert 'create_completion' not in vars(backend.model)


def test_unsupported_handler_does_not_estimate_from_text():
    backend=LlamaCppBackend();backend.model=HandlerFixture();original=backend.model.create_completion
    backend.model.create_chat_completion=lambda **kwargs:backend.model.create_completion(prompt='unsupported')
    with pytest.raises(ValueError):backend.measure_messages([],max_tokens=1024)
    assert backend.model.create_completion==original
    assert 'create_completion' not in vars(backend.model)
