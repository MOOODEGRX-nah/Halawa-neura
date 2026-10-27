import json
from pathlib import Path
import pytest
from src.core.invoice_orchestrator import ProjectRequest, InvoiceOrchestrator, extract_and_validate

REQUEST={'user_request':'create add','requirements':['sum two inputs'],'required_files':['main.py'],'required_python_symbols':['add']}
GOOD='```python main.py\ndef add(a,b):\n    return a+b\n```'

@pytest.mark.parametrize('text',[
 'plain prose',
 '```python ../bad.py\nprint(1)\n```',
 '```python /tmp/bad.py\nprint(1)\n```',
 '```python main.py\ndef broken(:\n```',
 GOOD+'\n'+GOOD,
 '```python main.py\ndef subtract(a,b):return a-b\n```',
])
def test_invalid_artifacts_are_rejected(text):
    with pytest.raises((ValueError,SyntaxError)):
        extract_and_validate(text,ProjectRequest(**REQUEST))


def test_handoff_and_bounded_retry(system):
    system.backend.replies=['```python main.py\ndef broken(:\n```',GOOD]
    result=InvoiceOrchestrator(system).process_request(REQUEST)
    assert result['success'] and len(system.backend.calls)==2
    assert len(result['stages'])==2
    assert not result['executed']
    root=Path(result['project_dir'])
    assert (root/'files/main.py').is_file()
    assert (root/'execution_0.txt').is_file()
    assert json.loads((root/'execution_1.json').read_text())['finish_reason']=='stop'


def test_no_extra_models_for_simple_task(system):
    system.backend.text=GOOD
    result=InvoiceOrchestrator(system).process_request(REQUEST)
    assert result['success'] and len(system.backend.calls)==1
    assert len(system.backend.loads)==1


def test_truncation_never_passes(system):
    system.backend.text=GOOD;system.backend.finish='length'
    result=InvoiceOrchestrator(system,max_fix_retries=0).process_request(REQUEST)
    assert not result['success'] and result['files']==[]
    assert 'truncated' in result['error']


def test_generated_code_is_never_executed(system,tmp_path):
    marker=tmp_path/'executed'
    system.backend.text=f'```python main.py\nfrom pathlib import Path\nPath({str(marker)!r}).touch()\ndef add(a,b):return a+b\n```'
    result=InvoiceOrchestrator(system).process_request(REQUEST)
    assert result['success'] and not marker.exists()
