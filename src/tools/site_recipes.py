"""P04 recipes REC02–REC06: reviewed offline Arabic site types with a real, checkable interaction each.

Every recipe is a bounded contract for the local model (planning and generation stay mandatory),
an independent source validator, and a browser probe that drives the declared interaction in the
isolated preview. Names, prices and data are placeholders by contract; nothing here claims a working
backend, payment, authentication or publication.
"""
import re

from src.core.project_files import ProjectError

COMMON = ('Offline Arabic site: index.html with html lang=ar dir=rtl, meta charset utf-8, meta viewport width=device-width, an Arabic meta description '
          'of 30 to 170 characters and exactly one h1; linked style.css and deferred script.js. No imports, remote assets, fonts, forms, fetch, cloud, '
          'storage, build tools or dependencies. style.css: responsive (one column below 600px), a clearly visible :focus-visible outline, '
          '[hidden]{display:none}, @media (prefers-reduced-motion: reduce) disabling transitions and animations, flat solid backgrounds and normal '
          'text contrast at least 4.5:1. Use native button elements with type=button so Tab, Enter and Space work. Preserve content and behavior through edits.')

SITES = {
    'arabic_landing_v1': {
        'label': 'وصفة صفحة تعريفية لنشاط تجاري', 'plan_id': 'REC02',
        'detect': r'صفح[ةه]\s+(?:هبوط|تعريفي[ةه]|تجاري[ةه])|\blanding\s*page\b|موقع\s+(?:ل|لـ)?\s*(?:شرك[ةه]|مطعم|مقهى|كافي[هة]|نشاط|مؤسس[ةه]|عياد[ةه]|مكتب|صالون|ورش[ةه]|مشروع(?:ي)?\s+(?:التجاري|الصغير))',
        'constraints': [
            COMMON,
            'Header nav with links to #services, #about, #faq and #contact. A hero section holds the single h1, a short Arabic value statement and one call-to-action link a.cta-button with href=#contact.',
            'Sections with ids services (at least three .service-item cards with an Arabic heading and placeholder description), about, faq and contact. Contact shows clearly labelled placeholder details only; do not invent real phone numbers, addresses or names.',
            'FAQ: at least three .faq-item elements, each with button.faq-question (type=button, aria-expanded=false, aria-controls=<answer id>) and div.faq-answer with that id and the hidden attribute. script.js toggles aria-expanded and the hidden attribute of the controlled answer; a second activation closes it.',
        ]},
    'arabic_dashboard_v1': {
        'label': 'وصفة لوحة بيانات تجريبية', 'plan_id': 'REC03',
        'detect': r'لوح[ةه]\s+(?:ال)?(?:بيانات|تحكم|معلومات|مؤشرات|احصائيات|إحصائيات)|\bdashboard\b|\badmin panel\b',
        'constraints': [
            COMMON,
            'At least four .kpi-card elements, each with an Arabic label and a .kpi-value. Values are declared sample data.',
            'A table id=data-table with a caption containing «بيانات تجريبية», a thead and at least six tbody rows; every row has data-status equal to one of the status filter values.',
            'Controls: input id=table-search type=search with an Arabic aria-label; select id=status-filter with option value=all plus at least two status options. script.js hides (hidden attribute) every row that does not match both the search text (case-insensitive, any cell) and the status, updates id=row-count (aria-live=polite) with the visible count in Arabic, and shows id=empty-state (initially hidden) only when no row matches.',
        ]},
    'arabic_blog_v1': {
        'label': 'وصفة مدونة أو توثيق', 'plan_id': 'REC04',
        'detect': r'مدون[ةه]|\bblog\b|توثيق|\bdocumentation\b|\bdocs\b|موقع\s+مقالات',
        'constraints': [
            COMMON,
            'At least four article.post-card elements, each with an h2 title, an Arabic placeholder excerpt and data-tags listing one or more tag slugs separated by spaces.',
            'A group id=tag-filters with role=group and an Arabic aria-label holds button.tag-filter elements (type=button, data-tag, aria-pressed): exactly one data-tag=all labelled الكل pressed initially, plus at least two tags actually used by posts.',
            'An input id=post-search type=search with an Arabic aria-label. script.js shows only posts matching the active tag and the search text (title or excerpt), keeps aria-pressed on the active tag only, and writes the visible count in Arabic to id=post-count (aria-live=polite).',
        ]},
    'arabic_store_v1': {
        'label': 'وصفة واجهة متجر بسلة تجريبية', 'plan_id': 'REC05',
        'detect': r'متجر|\bstore\b|\bshop\b|سل[ةه]\s+(?:ال)?مشتريات|منتجات\s+(?:مع|و)\s*سل[ةه]',
        'constraints': [
            COMMON,
            'An element id=demo-notice states in Arabic that the cart is a demo with no real payment or order (سلة تجريبية — لا يوجد دفع أو طلب حقيقي).',
            'At least six .product-card elements, each with an h3 name, a .price text and data-price (a plain number), and a button.add-to-cart (type=button) with data-product. Product names and prices are placeholders.',
            'Cart: id=cart-count (aria-live=polite) shows the number of items, id=cart-total shows the sum of data-price of added items, button id=clear-cart (type=button) empties the cart. Keep the cart in memory only (no storage).',
        ]},
    'arabic_saas_v1': {
        'label': 'وصفة واجهة تطبيق SaaS', 'plan_id': 'REC06',
        'detect': r'\bsaas\b|منص[ةه]\s+(?:رقمي[ةه]|سحابي[ةه]|اشتراك|خدم[ةه])|واجه[ةه]\s+تطبيق|خطط\s+(?:ال)?اسعار|خطط\s+(?:ال)?أسعار|(?:ال)?اشتراكات\s+(?:الشهري[ةه]|السنوي[ةه])',
        'constraints': [
            COMMON,
            'Features as tabs: an element with role=tablist holds at least three button elements with role=tab (type=button, aria-selected, aria-controls) and exactly one aria-selected=true; each controls an element with role=tabpanel; only the selected panel is visible (others have hidden). script.js switches selection on activation.',
            'Pricing: at least three .plan-card elements, each with a .plan-price carrying data-monthly and data-yearly text values (the monthly value shown initially), and a button id=billing-toggle (type=button, aria-pressed=false). Activating it switches every .plan-price to data-yearly and aria-pressed=true; again restores monthly. State that prices are illustrative (أسعار توضيحية).',
            'No real sign-up, login or payment: any such button is labelled as a demo placeholder.',
        ]},
}

