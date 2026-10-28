import threading
import time
import pytest
from src.core.neura_loop import InferenceError


def test_history_and_generation_options(system,messages):
    result=system.complete(messages,max_tokens=34,temperature=.3,top_p=.8)
    assert result['model']=='qwen3.5-9b-q4'
    assert system.backend.calls[0]['messages']==messages
    assert system.backend.calls[0]['max_tokens']==34
    assert result['choices'][0]['finish_reason']=='stop'


def test_model_switches_update_residency(system,messages):
    system.complete(messages,tier='fast')
    assert system.residency.current_model_id==system.current_model_id=='gemma-4-e4b-q4'
    system.complete(messages,tier='expert')
    system.complete(messages,tier='coder')
    assert len(system.backend.loads)==2
    assert system.backend.unloads==1
    system.shutdown()
    assert system.residency.current_model_id is None


def test_empty_response_is_failure(system,messages):
    system.backend.text=' '
    with pytest.raises(InferenceError) as exc:
        system.complete(messages)
    assert exc.value.status==502 and exc.value.code=='empty_completion'


def test_load_failure_clears_registration(system,messages,monkeypatch):
    system.complete(messages,tier='fast')
    def broken(*a,**kw):raise ValueError('bad model')
    monkeypatch.setattr(system.backend,'load',broken)
    with pytest.raises(InferenceError,match='load failed'):
        system.complete(messages,tier='daily')
    assert system.current_model_id is None
    assert system.residency.current_model_id is None


def test_cancel_before_load(system,messages):
    event=threading.Event();event.set()
    with pytest.raises(InferenceError) as exc:
        system.complete(messages,cancel=event)
    assert exc.value.code=='cancelled' and not system.backend.loads


def test_timeout_cooperates_with_backend(system,messages):
    system.backend.delay=.4
    with pytest.raises(InferenceError) as exc:
        system.complete(messages,deadline=time.monotonic()+.03)
    assert exc.value.status==504
    assert system.phase=='idle'


def test_stream_has_native_chunks_and_finish_reason(system,messages):
    system.backend.finish='length'
    result=list(system.stream(messages))
    assert ''.join(c['choices'][0]['delta'].get('content','') for c in result)=='answer'
    assert result[-1]['choices'][0]['finish_reason']=='length'
    assert system.backend.calls[0]['stream']


def test_stream_cancel_releases_model_lock(system,messages):
    event=threading.Event();stream=system.stream(messages,cancel=event)
    next(stream);event.set()
    with pytest.raises(InferenceError,match='cancelled'):
        next(stream)
    assert system.phase=='idle'
    assert system.complete(messages)['tier']=='daily'


def test_busy_request_does_not_corrupt_model(system,messages):
    system.backend.release=threading.Event()
    errors=[]
    def work():
        try:system.complete(messages)
        except Exception as exc:errors.append(exc)
    thread=threading.Thread(target=work);thread.start()
    assert system.backend.entered.wait(1)
    try:
        with pytest.raises(InferenceError) as exc:system.complete(messages,tier='fast')
        assert exc.value.status==409
        assert len(system.backend.loads)==1
    finally:
        system.backend.release.set();thread.join(2)
    assert not errors


def test_metrics_count_real_requests_and_do_not_invent_stream_tokens(system,messages):
    system.complete(messages)
    list(system.stream(messages))
    snapshot=system.metrics_snapshot()
    assert snapshot['totals']['requests']==2
    assert snapshot['totals']['output_tokens']==3
    assert snapshot['totals']['unknown_usage_requests']==1
    assert snapshot['recent'][0]['output'] is None
    system.backend.failure=ValueError('broken')
    with pytest.raises(InferenceError):system.complete(messages)
    assert system.metrics_snapshot()['totals']['errors']==1


def test_model_switch_waits_for_measured_vram_release(system,messages,monkeypatch):
    system.complete(messages,tier='fast')
    original=system.residency.can_load
    reads=[]
    def delayed_release(*args,**kwargs):
        reads.append(system.residency.current_model_id)
        if len(reads)==1:return False,'native buffers were just released'
        return original(*args,**kwargs)
    monkeypatch.setattr(system.residency,'can_load',delayed_release)
    system._load('qwen3.5-9b-q4','daily')
    assert len(reads)>=2 and all(value is None for value in reads)
    assert system.current_model_id=='qwen3.5-9b-q4'
    assert system.backend.unloads==1
