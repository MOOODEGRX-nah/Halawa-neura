"""Static skills, strict schemas, scoped/revocable grants, and bounded local history."""
import hashlib
import json
import re
import time
import uuid
from urllib.parse import urlencode, urlsplit
from pydantic import BaseModel, ConfigDict, Field, model_validator
from src.core.project_files import ProjectError
from src.core.project_store import now
from src.desktop.actions import DesktopAdapter


class Arguments(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Website(Arguments):
    destination: str = Field(min_length=1,max_length=2048)


class Search(Arguments):
    query: str = Field(min_length=1,max_length=1000)


class Application(Arguments):
    application_id: str = Field(pattern=r'^[A-Za-z0-9_.-]+\.desktop$',max_length=160)


class Location(Arguments):
    project_id: str | None = Field(default=None,pattern=r'^p_[a-f0-9]{32}$')
    path: str | None = Field(default=None,max_length=240)
    selection_id: str | None = Field(default=None,pattern=r'^l_[a-f0-9]{32}$')

    @model_validator(mode='after')
    def specific(self):
        if bool(self.project_id) == bool(self.selection_id) or (self.selection_id and self.path):
            raise ValueError('حدد مشروعًا أو مكانًا مختارًا واحدًا')
        return self


class Empty(Arguments):
    pass


NAMES = {'youtube':'https://www.youtube.com/','يوتيوب':'https://www.youtube.com/',
         'github':'https://github.com/','جيت هب':'https://github.com/',
         'brave':'https://search.brave.com/','برايف':'https://search.brave.com/'}
DEFINITIONS = {
    'open_website': (Website,'فتح موقع في Brave',['desktop:browser']),
    'search_web': (Search,'فتح نتائج بحث Brave',['desktop:browser']),
    'search_youtube': (Search,'فتح نتائج بحث YouTube في Brave',['desktop:browser']),
    'open_file': (Location,'عرض ملف مختار أو ملف مشروع دون تنفيذه',['desktop:file_view']),
    'open_folder': (Location,'فتح مجلد مشروع أو مكان مختار',['desktop:folder']),
    'open_application': (Application,'فتح تطبيق مثبت من السجل الموثوق',['desktop:application']),
    'list_recent_applications': (Empty,'قائمة التطبيقات التي فتحها Neura فقط',['history:neura']),
}


class PermissionDenied(ProjectError):
    status=403


def website_url(value):
    value=NAMES.get(value.casefold(),value)
    if any(ord(c)<33 or ord(c)==127 for c in value) or '\\' in value:
        raise ProjectError('عنوان الموقع غير صالح')
    try:parsed=urlsplit(value)
    except ValueError as exc:raise ProjectError('عنوان الموقع غير صالح') from exc
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
        raise ProjectError('استخدم عنوان HTTP أو HTTPS أو اسم موقع معروف.')
    try: parsed.port
    except ValueError as exc: raise ProjectError('منفذ الموقع غير صالح') from exc
    if len(parsed.hostname)>253:
        raise ProjectError('اسم الموقع يتجاوز الحد')
    return value


class DesktopSkills:
    def __init__(self,store,adapter=None):
        self.store=store
        self.adapter=adapter or DesktopAdapter(store)
        with store.lock:
            store.db.execute('CREATE TABLE IF NOT EXISTS skill_grants(id TEXT PRIMARY KEY,scope TEXT,name TEXT,label TEXT,expires REAL,reusable INTEGER,revoked INTEGER)')
            store.db.execute('CREATE TABLE IF NOT EXISTS skill_history(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT,label TEXT,status TEXT,application_id TEXT,created TEXT)')
            store.db.commit()

    def describe(self):
        status=self.adapter.status()
        result=[]
        for name,(schema,description,permissions) in DEFINITIONS.items():
            available=True if name=='list_recent_applications' else status['desktop_available'] and (status['brave_available'] if name in ('open_website','search_web','search_youtube') else True)
            if name=='open_file':available=available and status.get('text_viewer_available',True)
            if name=='open_folder':available=available and status.get('folder_viewer_available',True)
            result.append({'name':name,'description':description,'input_schema':schema.model_json_schema(),
                'output_schema':{'type':'object','required':['status','message'],'properties':{'status':{'type':'string'},'message':{'type':'string'}}},
                'permissions':permissions,'timeout_s':8,'available':bool(available),
                'unavailable_reason':'' if available else status['reason'] or ('محرر النصوص الموثوق غير متاح.' if name=='open_file' else 'مدير الملفات الموثوق غير متاح.' if name=='open_folder' else 'Brave غير متاح.')})
        return {'skills':result,'desktop':status,'recent_scope':'التطبيقات التي فتحها Neura فقط؛ ليست كل أنشطة KDE.'}

    def validate(self,name,args):
        if name not in DEFINITIONS:
            raise ProjectError('المهارة غير موجودة؛ تنفيذ الأوامر والمهارات المحمّلة غير مدعوم.')
        values=DEFINITIONS[name][0].model_validate(args).model_dump(exclude_none=True)
        if name=='open_website':
            values['destination']=website_url(values['destination'])
        if name=='open_file' and values.get('project_id') and not values.get('path'):
            raise ProjectError('اختر ملف المشروع المطلوب')
        if name=='open_file' and values.get('path'):
            from src.core.project_files import safe_path
            safe_path(values['path'])
        if name=='open_folder' and values.get('path'):
            raise ProjectError('فتح مجلد المشروع لا يقبل مسارًا إضافيًا')
        return values

    @staticmethod
    def scope(name,args):
        return hashlib.sha256(json.dumps([name,args],sort_keys=True,ensure_ascii=False).encode()).hexdigest()

    @staticmethod
    def label(name,args):
        if name=='open_website': return urlsplit(args['destination']).hostname
        if name in ('search_web','search_youtube'): return 'نتائج بحث Brave' if name=='search_web' else 'نتائج بحث YouTube'
        if name=='open_application':return args['application_id']
        if name in ('open_file','open_folder'):return 'ملف مشروع' if name=='open_file' else 'مجلد مختار'
        return 'سجل Neura المحلي'

    def authorize(self,name,args,remember=False):
        args=self.validate(name,args)
        scope=self.scope(name,args)
        grant='g_'+uuid.uuid4().hex
        with self.store.lock:
            if remember:
                existing=self.store.db.execute('SELECT id FROM skill_grants WHERE scope=? AND reusable=1 AND revoked=0 AND expires>?',(scope,time.time())).fetchone()
                if existing:return {'permission_id':existing['id'],'reused':True}
            self.store.db.execute('INSERT INTO skill_grants VALUES(?,?,?,?,?,?,0)',(grant,scope,name,self.label(name,args),time.time()+(86400 if remember else 90),int(remember)))
            self.store.db.commit()
        return {'permission_id':grant,'reused':False,'scope':'specific_action','expires_in_s':86400 if remember else 90}

    def revoke(self,permission_id):
        with self.store.lock:
            self.store.db.execute('UPDATE skill_grants SET revoked=1 WHERE id=?',(permission_id,));self.store.db.commit()
        return {'status':'revoked','message':'أُلغيت الصلاحية المحددة.'}

    def grants(self):
        with self.store.lock:
            rows=self.store.db.execute('SELECT id,name,label,expires FROM skill_grants WHERE revoked=0 AND reusable=1 AND expires>? ORDER BY expires DESC LIMIT 100',(time.time(),)).fetchall()
            return [dict(row) for row in rows]

    def execute(self,name,args,permission_id):
        args=self.validate(name,args)
        with self.store.lock:
            row=self.store.db.execute('SELECT * FROM skill_grants WHERE id=?',(permission_id,)).fetchone()
            if not row or row['revoked'] or row['expires']<time.time() or row['scope']!=self.scope(name,args):
                raise PermissionDenied('هذا الفعل يحتاج طلبًا صريحًا وصلاحية مطابقة؛ لم يُنفّذ شيء.')
            if not row['reusable']:
                self.store.db.execute('UPDATE skill_grants SET revoked=1 WHERE id=?',(permission_id,));self.store.db.commit()
        result=None
        try:
            if name=='open_website':result=self.adapter.browser(args['destination'])
            elif name=='search_web':result=self.adapter.browser('https://search.brave.com/search?'+urlencode({'q':args['query']}))
            elif name=='search_youtube':result=self.adapter.browser('https://www.youtube.com/results?'+urlencode({'search_query':args['query']}))
            elif name=='open_file':result=self.adapter.open_file(args)
            elif name=='open_folder':result=self.adapter.open_folder(args)
            elif name=='open_application':result=self.adapter.launch(args['application_id'])
            else:result={'status':'listed','message':'هذه التطبيقات فتحها Neura فقط. اختر تطبيقًا قبل فتحه.','applications':self.recent()}
            if name in ('search_web','search_youtube'):
                result['message']='أُرسل طلب فتح نتائج البحث في Brave؛ لم تُقرأ النتائج أو تُشاهد الفيديوهات.'
            return result
        finally:
            with self.store.lock:
                self.store.db.execute('INSERT INTO skill_history(name,label,status,application_id,created) VALUES(?,?,?,?,?)',
                    (name,self.label(name,args),result.get('status','error') if result else 'error',result.get('application_id') if result else None,now()))
                self.store.db.execute('DELETE FROM skill_history WHERE id NOT IN(SELECT id FROM skill_history ORDER BY id DESC LIMIT 100)')
                self.store.db.execute('DELETE FROM skill_grants WHERE expires<?',(time.time()-86400,))
                self.store.db.commit()

    def history(self):
        with self.store.lock:
            return [dict(x) for x in self.store.db.execute('SELECT name,label,status,created FROM skill_history ORDER BY id DESC LIMIT 50')]

    def recent(self):
        with self.store.lock:
            return [dict(x) for x in self.store.db.execute("SELECT application_id,MAX(created) AS last_launched FROM skill_history WHERE status='launched' AND application_id IS NOT NULL GROUP BY application_id ORDER BY last_launched DESC LIMIT 10")]