FILES = ['index.html', 'style.css', 'script.js']


def detect(q):
    for recipe_id in ('arabic_store_v1', 'arabic_dashboard_v1', 'arabic_blog_v1', 'arabic_saas_v1', 'arabic_landing_v1'):
        if re.search(SITES[recipe_id]['detect'], q, re.I):
            return recipe_id
    return None


def _classes(attrs):
    return (attrs.get('class') or '').split()


def _quality(files):
    from src.core.web_quality import report as quality
    items = quality(files, 'index.html')['items']
    if not (items['meta_description']['ok'] and items['viewport']['ok'] and items['charset']['ok']):
        raise ProjectError('الوصفة تحتاج meta description عربيًا (30–170 حرفًا) وviewport وcharset')
    if not items['single_h1']['ok']:
        raise ProjectError('الوصفة تحتاج عنوان h1 واحدًا بالضبط')
    css = files['style.css']
    if not re.search(r':focus-visible', css) or not re.search(r'@media[^{]*prefers-reduced-motion\s*:\s*reduce', css, re.I) or not re.search(r'\[hidden\]', css):
        raise ProjectError('الوصفة تحتاج :focus-visible و[hidden] وprefers-reduced-motion في style.css')


def _arabic_words(parser, minimum, what):
    if len(re.findall(r'[؀-ۿ]{2,}', ' '.join(parser.words))) < minimum:
        raise ProjectError('محتوى ' + what + ' العربي مفقود')


