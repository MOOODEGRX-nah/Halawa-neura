"""Run explicit HTTP + GPU acceptance against a temporary local server."""
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import httpx
ROOT=Path(__file__).resolve().parents[1]

if __name__=='__main__':
    output=Path(sys.argv[1]).resolve()
    report={}
    with tempfile.TemporaryDirectory(prefix='neura-api-check-') as directory:
        data=Path(directory)
        with (data/'server.log').open('w') as log:
            process=subprocess.Popen([sys.executable,'-m','uvicorn','src.backend.api:app','--host','127.0.0.1','--port','8018','--workers','1','--no-proxy-headers'],
                cwd=ROOT,env={**os.environ,'NEURA_DATA_DIR':str(data)},stdout=log,stderr=log)
        try:
            with httpx.Client(base_url='http://127.0.0.1:8018',timeout=30,trust_env=False) as client:
                for _ in range(100):
                    try:
                        if client.get('/health').is_success:break
                    except httpx.TransportError:pass
                    if process.poll() is not None:raise RuntimeError('Test server exited')
                    time.sleep(.1)
                client.headers['X-Neura-Token']=(data/'.api-token').read_text().strip()
                route=client.post('/route',json={'text':'Count from 1 to 100','tier':'fast'})
                report['route']=route.json()
                report['route_did_not_load']=client.get('/health').json()['current_model'] is None
                started=time.monotonic();content=''
                with client.stream('POST','/v1/chat/completions',json={'messages':[{'role':'user','content':'Count from 1 to 300, one number per line.'}],'tier':'fast','stream':True,'max_tokens':1000}) as response:
                    response.raise_for_status()
                    report['stream_model']=response.headers['x-neura-model']
                    for line in response.iter_lines():
                        if not line.startswith('data: ') or line=='data: [DONE]':continue
                        chunk=json.loads(line[6:])
                        for choice in chunk.get('choices',[]):content+=choice.get('delta',{}).get('content','') or ''
                        if len(content)>10:
                            report['first_content_s']=time.monotonic()-started
                            report['partial_content']=content
                            break
                # Closing the stream must cooperatively free the coordinator lock.
                for _ in range(100):
                    health=client.get('/health').json()
                    if health['phase']=='idle':break
                    time.sleep(.05)
                report['cancel_released_lock']=health['phase']=='idle'
                followup=client.post('/v1/chat/completions',json={'messages':[{'role':'user','content':'Say OK only.'}],'tier':'fast','max_tokens':16})
                report['followup_status']=followup.status_code
                report['followup']=followup.json()
                report['stats']=client.get('/stats').json()
                report['passed']=all([report['route_did_not_load'],report['cancel_released_lock'],followup.is_success,bool(content)])
        except Exception as exc:
            report.update(passed=False,error=str(exc))
        finally:
            process.terminate()
            try:process.wait(timeout=15)
            except subprocess.TimeoutExpired:process.kill();process.wait()
            output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
            print('passed',report.get('passed'),report.get('error',''))
