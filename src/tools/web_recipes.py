"""One reviewed offline recipe. Catalog text is data, never tool authority."""
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


class RecipeArguments(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    recipe_id:Literal['arabic_cv_v1']=ID


class RecipeManifest(BaseModel):
    model_config=ConfigDict(extra='forbid',strict=True)
    id:Literal['arabic_cv_v1']
    version:Literal[1]
    sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    required_files:list[str]
    constraints:list[str]
    scope:str


def manifest():
    data={'id':ID,'version':1,'required_files':list(FILES),'constraints':list(CONSTRAINTS),'scope':'Static offline Arabic CV; model-generated files, mandatory planning and independent source/browser checks; no native program execution'}
    return {**data,'sha256':hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True).encode()).hexdigest()}


def select_for_request(text,validated_intent):
    """Bounded selection only AFTER admission of a user-origin create request."""
    if validated_intent!='project.create':return None
    from src.core.user_commands import command_text
    q=command_text(text)
    if not q or not re.search(r'(?<!\w)cv\b|سير[هة]\s+(?:ال)?ذاتي[هة]',q,re.I):return None
    if not re.search(r'عربي|عربيا|محلي|محليا|بدون انترنت|دون انترنت|بلا انترنت|وصفة|\b(?:arabic|offline|recipe)\b',q,re.I):return None
    if re.search(r'(?<!\w)(?:react|next(?:js|\.js)?|vue|angular|svelte|tsx|typescript|django|flask|node|php|wordpress)(?!\w)|https?://|خطوط جوجل|google fonts',q,re.I):return None
    named=re.findall(r'[\w./-]+\.(?:html?|css|js|jsx|ts|tsx)\b',q,re.I)
    if any(p not in FILES for p in named):return None
    return ID


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
    if recipe_id!=ID:raise ProjectError('وصفة الويب غير معروفة')
    if set(FILES)-files.keys():raise ProjectError('الوصفة تحتاج index.html وstyle.css وscript.js بأسمائها الصحيحة')
    if any(not isinstance(files[p],str) for p in FILES):raise ProjectError('ملفات الوصفة يجب أن تكون نصية')
    p=Structure();p.feed(files['index.html']);p.close();elements=p.elements
    if not any(t=='html' and a.get('lang','').startswith('ar') and a.get('dir')=='rtl' for t,a in elements):raise ProjectError('الوصفة تتطلب HTML عربيًا وRTL')
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