def _one(elements, element_id):
    found = [a for t, a in elements if a.get('id') == element_id]
    if len(found) != 1:
        raise ProjectError('هوية ' + element_id + ' مفقودة أو مكررة')
    return found[0]


def _buttons(elements, cls):
    found = [(t, a) for t, a in elements if cls in _classes(a)]
    if any(t != 'button' or a.get('type') != 'button' for t, a in found):
        raise ProjectError('عناصر ' + cls + ' يجب أن تكون button type=button')
    return [a for t, a in found]


def validate_landing(parser, elements, files):
    hrefs = {a.get('href') for t, a in elements if t == 'a'}
    for anchor in ('#services', '#about', '#faq', '#contact'):
        if anchor not in hrefs:
            raise ProjectError('التنقل يحتاج رابطًا إلى ' + anchor)
        _one(elements, anchor[1:])
    if not any(t == 'a' and 'cta-button' in _classes(a) and a.get('href') == '#contact' for t, a in elements):
        raise ProjectError('زر الدعوة a.cta-button يجب أن يشير إلى #contact')
    if sum('service-item' in _classes(a) for t, a in elements) < 3:
        raise ProjectError('قسم الخدمات يحتاج ثلاث بطاقات service-item على الأقل')
    questions = _buttons(elements, 'faq-question')
    ids = {a.get('id'): a for t, a in elements if a.get('id')}
    if len(questions) < 3:
        raise ProjectError('الأسئلة الشائعة تحتاج ثلاثة أسئلة على الأقل')
    for q in questions:
        panel = ids.get(q.get('aria-controls'))
        if q.get('aria-expanded') != 'false' or not panel or 'faq-answer' not in _classes(panel) or 'hidden' not in panel:
            raise ProjectError('كل سؤال يحتاج aria-expanded=false وaria-controls لإجابة faq-answer مخفية بالسمة hidden')
    _arabic_words(parser, 20, 'الصفحة التعريفية')


def validate_dashboard(parser, elements, files):
    if sum('kpi-card' in _classes(a) for t, a in elements) < 4 or sum('kpi-value' in _classes(a) for t, a in elements) < 4:
        raise ProjectError('اللوحة تحتاج أربع بطاقات kpi-card لكل منها kpi-value')
    _one(elements, 'data-table')
    if 'بيانات تجريبية' not in ' '.join(parser.words):
        raise ProjectError('الجدول يحتاج caption يذكر «بيانات تجريبية»')
    search = _one(elements, 'table-search')
    if search.get('type') != 'search' or not re.search(r'[؀-ۿ]', search.get('aria-label', '')):
        raise ProjectError('حقل البحث يحتاج type=search ووصفًا عربيًا')
    _one(elements, 'status-filter')
    values = re.findall(r'<option[^>]*value\s*=\s*["\']([^"\']+)', files['index.html'], re.I)
    if 'all' not in values or len(set(values)) < 3:
        raise ProjectError('مرشح الحالة يحتاج خيار all وخيارين على الأقل')
    statuses = [a.get('data-status') for t, a in elements if t == 'tr' and a.get('data-status')]
    if len(statuses) < 6 or any(s not in values for s in statuses):
        raise ProjectError('الجدول يحتاج ست صفوف على الأقل بقيم data-status من خيارات المرشح')
    if _one(elements, 'row-count').get('aria-live') != 'polite':
        raise ProjectError('عداد الصفوف يحتاج aria-live=polite')
    if 'hidden' not in _one(elements, 'empty-state'):
        raise ProjectError('حالة «لا نتائج» يجب أن تبدأ مخفية')
    _arabic_words(parser, 16, 'لوحة البيانات')


