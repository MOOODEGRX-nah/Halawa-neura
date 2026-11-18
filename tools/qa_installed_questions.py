"""Question battery against the INSTALLED package: does Neura understand each kind of request?

Each item is sent exactly like the composer does it (POST /chat/dispatch; when the dispatcher
answers kind=chat, POST /route then /v1/chat/completions with the session history), on the real
GPU models, in an isolated QA profile. Every item declares the expected interpretation (kind,
skill, recipe, edit/plan/status...) and, for chat, an answer check. Desktop skills are disabled in
the QA profile so an understood desktop request is visible by its skill name without opening
anything on the user's screen. Project jobs that only test understanding are cancelled at once.
"""
import argparse, base64, json, os, re, struct, sys, time, uuid, zlib
from pathlib import Path

p = argparse.ArgumentParser(description=__doc__)
p.add_argument('--out', type=Path, required=True)
p.add_argument('--app', type=Path, default=Path('/opt/neura-ai/app'))
p.add_argument('--vendor', type=Path, default=Path('/opt/neura-ai/vendor'))
p.add_argument('--only', default='')
a = p.parse_args(); out = a.out.resolve(); out.mkdir(parents=True, exist_ok=True)
if (out / 'answers.json').exists(): raise SystemExit('Refusing to overwrite an existing run')
sys.path[:0] = [str(a.app), str(a.vendor)]; sys.path.append(str(Path(__file__).resolve().parent))
profile = out / 'profile'
os.environ.update(NEURA_SETTINGS_DIR=str(profile / 'config'), NEURA_DATA_DIR=str(profile / 'data'), NEURA_STATE_DIR=str(profile / 'state'), NEURA_TIMEOUT_S='900',
                  PYTHONPATH=os.pathsep.join([str(a.app), str(a.vendor)]))
import src
assert Path(src.__file__).resolve().is_relative_to(a.app.resolve()), src.__file__
from verification.live import foreign_instances
if foreign_instances(): raise SystemExit('A Neura backend is already running; refused')
from src.desktop.paths import DesktopSettings, VERSION
from src.desktop.service import BackendService
DESKTOP = ['open_website', 'search_web', 'search_youtube', 'open_file', 'open_folder', 'open_application', 'list_recent_applications']
settings = DesktopSettings()
settings.values.update(models_dir='/opt/neura-ai/models', n_gpu_layers=-1, gpu_device='AMD Radeon RX 9060 XT (RADV GFX1200)', n_ctx=8192, dedicated_coder=True,
                       check_updates=False, disabled_skills=DESKTOP); settings.save()
service = BackendService(settings); service.start()
end = time.monotonic() + 90
while not service.health() and time.monotonic() < end: time.sleep(.3)
if not service.health(): raise SystemExit('backend not healthy')
TOKEN = (profile / 'data/.api-token').read_text().strip()


def api(path, body=None, timeout=60, method=None):
    import http.client
    from urllib.parse import urlsplit
    u = urlsplit(service.url); conn = http.client.HTTPConnection(u.hostname, u.port, timeout=timeout)
    try:
        conn.request(method or ('POST' if body is not None else 'GET'), path, body=None if body is None else json.dumps(body).encode(),
                     headers={'X-Neura-Token': TOKEN, 'Content-Type': 'application/json'})
        r = conn.getresponse(); data = r.read()
        try: return r.status, json.loads(data)
        except ValueError: return r.status, data.decode(errors='replace')
    except Exception as e: return None, type(e).__name__ + ': ' + str(e)[:200]
    finally: conn.close()


def rid(): return 'r_' + str(int(time.time() * 1000)) + '_' + uuid.uuid4().hex
sessions = {}; history = {}; bound = {}
def sid(key): return sessions.setdefault(key, 'qs-' + key + '-' + uuid.uuid4().hex[:6])


def png(left, right):
    def chunk(n, d): return struct.pack('>I', len(d)) + n + d + struct.pack('>I', zlib.crc32(n + d) & 0xffffffff)
    raw = b''.join(b'\0' + bytes(left) * 32 + bytes(right) * 32 for _ in range(64))
    return b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 64, 64, 8, 2, 0, 0, 0)) + chunk(b'IDAT', zlib.compress(raw)) + chunk(b'IEND', b'')


