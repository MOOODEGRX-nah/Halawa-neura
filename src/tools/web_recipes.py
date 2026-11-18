"""Reviewed offline web recipes (bounded catalog). Catalog text is data, never tool authority."""
import hashlib,json,re
from html.parser import HTMLParser
from typing import Literal
from pydantic import BaseModel,ConfigDict,Field
from src.core.project_files import ProjectError

ID='arabic_cv_v1'
FILES=['index.html','style.css','script.js']
CONSTRAINTS=[
    'Offline Arabic CV: index.html with html lang=ar dir=rtl, linked style.css and deferred script.js. No imports, remote assets, fonts, fetch, cloud, build tools or dependencies.',
    'Arabic visible headings and clearly labelled placeholders for name, about, skills and contact. Do not invent personal facts, degrees, employers or contact details. Include the actual user-provided content when supplied.',
    'Include one visible type=button with id=cv-font-toggle, aria-controls=cv-content, aria-pressed=false and fixed Arabic label تكبير الخط. Main content has id=cv-content and a visible paragraph.',
    'script.js wires that button to toggle the body class cv-large-text and aria-pressed true/false. style.css increases the actual paragraph font size inside #cv-content in cv-large-text state. A second click restores the original state. No storage, dialogs or native capabilities.',
    'Preserve text, links, control identities, working font-size toggle and any subsequently accepted Login/theme through edits. Keep a simple readable responsive design with flat solid backgrounds and no gradients. Normal text contrast at least 4.5:1.'
]


# B2: an independently testable recipe with a meaningful interaction (category filter).
SERVICES_ID='arabic_services_v1'
SERVICES_CONSTRAINTS=[
    'Offline Arabic service directory: index.html with html lang=ar dir=rtl, meta charset utf-8, meta viewport width=device-width, an Arabic meta description of 30 to 170 characters and exactly one h1 heading; linked style.css and deferred script.js. No imports, remote assets, fonts, fetch, cloud, storage, build tools or dependencies.',
    'A filter group id=service-filters with role=group and an Arabic aria-label holds native type=button filters with class service-filter and data-category: exactly one data-category=all labelled الكل with aria-pressed=true, plus at least three category filters with Arabic labels and aria-pressed=false.',
    'A list id=service-list holds at least six li elements with class service-card and a data-category equal to one of the filter categories (every category used). Each card has an Arabic heading and a clearly labelled placeholder description; do not invent real business names, phone numbers or addresses.',
    'script.js: activating a filter sets aria-pressed=true on it and false on the others, and sets the hidden attribute on every card whose data-category differs (all shows every card). An element id=service-count with aria-live=polite states the visible count in Arabic. Keep native buttons so Tab, Enter and Space work.',
    'style.css: one column below 600px and a grid on wider screens; a clearly visible :focus-visible outline on buttons; [hidden]{display:none}; @media (prefers-reduced-motion: reduce) disabling transitions and animations. Flat solid backgrounds, normal text contrast at least 4.5:1. Preserve content, filters and behavior through edits.'
]
RECIPES={ID:{'files':FILES,'constraints':CONSTRAINTS,'scope':'Static offline Arabic CV; model-generated files, mandatory planning and independent source/browser checks; no native program execution','skill':'prepare_static_cv','label':'وصفة CV عربية محلية v1'},
         SERVICES_ID:{'version':2,'files':FILES,'constraints':SERVICES_CONSTRAINTS,'scope':'Static offline Arabic RTL service directory with a keyboard-operable category filter; model-generated files, mandatory planning and independent source/browser checks; no native program execution','skill':'prepare_static_services','label':'وصفة دليل خدمات عربي محلي v1'}}
RECIPE_IDS=tuple(RECIPES)


