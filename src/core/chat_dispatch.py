"""User-message routing, scoped desktop actions and durable retry protection.

Only the authenticated user-message endpoint calls this module. Model output and
project/preview contents are never inputs to this dispatcher.
"""
import hashlib
import json
import re
import time
import unicodedata
import uuid
from pydantic import ValidationError
from src.core.project_files import ProjectError,Conflict
from src.core.project_jobs import WorkspaceRequest
from src.tools.desktop_skills import website_url

REQUEST_ID=re.compile(r'^r_([0-9]{13})_[a-f0-9]{32}$')
DAY=86400


def normalize(text):
    text=unicodedata.normalize('NFKC',text).casefold()
    text=re.sub(r'[\u064b-\u065f\u0670\u0640]','',text)
    return re.sub(r'\s+',' ',text.translate(str.maketrans('أإآٱ','اااا'))).strip(' \t\r\n؟?!.،,')


def command_text(text):
    original=text.strip()
    if not original or original.startswith(('"',"'",'«','“','`','>','<','~~~')) or '```' in original:
        return ''
    q=normalize(text)
    for _ in range(4):
        before=q
        q=re.sub(r'^(?:لو سمحت|من فضلك|ارجوك|رجاء|رجاءا|ممكن|please)\s+','',q)
        q=re.sub(r'^(?:هل\s+(?:يمكنك|تستطيع|تقدر|بامكانك)|تقدر|تستطيع|يمكنك|بامكانك|اريد(?:\s+منك)?|ابي|ابغى|can you|could you|would you|i want you to)\s+(?:ان\s+)?','',q)
        if q==before:break
    if q!=normalize(text):
        q=re.sub(r'^فتح\s+','افتح ',q)
        q=re.sub(r'^(?:البحث|بحث)\s+','ابحث ',q)
        q=re.sub(r'^انشاء\s+','انشئ ',q)
    if re.match(r'^(?:لا\b|لاتفتح|ما تفتح|ماتفتح|ليس\b|لم\b|كيف\b|كيفية\b|اشرح\b|فسر\b|معنى\b|مثال\b|how\b|explain\b|do not\b|don.t\b|never\b)',q):return ''
    return q


def project_intent(text):
    q=command_text(text)
    return bool(re.match(r'^(?:انشئ|تنشئ|اصنع|تصنع|صمم|تصمم|ابن|ابني|تبني|اكتب|تكتب|create|build|design|make|write)\s+(?:لي\s+)?(?:موقع|برنامج|تطبيق|صفحة|مشروع|website|web ?app|application|project|program|landing page)\b',q))


def key(text):
    return ' '.join(w[2:] if w.startswith('ال') and len(w)>3 else w for w in normalize(text).replace('_',' ').replace('-',' ').split())


def metadata_intent(text):
    q=command_text(text)
    if not re.search(r'مشروع|project',q):return False
    return bool(re.search(r'^(?:ما|اي|what|which).*(?:لغة|لغات|غرض|هدف|purpose|languages?)',q) or
        re.search(r'^(?:ما\s*(?:هو|هذا|هي).*المشروع|what is (?:this|the) project)',q) or
        re.search(r'^(?:لماذا|why).*(?:انش|صنع|created|built)',q))


def workspace_intent(text):
    q=command_text(text)
    return bool(re.match(r'^(?:(?:عدل|تعدل|حرر|تحرر|edit|modify|update)\s+(?:لي\s+)?(?:(?:هذا|هاذه|هذه)\s+)?(?:المشروع|مشروع|موقع|الموقع|the project|this project|project)\b|(?:افتح|تفتح|open)\s+(?:لي\s+)?(?:مشروع|المشروع|project)\b)',q))