def chat_turn(key, text, image=None):
    """What the composer does after dispatch says kind=chat: /route, then completion with history."""
    h = history.setdefault(key, [])
    user = {'role': 'user', 'content': [{'type': 'text', 'text': text}, {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + base64.b64encode(image).decode()}}]} if image else {'role': 'user', 'content': text}
    c1, route = api('/route', {'text': text, 'tier': 'vision' if image else None, 'deep': False, 'has_image': bool(image)})
    c2, r = api('/v1/chat/completions', {'messages': (h + [user])[-40:], 'stream': False, 'max_tokens': 400, 'temperature': 0.2, 'neura': {'tier': 'vision' if image else None, 'deep': False}}, timeout=900)
    try: answer = r['choices'][0]['message']['content']
    except Exception: answer = None
    if answer: h.extend([user, {'role': 'assistant', 'content': answer}])
    return {'route': {k: route.get(k) for k in ('tier', 'model_id', 'reason', 'intent')} if isinstance(route, dict) else route, 'http': c2,
            'model': r.get('model') if isinstance(r, dict) else None, 'answer': answer if answer else str(r)[:300], 'claim_guard': r.get('neura_claim_guard') if isinstance(r, dict) else None}


def wait_job(job_id, seconds=1500):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        c, job = api('/project-jobs/' + job_id)
        if c == 200 and job['state'] in ('completed', 'failed', 'cancelled'): return job
        time.sleep(1)
    return api('/project-jobs/' + job_id)[1]


results = []
def ask(n, key, text, expect, check=None, keep_job=False, project=False, image=None):
    """expect: dispatch kind ('chat','project','action','clarification','plan','metadata','status','workspace','knowledge')."""
    if a.only and str(n) not in a.only.split(','): return
    t0 = time.time(); body = {'text': text, 'request_id': rid(), 'session_id': sid(key)}
    if key in bound: body['active_project_id'] = bound[key]
    c, d = (200, {'kind': 'chat'}) if image else api('/chat/dispatch', body, timeout=900)
    d = d if isinstance(d, dict) else {'kind': None, 'raw': str(d)[:300]}
    row = {'n': n, 'session': key, 'question': text, 'expected_kind': expect, 'kind': d.get('kind'), 'http': c,
           'skill': d.get('skill'), 'message': (d.get('message') or (d.get('result') or {}).get('message') or '')[:400],
           'choices': [x.get('label') for x in d.get('choices', [])][:5], 'operation': d.get('operation')}
    job = (d.get('job') or {}).get('job_id')
    if d.get('kind') == 'project':
        inv = (d.get('job') or {}).get('invoice') or {}
        row['recipe'] = inv.get('web_recipe'); row['filename_hints'] = inv.get('filename_hints')
        row['feature_contract'] = (d.get('decision') or {}).get('required_feature_contract')
        if keep_job:
            j = wait_job(job); row['job_state'] = j['state']; row['job_error'] = j.get('error')
            if project and j['state'] == 'completed': bound[key] = j['project_id']
            pr = api('/projects/' + j['project_id'])[1] if j.get('project_id') else {}
            row['files'] = [f['path'] for f in pr.get('files', [])]; row['revision'] = pr.get('project_revision')
        elif job:
            api('/project-jobs/' + job + '/cancel', {}, method='POST'); row['job_state'] = wait_job(job, 300)['state']
    if d.get('kind') == 'chat': row.update(chat_turn(key, text, image))
    ok = d.get('kind') == expect
    detail = None
    if ok and check:
        try: detail = check(row, d)
        except Exception as e: detail = 'check error: ' + type(e).__name__ + ' ' + str(e)[:120]
        ok = detail is True
    row['understood'] = ok; row['check'] = None if detail in (None, True) else detail; row['seconds'] = round(time.time() - t0, 1)
    results.append(row); (out / 'answers.json').write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print(('PASS' if ok else 'FAIL'), n, text[:60], '->', row['kind'], row.get('skill') or row.get('recipe') or '', (row.get('answer') or row['message'] or '')[:90].replace('\n', ' '), flush=True)


def says(pattern):
    return lambda r, d: True if r.get('answer') and re.search(pattern, r['answer'], re.I) else 'answer does not match /' + pattern + '/: ' + str(r.get('answer'))[:160]
def skill(name, query=None):
    def f(r, d):
        if d.get('skill') != name: return 'skill ' + str(d.get('skill')) + ' != ' + name
        return True
    return f
