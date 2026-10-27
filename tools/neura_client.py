"""Local CLI client. The server must already be running; no independent model load."""
import argparse
import json
import sys
from pathlib import Path
import httpx
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.runtime import Settings

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('text')
    parser.add_argument('--tier',choices=['fast','daily','expert','vision','coder'])
    parser.add_argument('--stream',action='store_true')
    parser.add_argument('--project',action='store_true')
    parser.add_argument('--required-file',action='append',default=[])
    parser.add_argument('--python-symbol',action='append',default=[])
    args=parser.parse_args()
    settings=Settings()
    token=settings.token or (settings.data_dir/'.api-token').read_text().strip()
    headers={'X-Neura-Token':token}
    with httpx.Client(base_url='http://127.0.0.1:8000',headers=headers,timeout=settings.timeout_s+10,trust_env=False) as client:
        if args.project:
            response=client.post('/projects',json={'user_request':args.text,'requirements':[args.text],
                                 'required_files':args.required_file,'required_python_symbols':args.python_symbol})
            print(json.dumps(response.json(),ensure_ascii=False,indent=2));sys.exit(0 if response.is_success else 1)
        payload={'messages':[{'role':'user','content':args.text}],'tier':args.tier,'stream':args.stream}
        if not args.stream:
            response=client.post('/v1/chat/completions',json=payload)
            print(json.dumps(response.json(),ensure_ascii=False,indent=2));sys.exit(0 if response.is_success else 1)
        with client.stream('POST','/v1/chat/completions',json=payload) as response:
            if not response.is_success:
                print(response.read().decode());sys.exit(1)
            for line in response.iter_lines():
                if not line.startswith('data: '):continue
                text=line[6:]
                if text=='[DONE]':break
                data=json.loads(text)
                if data.get('error'):print(data['error']['message']);sys.exit(1)
                for choice in data.get('choices',[]):print(choice.get('delta',{}).get('content',''),end='',flush=True)
        print()