def validate_blog(parser, elements, files):
    posts = [a for t, a in elements if t == 'article' and 'post-card' in _classes(a)]
    if len(posts) < 4 or any(not (a.get('data-tags') or '').split() for a in posts):
        raise ProjectError('المدونة تحتاج أربع مقالات post-card على الأقل لكل منها data-tags')
    group = _one(elements, 'tag-filters')
    if group.get('role') != 'group' or not re.search(r'[؀-ۿ]', group.get('aria-label', '')):
        raise ProjectError('مجموعة الوسوم تحتاج role=group ووصفًا عربيًا')
    filters = _buttons(elements, 'tag-filter')
    tags = [a.get('data-tag') for a in filters]
    used = {tag for a in posts for tag in a['data-tags'].split()}
    if tags.count('all') != 1 or len([t for t in tags if t in used]) < 2 or any(a.get('aria-pressed') != ('true' if a.get('data-tag') == 'all' else 'false') for a in filters):
        raise ProjectError('الوسوم تحتاج «الكل» مضغوطًا ووسمين مستخدمين على الأقل')
    search = _one(elements, 'post-search')
    if search.get('type') != 'search':
        raise ProjectError('بحث المقالات يحتاج type=search')
    if _one(elements, 'post-count').get('aria-live') != 'polite':
        raise ProjectError('عداد المقالات يحتاج aria-live=polite')
    _arabic_words(parser, 20, 'المدونة')


def validate_store(parser, elements, files):
    notice = re.search(r'id\s*=\s*["\']demo-notice["\'][^>]*>([\s\S]{0,300}?)<', files['index.html'])
    if not notice or not re.search(r'تجريبي', notice.group(1)):
        raise ProjectError('المتجر يحتاج تنبيه demo-notice يوضح أن السلة تجريبية')
    cards = [a for t, a in elements if 'product-card' in _classes(a)]
    if len(cards) < 6 or any(not re.fullmatch(r'\d+(?:\.\d+)?', a.get('data-price') or '') for a in cards):
        raise ProjectError('المتجر يحتاج ست منتجات product-card على الأقل بسعر data-price رقمي')
    if len(_buttons(elements, 'add-to-cart')) < 6:
        raise ProjectError('كل منتج يحتاج زر add-to-cart')
    if _one(elements, 'cart-count').get('aria-live') != 'polite':
        raise ProjectError('عداد السلة يحتاج aria-live=polite')
    _one(elements, 'cart-total')
    clear = _one(elements, 'clear-cart')
    if not any(t == 'button' and a.get('id') == 'clear-cart' and a.get('type') == 'button' for t, a in elements):
        raise ProjectError('زر تفريغ السلة يحتاج button type=button')
    _arabic_words(parser, 16, 'المتجر')


def validate_saas(parser, elements, files):
    if not any(a.get('role') == 'tablist' for t, a in elements):
        raise ProjectError('الميزات تحتاج role=tablist')
    tabs = [a for t, a in elements if a.get('role') == 'tab']
    if len(tabs) < 3 or any(t != 'button' or a.get('type') != 'button' for t, a in elements if a.get('role') == 'tab'):
        raise ProjectError('تحتاج ثلاثة تبويبات button role=tab على الأقل')
    if [a.get('aria-selected') for a in tabs].count('true') != 1:
        raise ProjectError('تبويب واحد فقط يكون aria-selected=true')
    ids = {a.get('id'): a for t, a in elements if a.get('id')}
    for tab in tabs:
        panel = ids.get(tab.get('aria-controls'))
        if not panel or panel.get('role') != 'tabpanel' or (tab.get('aria-selected') == 'true') == ('hidden' in panel):
            raise ProjectError('كل تبويب يتحكم بلوحة role=tabpanel، والمخفية فقط غير المختارة')
    prices = [a for t, a in elements if 'plan-price' in _classes(a)]
    if sum('plan-card' in _classes(a) for t, a in elements) < 3 or len(prices) < 3 or any(not a.get('data-monthly') or not a.get('data-yearly') or a['data-monthly'] == a['data-yearly'] for a in prices):
        raise ProjectError('الأسعار تحتاج ثلاث خطط بقيم data-monthly وdata-yearly مختلفة')
    toggle = _one(elements, 'billing-toggle')
    if toggle.get('aria-pressed') != 'false' or toggle.get('type') != 'button':
        raise ProjectError('زر الفوترة يحتاج type=button وaria-pressed=false')
    if 'توضيحي' not in ' '.join(parser.words):
        raise ProjectError('اذكر أن الأسعار توضيحية')
    _arabic_words(parser, 20, 'واجهة التطبيق')


