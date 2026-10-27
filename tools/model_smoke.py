"""Explicit hardware acceptance checks, never part of the default unit suite."""
import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.runtime import Settings
from src.core.neura_loop import NeuraLoop

CASES = [
    ('arabic', 'أجب بجملة عربية قصيرة: ما عاصمة فرنسا؟'),
    ('english', 'Answer in one short sentence: what is 2 + 2?'),
    ('code', 'Return only Python code for a function add(a, b) that returns their sum.'),
]

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tier', choices=['fast','daily','expert','coder','vision'], default='fast')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-tokens', type=int, default=256)
    args = parser.parse_args()
    loop = NeuraLoop(settings=Settings())
    report = {'created_at': datetime.now(timezone.utc).isoformat(), 'tier': args.tier,
              'n_ctx': loop.settings.n_ctx, 'n_gpu_layers': loop.settings.n_gpu_layers, 'cases': []}
    try:
        for name, question in CASES:
            started = time.monotonic()
            record = {'name': name, 'prompt': question}
            try:
                result = loop.complete([{'role':'system','content':'Follow the requested output format. Be concise.'},
                                        {'role':'user','content':question}], tier=args.tier,
                                       max_tokens=args.max_tokens, temperature=0.2, top_p=0.9)
                record.update({'result': result, 'nonempty': bool(result['choices'][0]['message']['content'].strip())})
            except Exception as exc:
                record['error'] = str(exc)
            record['elapsed_s'] = round(time.monotonic()-started, 3)
            report['cases'].append(record)
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(name, record['elapsed_s'], record.get('error','nonempty=' + str(record.get('nonempty'))), flush=True)
    finally:
        loop.shutdown()