class ChatDispatcher:
    def __init__(self,store,skills,jobs):
        self.store,self.skills,self.jobs=store,skills,jobs
        with store.lock:
            store.db.execute('CREATE TABLE IF NOT EXISTS chat_requests(id TEXT PRIMARY KEY,fingerprint TEXT,state TEXT,response TEXT,options TEXT,selected TEXT,created REAL)')
            interrupted={'kind':'action','result':{'status':'unknown','message':'توقف التطبيق أثناء إرسال الطلب؛ راجع سطح المكتب والمشاريع قبل طلب تنفيذ جديد. لم تُعد المحاولة تلقائيًا.'}}
            store.db.execute("UPDATE chat_requests SET state='done',response=? WHERE state='running'",(json.dumps(interrupted,ensure_ascii=False),))
            store.db.commit()

    def _id(self,request_id,*,fresh=False):
        match=REQUEST_ID.fullmatch(request_id)
        if not match:raise ProjectError('معرّف الطلب غير صالح')
        stamp=int(match[1])/1000
        if fresh and not time.time()-DAY<=stamp<=time.time()+120:
            error=ProjectError('انتهت صلاحية إعادة المحاولة؛ لم يُنفذ الطلب. أرسل طلبًا جديدًا صريحًا عند الحاجة.');error.status=410;raise error

    @staticmethod
    def fingerprint(payload):
        return hashlib.sha256(json.dumps(payload,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

    def get(self,request_id):
        self._id(request_id)
        with self.store.lock:
            row=self.store.db.execute('SELECT * FROM chat_requests WHERE id=?',(request_id,)).fetchone()
            if not row:
                error=ProjectError('الطلب غير موجود');error.status=404;raise error
            if row['state']=='running':return {'kind':'pending','request_id':request_id,'message':'جارٍ تنفيذ الطلب نفسه؛ لم يبدأ تنفيذ إضافي.'}
            return json.loads(row['response'])

    def _run(self,request_id,payload,operation):
        self._id(request_id)
        fingerprint=self.fingerprint(payload)
        with self.store.lock:
            row=self.store.db.execute('SELECT * FROM chat_requests WHERE id=?',(request_id,)).fetchone()
            if row:
                if row['fingerprint']!=fingerprint:raise Conflict('معرّف إعادة المحاولة مرتبط بطلب مختلف؛ لم يُنفذ شيء.')
                return self.get(request_id)
            self._id(request_id,fresh=True)
            self.store.db.execute('DELETE FROM chat_requests WHERE created<?',(time.time()-2*DAY,))
            if self.store.db.execute('SELECT COUNT(*) FROM chat_requests').fetchone()[0]>=4096:
                error=ProjectError('سجل الطلبات ممتلئ مؤقتًا؛ انتظر قبل طلب تنفيذ جديد.');error.status=429;raise error
            self.store.db.execute('INSERT INTO chat_requests VALUES(?,?,?,?,?,?,?)',(request_id,fingerprint,'running',None,'[]',None,time.time()))
            self.store.db.commit()
        return self._finish(request_id,operation)

    def _finish(self,request_id,operation):
        try:
            result=operation()
        except FileNotFoundError:
            result={'kind':'action','result':{'status':'error','message':'الملف أو المجلد المحدد غير موجود؛ لم يُفتح شيء.'}}
        except ValidationError:
            result={'kind':'action','result':{'status':'error','message':'مدخلات المهارة غير صالحة؛ لم يُنفذ شيء.'}}
        except (ProjectError,ValueError,OSError) as exc:
            result={'kind':'action','result':{'status':'error','message':str(exc)[:500] or 'تعذر تنفيذ الطلب.'}}
        except Exception:
            # The desktop may have accepted a launch before a process failed.
            # Keep the record terminal; retry must never repeat an uncertain action.
            result={'kind':'action','result':{'status':'unknown','message':'تعذر تأكيد نتيجة الطلب؛ راجع سطح المكتب قبل طلب تنفيذ جديد.'}}
        options=result.pop('_options',[])
        result['request_id']=request_id
        with self.store.lock:
            self.store.db.execute('UPDATE chat_requests SET state=?,response=?,options=? WHERE id=?',
                ('choice' if options else 'done',json.dumps(result,ensure_ascii=False),json.dumps(options,ensure_ascii=False),request_id))
            self.store.db.commit()
        return result

    def _skill(self,name,args,permission_id=None):
        args=self.skills.validate(name,args)
        capability=next(s for s in self.skills.describe()['skills'] if s['name']==name)
        if not capability['available']:
            return {'kind':'action','skill':name,'result':{'status':'unavailable','message':capability['unavailable_reason']}}
        if permission_id is None:permission_id=self.skills.authorize(name,args)['permission_id']
        result=self.skills.execute(name,args,permission_id)
        if name=='list_recent_applications':
            names={a['id']:a['name'] for a in self.skills.adapter.status().get('applications',[])}
            result['applications']=[{**a,'display_name':names.get(a['application_id'],'تطبيق سابق')} for a in result.get('applications',[])]
        return {'kind':'action','skill':name,'result':result}

    def manual(self,name,args,permission_id,request_id):
        return self._run(request_id,['manual',name,args],lambda:self._skill(name,args,permission_id))

    @staticmethod
    def _choice(candidates,message):
        options=[{'id':'o_'+uuid.uuid4().hex,'label':label,'name':name,'args':args} for label,name,args in candidates[:8]]
        return {'kind':'clarification','message':message,'choices':[{'id':o['id'],'label':o['label']} for o in options],'_options':options}

    def _targets(self,candidates,target,message):
        exact=[c for c in candidates if key(c[0])==key(target)]
        matches=exact or [c for c in candidates if key(target) and key(target) in key(c[0])]
        if len(matches)==1:return self._skill(matches[0][1],matches[0][2])
        return self._choice(matches or candidates,message)

    def _workspace(self,args):
        project=self.store.get(args['project_id'])
        return {'kind':'workspace','project_id':project['project_id'],'display_name':project['display_name'],
                'edit_request':args.get('edit_request',''),
                'message':'فُتحت مساحة المشروع. راجع الملف المناسب وطلب التعديل قبل توليده.' if args.get('edit_request') else 'فُتحت مساحة المشروع المحفوظ.'}

    def _selected(self,name,args):
        return self._workspace(args) if name=='workspace' else self._skill(name,args)

    def _open_workspace(self,text,active_project_id):
        q=command_text(text)
        edit=bool(re.match(r'^(?:عدل|تعدل|حرر|تحرر|edit|modify|update)\b',q))
        target=re.sub(r'^(?:عدل|تعدل|حرر|تحرر|edit|modify|update|افتح|تفتح|open)\s+(?:لي\s+)?','',q)
        if re.match(r'^(?:(?:هذا|هذه)\s+)?(?:المشروع|the project|this project)(?:\s+(?:الحالي|current))?(?:$|\s+(?:و|ب|ل|اجعل|غير|change|with))',target) and active_project_id:
            return self._workspace({'project_id':active_project_id,'edit_request':text if edit else ''})
        target=re.sub(r'^(?:مشروع|المشروع|موقع|الموقع|project)\s*','',target)
        candidates=[]
        for project in self.store.list():
            title=re.sub(r'^(?:موقع|مشروع|المشروع)\s+','',normalize(project['display_name']))
            candidates.append((project['display_name'],'workspace',{'project_id':project['project_id'],'edit_request':text if edit else ''},key(title)))
        matches=[c for c in candidates if c[3] and (key(target)==c[3] or key(target).startswith(c[3]+' '))]
        if not candidates:return {'kind':'action','result':{'status':'error','message':'لا توجد مشاريع محفوظة بعد. اكتب طلب إنشاء المشروع في المحادثة أولًا.'}}
        if len(matches)==1:return self._workspace(matches[0][2])
        return self._choice([c[:3] for c in matches or candidates],'أي مشروع محفوظ تقصد؟ اختره لفتح مساحة المبرمج.')

    def resolve(self,text,active_project_id=None):
        q=command_text(text)
        if not q:return {'kind':'chat'}
        if project_intent(text):return {'kind':'project_intent'}
        if workspace_intent(text):return self._open_workspace(text,active_project_id)
        q=re.sub(r'\s+(?:من فضلك|لو سمحت|please)$','',q)
        if re.fullmatch(r'(?:اعرض|افتح|ما هي|list|show)\s+(?:اخر التطبيقات|التطبيقات الاخيرة|البرامج الاخيرة|recent apps|recent applications)',q):
            return self._skill('list_recent_applications',{})
        match=re.match(r'^(?:ابحث(?:لي)?|تبحث|search)\s+(?:لي\s+)?(?:(?:في|على|in|on)\s+)?(?:(?:ال)?يوتيوب|(?:ال)?يوتوب|يو تيوب|youtube|you tube)\s+(?:عن\s+|for\s+)?(.+)$',q)
        if match:return self._skill('search_youtube',{'query':self._original_query(text,match[1])})
        match=re.match(r'^(?:ابحث(?:لي)?|تبحث|search)\s+(?:لي\s+)?(?:(?:في الويب|في الانترنت|في brave|on the web)\s+)?(?:عن\s+|for\s+)(.+)$',q)
        if match:return self._skill('search_web',{'query':self._original_query(text,match[1])})
        match=re.match(r'^(?:افتح(?:لي)?|تفتح(?:لي)?|open|launch)\s+(?:لي\s+)?(.+)$',q)
        if not match:return {'kind':'chat'}
        target=match[1].strip()
        if target.startswith(('مجلد مشروع ','مجلد المشروع')):
            title=re.sub(r'^مجلد (?:المشروع|مشروع)\s*','',target)
            if not title and active_project_id:return self._skill('open_folder',{'project_id':active_project_id})
            candidates=[(p['display_name'],'open_folder',{'project_id':p['project_id']}) for p in self.store.list()]
            return self._targets(candidates,title,'أي مشروع تقصد؟ اختر مجلد المشروع المطلوب هنا.')
        status=self.skills.adapter.status()
        explicit_site=bool(re.match(r'^(?:موقع|website|site)\s+',target))
        target=re.sub(r'^(?:موقع|متصفح|تطبيق|برنامج|website|site|browser|application|app)\s+','',target)
        aliases={'يوتيوب':'https://www.youtube.com/','يوتوب':'https://www.youtube.com/','اليوتيوب':'https://www.youtube.com/','اليوتوب':'https://www.youtube.com/','يو تيوب':'https://www.youtube.com/','youtube':'https://www.youtube.com/','you tube':'https://www.youtube.com/',
                 'جيت هب':'https://github.com/','جيتهاب':'https://github.com/','github':'https://github.com/'}
        if target in aliases:return self._skill('open_website',{'destination':aliases[target]})
        if target in ('brave','برايف','بريف','براڤ'):
            if explicit_site:return self._skill('open_website',{'destination':'https://search.brave.com/'})
            config=getattr(self.skills.adapter,'configuration',lambda:{})()
            app_id=config.get('brave_desktop_id','brave-browser.desktop')
            if not status['brave_available']:return {'kind':'action','result':{'status':'unavailable','message':'Brave غير مثبت أو لم يُضبط. اختر تطبيق Brave من إعدادات Neura.'}}
            return self._skill('open_application',{'application_id':app_id})
        if explicit_site or re.match(r'^[a-z][a-z0-9+.-]*:',target) or re.match(r'^(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/|$)',target):
            # Preserve URL path/query case; normalization is only for intent words.
            raw=re.search(r'https?://\S+',text,re.I)
            destination=raw[0].rstrip('؟?!.,،') if raw else target
            if '://' not in destination and re.match(r'^(?:[a-z0-9-]+\.)+[a-z]{2,}(?:/|$)',destination):destination='https://'+destination
            return self._skill('open_website',{'destination':website_url(destination)})
        kind='folder' if target.startswith('مجلد ') else 'file' if target.startswith('ملف ') else None
        name=re.sub(r'^(?:ملف|مجلد)\s+','',target)
        candidates=[(p['name'],'open_'+p['kind'],{'selection_id':p['id']}) for p in status.get('locations',[]) if kind is None or p['kind']==kind]
        if kind:return self._targets(candidates,name,'أي ملف أو مجلد مختار تقصد؟ اختره هنا، أو أضف مكانًا من إعدادات Neura.')
        aliases={'كيت':'org.kde.kate.desktop','kate':'org.kde.kate.desktop','دولفين':'org.kde.dolphin.desktop','مدير الملفات':'org.kde.dolphin.desktop','الحاسبة':'org.kde.kcalc.desktop','الالة الحاسبة':'org.kde.kcalc.desktop','kcalc':'org.kde.kcalc.desktop'}
        apps=[(a['name'],'open_application',{'application_id':a['id']}) for a in status.get('applications',[])]
        alias=aliases.get(target)
        if alias:
            found=next((a for a in apps if a[2]['application_id']==alias),None)
            if found:return self._skill(found[1],found[2])
        return self._targets(candidates+apps,target,'الاسم غير محدد أو له أكثر من مطابقة. أي هدف تقصد؟')

    @staticmethod
    def _original_query(original,normalized):
        # Keep case/diacritics in the user's search. Find a matching suffix,
        # accounting for polite suffixes stripped from the command grammar.
        original=re.sub(r'\s+(?:من فضلك|لو سمحت|please)[؟?!.،,\s]*$','',original,flags=re.I).rstrip('؟?!.،, ')
        words=original.split()
        for i in range(len(words)):
            suffix=' '.join(words[i:])
            if normalize(suffix)==normalized:return suffix
        return normalized

    def dispatch(self,text,request_id,active_project_id=None):
        # Unrecognized ordinary chat never creates a ledger entry or loads a model.
        q=command_text(text)
        action=bool(re.match(r'^(?:افتح(?:لي)?|تفتح(?:لي)?|open|launch|ابحث(?:لي)?|تبحث|search|اعرض|list|show|ما هي)\b',q))
        metadata=bool(active_project_id and metadata_intent(text))
        if not action and not project_intent(text) and not workspace_intent(text) and not metadata:return {'kind':'chat'}
        def operation():
            if metadata:
                answer=self.store.answer(active_project_id,text)
                return {'kind':'metadata','message':answer['answer']+'\n— من فهرس المشروع، دون استدعاء نموذج.','project_id':active_project_id,'model_called':False,'source':answer['source']}
            result=self.resolve(text,active_project_id)
            if result['kind']=='project_intent':
                title='موقع السيرة الذاتية' if 'سيرة' in q else re.sub(r'^\S+\s+(?:لي\s+)?','',text.strip())[:70]
                created=self.jobs.create(WorkspaceRequest(user_request=text,requirements=[text],title=title,background=True,max_tokens=4096))
                return {'kind':'project',**created}
            return result
        return self._run(request_id,['chat',text,active_project_id],operation)

    def choose(self,request_id,choice_id):
        self._id(request_id)
        with self.store.lock:
            row=self.store.db.execute('SELECT * FROM chat_requests WHERE id=?',(request_id,)).fetchone()
            if not row:raise ProjectError('طلب الاختيار غير موجود')
            if row['selected']:
                if row['selected']!=choice_id:raise Conflict('تم اختيار هدف لهذا الطلب بالفعل؛ لم يُفتح هدف إضافي.')
                return self.get(request_id)
            if row['state']!='choice':raise ProjectError('هذا الطلب لا ينتظر اختيارًا')
            self._id(request_id,fresh=True)
            option=next((o for o in json.loads(row['options']) if o['id']==choice_id),None)
            if not option:raise ProjectError('الاختيار لا ينتمي إلى هذا الطلب')
            self.store.db.execute("UPDATE chat_requests SET state='running',selected=? WHERE id=?",(choice_id,request_id));self.store.db.commit()
        return self._finish(request_id,lambda:self._selected(option['name'],option['args']))
