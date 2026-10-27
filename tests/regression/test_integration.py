from src.core.invoice_orchestrator import InvoiceOrchestrator


def test_chat_and_project_share_one_lifecycle(system,messages):
    system.complete(messages,tier='fast')
    system.backend.text='```python main.py\ndef add(a,b):\n    return a+b\n```'
    result=InvoiceOrchestrator(system).process_request({'user_request':'Write add','requirements':['return sum'],'required_files':['main.py'],'required_python_symbols':['add']})
    assert result['success'] and result['executed'] is False
    assert result['acceptance']['behavior']=='not_run'
    assert len(system.backend.loads)==2
    assert system.residency.current_model_id=='qwen3.5-9b-claude-distilled-q4'
