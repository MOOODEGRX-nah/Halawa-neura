from src.backends.llama_cpp_backend import LlamaCppBackend


def test_reasoning_filter_is_specific_and_preserves_technical_text():
    chunks=[]
    for text in ['reasoning </thi','nk>\n```python\n','import os\n```']:
        chunks.append({'choices':[{'delta':{'content':text},'finish_reason':None}]})
    chunks.append({'choices':[{'delta':{},'finish_reason':'stop'}]})
    result=list(LlamaCppBackend._answer_stream(iter(chunks),'</think>'))
    text=''.join(c['choices'][0]['delta'].get('content','') for c in result)
    assert text=='```python\nimport os\n```'
    assert result[-1]['choices'][0]['finish_reason']=='stop'


def test_reasoning_filter_preserves_content_without_marker():
    chunks=iter([{'choices':[{'delta':{'content':'plain answer'},'finish_reason':None}]},
                 {'choices':[{'delta':{},'finish_reason':'stop'}]}])
    text=''.join(c['choices'][0]['delta'].get('content','') for c in LlamaCppBackend._answer_stream(chunks,'</think>'))
    assert text=='plain answer'