VALIDATORS = {'arabic_landing_v1': validate_landing, 'arabic_dashboard_v1': validate_dashboard, 'arabic_blog_v1': validate_blog,
              'arabic_store_v1': validate_store, 'arabic_saas_v1': validate_saas}


def validate(files, recipe_id):
    from src.tools.web_recipes import offline_document, manifest
    parser = offline_document(files, recipe_id)
    VALIDATORS[recipe_id](parser, parser.elements, files)
    _quality(files)
    return {'recipe': manifest(recipe_id), 'status': 'passed', 'scope': 'Source structure/offline references only; the interaction is verified in the isolated browser'}


VIS = "const vis=e=>!!e&&e.getClientRects().length>0&&getComputedStyle(e).display!=='none'&&getComputedStyle(e).visibility!=='hidden'&&!e.closest('[hidden]');"
PROBES = {
    'arabic_landing_v1': VIS + r"""const q=document.querySelector('.faq-question'),errors=[];if(!q)return JSON.stringify({errors:['no faq question']});
const panel=document.getElementById(q.getAttribute('aria-controls'));const before=vis(panel);q.click();const opened=vis(panel)&&q.getAttribute('aria-expanded')==='true';q.click();const closed=!vis(panel)&&q.getAttribute('aria-expanded')==='false';
if(before)errors.push('FAQ answer visible before activation');if(!opened)errors.push('FAQ question did not open its answer');if(!closed)errors.push('FAQ question did not close its answer again');
const cta=document.querySelector('a.cta-button');if(!vis(cta)||!vis(document.getElementById('contact')))errors.push('call-to-action or contact section not visible');
return JSON.stringify({errors,proof:{before,opened,closed}});""",
    'arabic_dashboard_v1': VIS + r"""const rows=Array.from(document.querySelectorAll('#data-table tbody tr')),s=document.getElementById('table-search'),f=document.getElementById('status-filter'),empty=document.getElementById('empty-state'),errors=[];
const shown=()=>rows.filter(vis).length;const set=(e,v,ev)=>{e.value=v;e.dispatchEvent(new Event(ev,{bubbles:true}));};const total=rows.length;
if(shown()!==total)errors.push('not every row visible initially');const cell=(rows[0]?.cells[0]?.textContent||'').trim();
set(s,cell,'input');const found=shown();if(!found||!vis(rows[0]))errors.push('search for the first row did not keep it visible');
set(s,'zzqxwyy','input');if(shown()!==0||!vis(empty))errors.push('no-match search did not show only the empty state');
set(s,'','input');if(shown()!==total||vis(empty))errors.push('clearing search did not restore all rows');
const option=Array.from(f.options).find(o=>o.value!=='all');if(option){set(f,option.value,'change');const v=rows.filter(vis);if(!v.length||v.some(r=>r.dataset.status!==option.value))errors.push('status filter did not show only '+option.value);
const count=(document.getElementById('row-count')?.textContent||'').replace(/[٠-٩]/g,d=>'٠١٢٣٤٥٦٧٨٩'.indexOf(d));if(!count.includes(String(v.length)))errors.push('row-count does not state the visible count');set(f,'all','change');}
if(shown()!==total)errors.push('status «all» did not restore all rows');
return JSON.stringify({errors,proof:{total,found}});""",
    'arabic_blog_v1': VIS + r"""const posts=Array.from(document.querySelectorAll('article.post-card')),errors=[],total=posts.length;const tags=Array.from(document.querySelectorAll('.tag-filter'));
const tag=tags.find(b=>b.dataset.tag!=='all'&&posts.some(p=>p.dataset.tags.split(/\s+/).includes(b.dataset.tag)));if(!tag)return JSON.stringify({errors:['no usable tag filter']});
tag.click();const v=posts.filter(vis);if(!v.length||v.some(p=>!p.dataset.tags.split(/\s+/).includes(tag.dataset.tag)))errors.push('tag filter did not show only its posts');
if(tags.some(b=>b.getAttribute('aria-pressed')!==(b===tag?'true':'false')))errors.push('aria-pressed did not follow the active tag');
const count=(document.getElementById('post-count')?.textContent||'').replace(/[٠-٩]/g,d=>'٠١٢٣٤٥٦٧٨٩'.indexOf(d));if(!count.includes(String(v.length)))errors.push('post-count does not state the visible count');
tags.find(b=>b.dataset.tag==='all').click();if(posts.filter(vis).length!==total)errors.push('«الكل» did not restore all posts');
const s=document.getElementById('post-search'),title=(posts[0].querySelector('h2')?.textContent||'').trim();s.value=title;s.dispatchEvent(new Event('input',{bubbles:true}));if(!vis(posts[0]))errors.push('search by title hid the matching post');
s.value='zzqxwyy';s.dispatchEvent(new Event('input',{bubbles:true}));if(posts.filter(vis).length)errors.push('no-match search still shows posts');s.value='';s.dispatchEvent(new Event('input',{bubbles:true}));
return JSON.stringify({errors,proof:{total,tag:tag.dataset.tag,visible:v.length}});""",
    'arabic_store_v1': VIS + r"""const errors=[],cards=Array.from(document.querySelectorAll('.product-card')),num=t=>Number(String(t||'').replace(/[٠-٩]/g,d=>'٠١٢٣٤٥٦٧٨٩'.indexOf(d)).replace(/[^\d.]/g,''));
const add=c=>c.querySelector('.add-to-cart').click();const p1=Number(cards[0].dataset.price),p2=Number(cards[1].dataset.price);add(cards[0]);add(cards[0]);add(cards[1]);
const count=num(document.getElementById('cart-count').textContent),total=num(document.getElementById('cart-total').textContent);
if(count!==3)errors.push('cart-count is '+count+' after adding three items');if(Math.abs(total-(2*p1+p2))>0.01)errors.push('cart-total '+total+' is not '+(2*p1+p2));
document.getElementById('clear-cart').click();if(num(document.getElementById('cart-count').textContent)!==0)errors.push('clear-cart did not empty the cart');
if(!vis(document.getElementById('demo-notice')))errors.push('demo notice not visible');return JSON.stringify({errors,proof:{count,total,expected:2*p1+p2}});""",
    'arabic_saas_v1': VIS + r"""const errors=[],tabs=Array.from(document.querySelectorAll('[role=tab]'));const panel=t=>document.getElementById(t.getAttribute('aria-controls'));
const next=tabs.find(t=>t.getAttribute('aria-selected')!=='true');next.click();if(next.getAttribute('aria-selected')!=='true'||!vis(panel(next))||tabs.some(t=>t!==next&&(vis(panel(t))||t.getAttribute('aria-selected')==='true')))errors.push('tab activation did not show only its panel');
const toggle=document.getElementById('billing-toggle'),price=document.querySelector('.plan-price'),before=price.textContent.trim();toggle.click();const yearly=price.textContent.trim();
if(toggle.getAttribute('aria-pressed')!=='true'||!yearly.includes(price.dataset.yearly.trim())||yearly===before)errors.push('billing toggle did not switch prices to yearly');toggle.click();
if(toggle.getAttribute('aria-pressed')!=='false'||!price.textContent.includes(price.dataset.monthly.trim()))errors.push('billing toggle did not restore monthly prices');
return JSON.stringify({errors,proof:{before,yearly}});""",
}


def probe_script(recipe_id):
    return '(()=>{' + PROBES[recipe_id] + '})()'