class RecipeArguments(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    recipe_id:Literal['arabic_cv_v1']=ID


class ServicesRecipeArguments(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    recipe_id:Literal['arabic_services_v1']=SERVICES_ID


class RecipeManifest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    id:Literal['arabic_cv_v1','arabic_services_v1']
    version:Literal[1,2]
    sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    required_files:list[str]
    constraints:list[str]
    scope:str


def manifest(recipe_id=ID):
    if recipe_id not in RECIPES:raise ProjectError('وصفة الويب غير معروفة')
    recipe=RECIPES[recipe_id]
    data={'id':recipe_id,'version':recipe.get('version',1),'required_files':list(recipe['files']),'constraints':list(recipe['constraints']),'scope':recipe['scope']}
    return {**data,'sha256':hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}


def skill_for(recipe_id):
    if recipe_id not in RECIPES:raise ProjectError('وصفة الويب غير معروفة')
    return RECIPES[recipe_id]['skill']


LOCAL=r'عربي|عربيا|محلي|محليا|بدون انترنت|دون انترنت|بلا انترنت|وصفة|\b(?:arabic|offline|recipe)\b'
STACKS=r'(?<!\w)(?:react|next(?:js|\.js)?|vue|angular|svelte|tsx|typescript|django|flask|node|php|wordpress)(?!\w)|https?://|خطوط جوجل|google fonts'


def select_for_request(text,validated_intent):
    """Bounded selection only AFTER admission of a user-origin create request."""
    if validated_intent!='project.create':return None
    from src.core.user_commands import command_text
    q=command_text(text)
    if not q:return None
    if re.search(r'(?<!\w)cv\b|سير[هة]\s+(?:ال)?ذاتي[هة]',q,re.I):recipe=ID
    elif re.search(r'دليل\s+(?:ال)?خدمات|(?:ال)?خدمات\s+(?:مع|مصنف|حسب|بفلتر|بتصفي)|\bservices?\s+directory\b',q,re.I):recipe=SERVICES_ID
    else:return None
    if not re.search(LOCAL,q,re.I):return None
    if re.search(STACKS,q,re.I):return None
    named=re.findall(r'[\w./-]+\.(?:html?|css|js|jsx|ts|tsx)\b',q,re.I)
    if any(p not in FILES for p in named):return None
    return recipe


class Structure(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=True);self.elements=[];self.words=[];self.ignore=0
    def handle_starttag(self,tag,attrs):
        self.elements.append((tag,dict(attrs)))
        if tag in ('head','script','style'):self.ignore+=1
    def handle_endtag(self,tag):
        if tag in ('head','script','style'):self.ignore=max(0,self.ignore-1)
    def handle_data(self,text):
        if not self.ignore:self.words.append(text)


def validate_source(files,recipe_id):
    if recipe_id==SERVICES_ID:return validate_services(files)
    if recipe_id!=ID:raise ProjectError('وصفة الويب غير معروفة')
    if set(FILES)-files.keys():raise ProjectError('الوصفة تحتاج index.html وstyle.css وscript.js بأسمائها الصحيحة')
    if any(not isinstance(files[p],str) for p in FILES):raise ProjectError('ملفات الوصفة يجب أن تكون نصية')
    p=Structure();p.feed(files['index.html']);p.close();elements=p.elements
    if not any(t=='html' and a.get('lang','').startswith('ar') and a.get('dir')=='rtl' for t,a in elements):raise ProjectError('الوصفة تتطلب HTML عربيًا وRTL')
    if any(len(re.findall(r'</'+tag+r'\s*>',files['index.html'],re.I))!=1 or sum(t==tag for t,a in elements)!=1 for tag in ('html','head','body')):raise ProjectError('الوصفة تحتاج مستند HTML كاملًا واحدًا دون نهايات مكررة')
    if sum(t=='script' and a.get('src') in ('script.js','./script.js') for t,a in elements)!=1:raise ProjectError('مرجع script.js يجب أن يظهر مرة واحدة')
    ids=[a.get('id') for t,a in elements]
    if ids.count('cv-font-toggle')!=1 or ids.count('cv-content')!=1:raise ProjectError('هوية زر الخط أو المحتوى مفقودة أو مكررة')
    if not any(t=='button' and a.get('id')=='cv-font-toggle' and a.get('type')=='button' and a.get('aria-controls')=='cv-content' and a.get('aria-pressed')=='false' for t,a in elements):raise ProjectError('زر الخط لا يطابق عقد الوصفة')
    if not any(t=='link' and a.get('rel')=='stylesheet' and a.get('href') in ('style.css','./style.css') for t,a in elements) or not any(t=='script' and a.get('src') in ('script.js','./script.js') for t,a in elements):raise ProjectError('مراجع CSS/JavaScript لا تطابق الملفات المطلوبة')
    if len(re.findall(r'[\u0600-\u06ff]{2,}',' '.join(p.words)))<4:raise ProjectError('محتوى CV العربي مفقود')
    for tag,a in elements:
        if tag in ('iframe','object','embed','form','base'):raise ProjectError('عناصر خدمات/تنقل غير مدعومة في الوصفة المحلية')
        for key in ('src','srcset','poster'):
            if a.get(key) and re.search(r'^(?:[a-z][a-z0-9+.-]*:|//)',a[key],re.I):raise ProjectError('الوصفة لا تقبل موارد خارجية')
        if tag=='link' and a.get('href') not in ('style.css','./style.css'):raise ProjectError('الوصفة لا تقبل خطوطًا أو روابط موارد خارجية')
    if re.search(r'@import|https?://|url\(\s*[\'"]?(?://|[a-z]+:)',files['style.css'],re.I) or re.search(r'\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|importScripts)\s*\(|\bimport\s*(?:\(|[\'{*])|\b(?:localStorage|sessionStorage)\b',files['script.js']):raise ProjectError('الوصفة محلية بلا شبكة أو تخزين أو imports')
    return {'recipe':manifest(),'status':'passed','scope':'Source structure/offline references only; behavior requires isolated browser checks'}


def repair_missing_button_type(files,recipe_id,failure,revision,binding):
    """One exact, deterministic shape repair; no fuzzy anchor or guessed code.

    A known recipe control may omit its explicit HTML type. Only that missing
    attribute is eligible; duplicate controls/attributes and conflicting values
    are never rewritten. The result still passes all independent gates.
    """
    if recipe_id==SERVICES_ID:return repair_missing_filter_attributes(files,failure,revision,binding)
    if recipe_id!=ID or failure!='زر الخط لا يطابق عقد الوصفة' or not isinstance(files.get('index.html'),str):return None
    source=files['index.html'];matches=[];ids=[]
    class Tags(HTMLParser):
        def handle_starttag(self,tag,attrs):
            values=dict(attrs)
            if values.get('id')=='cv-font-toggle':
                ids.append(tag)
                if tag!='button' or len(attrs)!=len(values):return
                if values.get('aria-controls')!='cv-content' or values.get('aria-pressed')!='false' or 'type' in values:return
                line,column=self.getpos();start=sum(len(s) for s in source.splitlines(keepends=True)[:line-1])+column;raw=self.get_starttag_text()
                if raw.endswith('/>') or source[start:start+len(raw)]!=raw:return
                matches.append((start,start+len(raw),raw[:-1]+' type="button">'))
    parser=Tags();parser.feed(source);parser.close()
    if ids!=['button'] or len(matches)!=1:return None
    start,end,after=matches[0]
    from src.core.repair_targets import RepairTargets
    targets=RepairTargets(files,revision,binding,ranges={'index.html':[(start,end)]});target_id=next(iter(targets.targets));edits=[{'target_id':target_id,'after':after}]
    result=targets.apply(files,edits,revision,binding)
    validate_source(result,recipe_id)
    return result,{'mode':'recipe_missing_explicit_button_type','repair_targets':targets.manifest(),'edits':edits,'model_called':False,'scope':'Only missing type=button in a uniquely identified validated recipe control; not acceptance until source/browser revalidation'}


def offline_document(files,recipe_id):
    """Shared source checks: full RTL Arabic document, linked local files, no network/storage."""
    if set(FILES)-files.keys():raise ProjectError('الوصفة تحتاج index.html وstyle.css وscript.js بأسمائها الصحيحة')
    if any(not isinstance(files[p],str) for p in FILES):raise ProjectError('ملفات الوصفة يجب أن تكون نصية')
    p=Structure();p.feed(files['index.html']);p.close();elements=p.elements
    if not any(t=='html' and a.get('lang','').startswith('ar') and a.get('dir')=='rtl' for t,a in elements):raise ProjectError('الوصفة تتطلب HTML عربيًا وRTL')
    if any(len(re.findall(r'</'+tag+r'\s*>',files['index.html'],re.I))!=1 or sum(t==tag for t,a in elements)!=1 for tag in ('html','head','body')):raise ProjectError('الوصفة تحتاج مستند HTML كاملًا واحدًا دون نهايات مكررة')
    if sum(t=='script' and a.get('src') in ('script.js','./script.js') for t,a in elements)!=1:raise ProjectError('مرجع script.js يجب أن يظهر مرة واحدة')
    if not any(t=='link' and a.get('rel')=='stylesheet' and a.get('href') in ('style.css','./style.css') for t,a in elements):raise ProjectError('مراجع CSS/JavaScript لا تطابق الملفات المطلوبة')
    for tag,a in elements:
        if tag in ('iframe','object','embed','form','base'):raise ProjectError('عناصر خدمات/تنقل غير مدعومة في الوصفة المحلية')
        for key in ('src','srcset','poster'):
            if a.get(key) and re.search(r'^(?:[a-z][a-z0-9+.-]*:|//)',a[key],re.I):raise ProjectError('الوصفة لا تقبل موارد خارجية')
        if tag=='link' and a.get('href') not in ('style.css','./style.css'):raise ProjectError('الوصفة لا تقبل خطوطًا أو روابط موارد خارجية')
    if re.search(r'@import|https?://|url\(\s*[\'"]?(?://|[a-z]+:)',files['style.css'],re.I) or re.search(r'\b(?:fetch|XMLHttpRequest|WebSocket|EventSource|importScripts)\s*\(|\bimport\s*(?:\(|[\'{*])|\b(?:localStorage|sessionStorage|indexedDB)\b',files['script.js']):raise ProjectError('الوصفة محلية بلا شبكة أو تخزين أو imports')
    return p


def validate_services(files):
    p=offline_document(files,SERVICES_ID);elements=p.elements
    ids=[a.get('id') for t,a in elements]
    for required in ('service-filters','service-list','service-count'):
        if ids.count(required)!=1:raise ProjectError('هوية '+required+' مفقودة أو مكررة')
    group=next(a for t,a in elements if a.get('id')=='service-filters')
    if group.get('role')!='group' or not re.search(r'[\u0600-\u06ff]',group.get('aria-label','')):raise ProjectError('مجموعة التصفية تحتاج role=group ووصفًا عربيًا')
    if next(a for t,a in elements if a.get('id')=='service-count').get('aria-live')!='polite':raise ProjectError('عداد الخدمات يحتاج aria-live=polite')
    filters=[(t,a) for t,a in elements if 'service-filter' in (a.get('class') or '').split()]
    if any(t!='button' or a.get('type')!='button' or not a.get('data-category') or a.get('aria-pressed') not in ('true','false') for t,a in filters):raise ProjectError('أزرار التصفية تحتاج button type=button وdata-category وaria-pressed')
    categories=[a['data-category'] for t,a in filters]
    if categories.count('all')!=1 or len(set(categories))!=len(categories) or len(categories)<4:raise ProjectError('التصفية تحتاج «الكل» مرة واحدة وثلاث فئات مميزة على الأقل')
    if [a.get('aria-pressed') for t,a in filters if a['data-category']=='all']!=['true'] or any(a.get('aria-pressed')!='false' for t,a in filters if a['data-category']!='all'):raise ProjectError('حالة aria-pressed الابتدائية للتصفية غير صحيحة')
    cards=[a.get('data-category') for t,a in elements if t=='li' and 'service-card' in (a.get('class') or '').split()]
    if len(cards)<6 or any(c not in categories or c=='all' for c in cards) or set(categories)-{'all'}-set(cards):raise ProjectError('قائمة الخدمات تحتاج ست بطاقات على الأقل تغطي كل الفئات')
    if len(re.findall(r'[\u0600-\u06ff]{2,}',' '.join(p.words)))<12:raise ProjectError('محتوى دليل الخدمات العربي مفقود')
    # B3 (recipe v2): metadata and heading structure measured on real generated sites.
    from src.core.web_quality import report as quality
    items=quality(files,'index.html')['items']
    if not (items['meta_description']['ok'] and items['viewport']['ok'] and items['charset']['ok']):raise ProjectError('الوصفة تحتاج meta description عربيًا (30–170 حرفًا) وviewport وcharset')
    if not items['single_h1']['ok']:raise ProjectError('الوصفة تحتاج عنوان h1 واحدًا بالضبط')
    css=files['style.css']
    if not re.search(r':focus-visible',css) or not re.search(r'@media[^{]*prefers-reduced-motion\s*:\s*reduce',css,re.I) or not re.search(r'\[hidden\]',css):raise ProjectError('الوصفة تحتاج :focus-visible و[hidden] وprefers-reduced-motion في style.css')
    return {'recipe':manifest(SERVICES_ID),'status':'passed','categories':categories,'cards':len(cards),'scope':'Source structure/offline references only; filtering/keyboard behavior requires isolated browser checks'}


FILTER_SHAPE_ERROR='أزرار التصفية تحتاج button type=button وdata-category وaria-pressed'


def repair_missing_filter_attributes(files,failure,revision,binding):
    """Deterministic shape repair for arabic_services_v1 filters; no model, no fuzzy anchors.

    Only for the exact filter-shape failure. Every element with class service-filter must be a
    <button> start tag with a unique data-category and no duplicate attributes. Only MISSING
    type and aria-pressed are added (type=button; aria-pressed=true for «all», false otherwise);
    any present but different value is a conflict and nothing is rewritten. The result must pass
    the full source contract, then the browser gate, like any candidate.
    """
    if failure!=FILTER_SHAPE_ERROR or not isinstance(files.get('index.html'),str):return None
    source=files['index.html'];ranges=[];edits=[];conflict=[]
    offsets=[0]
    for line in source.splitlines(keepends=True):offsets.append(offsets[-1]+len(line))
    class Tags(HTMLParser):
        def handle_starttag(self,tag,attrs):
            values=dict(attrs)
            if 'service-filter' not in (values.get('class') or '').split():return
            line,column=self.getpos();start=offsets[line-1]+column;raw=self.get_starttag_text()
            if tag!='button' or len(attrs)!=len(values) or not values.get('data-category') or raw.endswith('/>') or source[start:start+len(raw)]!=raw:conflict.append(raw);return
            if values.get('type') not in (None,'button') or values.get('aria-pressed') not in (None,'true','false'):conflict.append(raw);return
            missing=('' if 'type' in values else ' type="button"')+('' if 'aria-pressed' in values else ' aria-pressed="'+('true' if values['data-category']=='all' else 'false')+'"')
            if missing:ranges.append((start,start+len(raw)));edits.append(raw[:-1]+missing+'>')
    parser=Tags();parser.feed(source);parser.close()
    categories=re.findall(r'data-category="([^"]*)"',''.join(edits))
    if conflict or not edits:return None
    from src.core.repair_targets import RepairTargets
    targets=RepairTargets(files,revision,binding,ranges={'index.html':ranges})
    by_start={t.start:t.target_id for t in targets.targets.values()}
    patch=[{'target_id':by_start[start],'after':after} for (start,_),after in zip(ranges,edits)]
    result=targets.apply(files,patch,revision,binding)
    # Confirm only the shape this repair owns; any other remaining failure is left to the normal
    # validation of the next bounded attempt instead of ending the job here.
    try:validate_source(result,SERVICES_ID)
    except ProjectError as error:
        if str(error)==FILTER_SHAPE_ERROR:return None
    return result,{'mode':'recipe_missing_filter_attributes','repair_targets':targets.manifest(),'edits':patch,'model_called':False,
                   'scope':'Only missing type/aria-pressed on uniquely identified service-filter buttons; not acceptance until source/browser revalidation'}
