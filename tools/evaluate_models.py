"""Small repeatable acceptance set. These checks do not measure general model quality."""
import ast
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from src.core.neura_loop import NeuraLoop
from src.backend.schemas import ChatRequest
from pydantic import ValidationError

CASES = [
 ('greeting','قل تحية عربية قصيرة.',lambda s:bool(re.search('[\u0600-\u06ff]',s))),
 ('knowledge','ما عاصمة فرنسا؟ اذكر اسم المدينة فقط.',lambda s:'باريس' in s or 'paris' in s.lower()),
 ('summary','لخص هذه الجملة بالعربية في جملة قصيرة: يعتمد المشروع على Python ويعمل محليا دون سحابة.',lambda s:'Python' in s or 'بايثون' in s),
 ('translation','ترجم كلمة cat إلى العربية. اكتب الكلمة فقط.',lambda s:'قط' in s),
 ('python','Return only a fenced Python function add(a,b) returning a+b.',lambda s:bool(re.search(r'def\s+add\s*\(',s)) and bool(re.search(r'a\s*\+\s*b',s))),
 ('javascript','Return only JavaScript function add(a,b) returning a+b.',lambda s:'function' in s and bool(re.search(r'a\s*\+\s*b',s))),
 ('debug','Fix this Python function to return the sum. Return only code: def add(a,b): return a-b',lambda s:bool(re.search(r'a\s*\+\s*b',s))),
 ('analysis','What is 12 multiplied by 13? Answer only the number.',lambda s:'156' in s),
 ('english','Answer in English in one sentence: what is Python?',lambda s:'python' in s.lower()),
]

if __name__=='__main__':
    loop=NeuraLoop()
    report={'created_at':datetime.now(timezone.utc).isoformat(),'tier':'daily','cases':[]}
    output=Path(sys.argv[1])
    try:
        for name,prompt,check in CASES:
            started=time.monotonic();record={'name':name,'prompt':prompt}
            try:
                result=loop.complete([{'role':'user','content':prompt}],tier='daily',max_tokens=256,temperature=.1)
                text=result['choices'][0]['message']['content']
                record.update(result=result,passed=bool(check(text)) and result['choices'][0]['finish_reason']=='stop')
            except Exception as exc:record.update(error=str(exc),passed=False)
            record['elapsed_s']=round(time.monotonic()-started,3);report['cases'].append(record)
            output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
            print(name,record['passed'],record['elapsed_s'],flush=True)
        try:
            ChatRequest(messages=[{'role':'user','content':''}])
            passed=False
        except ValidationError:passed=True
        report['cases'].append({'name':'empty_input','passed':passed,'check':'Pydantic rejects empty user content before inference'})
        output.write_text(json.dumps(report,ensure_ascii=False,indent=2))
    finally:loop.shutdown()