def recipe(name): return lambda r, d: True if r.get('recipe') == name else 'recipe ' + str(r.get('recipe')) + ' != ' + str(name)
def no_false_claim(r, d):
    ans = r.get('answer') or ''
    claimed = re.search(r'(?:تم|لقد)\s+(?:إرسال|ارسال|أرسلت)|أرسلت (?:البريد|الرسالة)|I (?:have )?sent', ans)
    return True if (not claimed or r.get('claim_guard')) else 'claimed a send without guard: ' + ans[:160]


try:
    # --- ordinary questions: must stay chat and be answered correctly ---
    ask(1, 'g', 'ما عاصمة فرنسا؟', 'chat', says('باريس|Paris'))
    ask(2, 'g', 'ما هي عاصمة اليابان؟', 'chat', says('طوكيو|Tokyo'))
    ask(3, 'e', 'What is the capital of Germany?', 'chat', says('Berlin'))
    ask(4, 'm', 'كم يساوي 15 × 4؟', 'chat', says('60|٦٠'))
    ask(5, 'm', 'What is 2 to the power of 10?', 'chat', says('1024|1,024'))
    ask(6, 'r', 'إذا كان عمر أحمد 10 سنوات وعمر أخيه ضعف عمره، كم عمر أخيه؟', 'chat', says('20|٢٠|عشرون|عشرين'))
    ask(7, 't', 'ترجم إلى الإنجليزية: صباح الخير', 'chat', says('good morning'))
    ask(8, 't', 'Translate to Arabic: Thank you very much', 'chat', says('شكر'))
    ask(9, 'x', 'اشرح ما هو الذكاء الاصطناعي في جملتين', 'chat', says('ذكاء|الذكاء'))
    ask(10, 'c', 'ما الفرق بين list و tuple في Python؟', 'chat', says('tuple|صف'))
    ask(11, 'c', 'اشرح هذا الكود: print(sum(range(5)))', 'chat', says(r'\b10\b|١٠|عشرة'))
    ask(12, 'w', 'اكتب لي جملة قصيرة عن البحر', 'chat', says('بحر|البحر'))
    ask(13, 'n', 'لا تبرمج شيئًا، فقط اشرح ما هو HTML', 'chat', says('HTML|لغة'))
    ask(14, 'mem', 'اسمي ليلى وأعمل مهندسة.', 'chat')
    ask(15, 'mem', 'ما اسمي وما عملي؟', 'chat', says('ليلى'))
    ask(16, 'id', 'من أنت؟', 'chat', says('Neura|نيورا|مساعد'))
    ask(17, 'claim', 'أرسل بريدًا إلى أحمد يقول له مرحبا', 'chat', no_false_claim)
    ask(18, 'mix', 'كيف أكتب for loop في JavaScript؟', 'chat', says('for'))
    # --- routing ---
    ask(19, 'img', 'ما لون النصف الأيسر من الصورة؟ أجب بكلمة: أحمر أو أزرق.', 'chat', lambda r, d: True if r['route'].get('tier') == 'vision' and 'أحمر' in (r.get('answer') or '') else 'vision route/answer: ' + json.dumps(r['route'], ensure_ascii=False) + ' ' + str(r.get('answer'))[:80], image=png((255, 0, 0), (0, 0, 255)))
    ask(20, 'img2', 'ما لون النصف الأيسر من الصورة؟ أجب بكلمة: أحمر أو أزرق.', 'chat', lambda r, d: True if 'أزرق' in (r.get('answer') or '') else 'answer: ' + str(r.get('answer'))[:80], image=png((0, 0, 255), (255, 0, 0)))
    # --- planning only ---
    ask(21, 'plan', 'خطط لموقع متجر إلكتروني صغير', 'plan', lambda r, d: True if d.get('message', '').count('\n') >= 3 and 'لم تنشأ مهمة' in d.get('message', '') else 'plan text: ' + d.get('message', '')[:160])
    # --- project creation intents (cancelled at once: understanding only) ---
    ask(22, 'p1', 'برمج لي موقع للcv', 'project', recipe(None))  # by design: no local/Arabic signal -> general path
    ask(48, 'p9', 'برمج لي موقع cv عربي محلي بدون إنترنت', 'project', recipe('arabic_cv_v1'))
    ask(23, 'p2', 'أنشئ دليل خدمات محلي بدون إنترنت لمركز صيانة فيه فلتر حسب الفئة', 'project', recipe('arabic_services_v1'))
    ask(24, 'p3', 'برمج سكربت Python يحسب متوسط قائمة أرقام', 'project', lambda r, d: True if r.get('filename_hints') == ['main.py'] and not r.get('recipe') else 'hints/recipe: ' + str(r.get('filename_hints')) + ' ' + str(r.get('recipe')))
    ask(25, 'p4', 'Build a website for a coffee shop', 'project', lambda r, d: True if r.get('filename_hints') == ['index.html'] else 'hints: ' + str(r.get('filename_hints')))
    ask(26, 'p5', 'اصنع لعبة بسيطة لتخمين الأرقام', 'project')
    ask(27, 'p6', 'صمم صفحة تسجيل دخول', 'project')
    ask(28, 'p7', 'برمج موقع شخصي بوضع داكن وبدون أي أنيميشن', 'project', lambda r, d: True if r.get('feature_contract') else 'no feature contract recorded')
    ask(29, 'p8', 'برمج لي موقع CV باستخدام React', 'project', lambda r, d: True if r.get('recipe') is None else 'React request must not use the offline recipe: ' + str(r.get('recipe')))
    # --- desktop skills (disabled in QA profile: understood = right skill, nothing opened) ---
    ask(30, 'd', 'افتح يوتيوب', 'action', skill('open_website'))
    ask(31, 'd', 'ابحث في يوتيوب عن تعلم Python', 'action', skill('search_youtube'))
    ask(32, 'd', 'ابحث في يوتيوب', 'action', lambda r, d: True if not d.get('skill') and 'اكتب عبارة البحث' in r['message'] else 'expected a request for the search words: ' + r['message'][:120])
    ask(33, 'd', 'ابحث عن أسعار الذهب اليوم', 'action', skill('search_web'))
    ask(34, 'd', 'افتح github.com', 'action', skill('open_website'))
    ask(35, 'd', 'افتح موقع example.com', 'action', skill('open_website'))
    ask(36, 'd', 'اعرض آخر التطبيقات', 'action', skill('list_recent_applications'))
    ask(37, 'd2', 'افتح تطبيق برنامج_غير_موجود_xyz', 'action', lambda r, d: True if 'لم أتعرف' in r['message'] and 'لم أفتح' in r['message'] else r['message'][:160])
    ask(38, 'd3', 'افتح ملف', 'action', lambda r, d: True if not d.get('skill') or d.get('kind') == 'clarification' else 'opened without a target')
    # --- a real saved project, then questions and edits bound to it ---
    ask(39, 'site', 'برمج لي موقع صفحة واحدة فيها عنوان مرحبا فقط', 'project', lambda r, d: True if r.get('job_state') == 'completed' and 'index.html' in r.get('files', []) else 'create: ' + str(r.get('job_state')) + ' ' + str(r.get('job_error'))[:160], keep_job=True, project=True)
    ask(40, 'site', 'ما لغة هذا المشروع؟', 'metadata', lambda r, d: True if d.get('model_called') is False and r['message'] else 'metadata: ' + r['message'][:120])
    ask(41, 'site', 'لماذا اخترت هذا التصميم للصفحة؟', 'chat')
    ask(42, 'site', 'ما حالة المهمة؟', 'status')
    ask(43, 'site', 'أضف زر «تواصل معنا» أسفل العنوان', 'project', lambda r, d: True if r.get('operation') == 'edit' else 'operation: ' + str(r.get('operation')), keep_job=True)
    ask(44, 'site', 'غير لون الخلفية إلى الأزرق الفاتح', 'project', lambda r, d: True if r.get('operation') == 'edit' else 'operation: ' + str(r.get('operation')), keep_job=True)
    ask(45, 'site', 'عدل المشروع الحالي', 'workspace')
    ask(46, 'fresh', 'أضف زر تسجيل الدخول', 'clarification', lambda r, d: True if r['choices'] else 'no project choices: ' + r['message'][:120])
    ask(47, 'site', 'أوقف المهمة', 'status')
finally:
    summary = {'version': VERSION, 'app': str(a.app), 'asked': len(results), 'understood': sum(r['understood'] for r in results),
               'not_understood': [(r['n'], r['question'], r['kind'], r['check']) for r in results if not r['understood']]}
    (out / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1)); print('SUMMARY', json.dumps(summary, ensure_ascii=False), flush=True)
    service.stop()
