"""Conservative source preservation gates, not a claim of semantic equivalence."""
import json
import re
from html.parser import HTMLParser
from src.core.application_targets import normalize
from src.core.project_files import ProjectError


class AcceptedHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden=0;self.text=[];self.controls=[];self.current=None

    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag in ('script','style','head'):self.hidden+=1
        if tag in ('a','button','input','select','textarea'):
            item={k:attrs[k] for k in ('id','href','name','type') if attrs.get(k)}
            item['tag']=tag;item['label']=[];self.controls.append(item)
            self.current=item if tag!='input' else None

    def handle_data(self,data):
        if not self.hidden and data.strip():
            self.text.append(data.strip())
            if self.current is not None:self.current['label'].append(data.strip())

    def handle_endtag(self,tag):
        if tag in ('script','style','head'):self.hidden=max(0,self.hidden-1)
        if tag in ('a','button','select','textarea'):self.current=None


def html_contract(files):
    result={}
    for path,value in files.items():
        if not path.endswith(('.html','.htm')) or not isinstance(value,str):continue
        parsed=AcceptedHTML();parsed.feed(value);parsed.close()
        result[path]={'text':[' '.join(x.split()) for x in parsed.text],
                      'controls':[{**c,'label':' '.join(c['label'])} for c in parsed.controls]}
    return result


def contract_summary(files,requirements=()):
    complete=html_contract(files)
    summary={path:{'text':value['text'][:100],'controls':value['controls'][:50],
                   'bounded':len(value['text'])>100 or len(value['controls'])>50} for path,value in list(complete.items())[:10]}
    return {'version':1,'provenance':'accepted saved source; bounded orientation, full source is checked for edits',
            'requirements':list(requirements)[-20:],'html':summary}


def preservation_errors(before,after,user_request):
    old,new=html_contract(before),html_contract(after);errors=[]
    q=normalize(user_request)
    removal=bool(re.match(r'^(?:احذف|ازل|remove|delete)\b',q))
    # Only an explicitly named label is removable. A generic removal request is
    # not permission to remove all content or every control.
    def waived(label):
        label=normalize(label)
        return bool(removal and len(label)>=3 and label in q)
    for path,contract in old.items():
        candidate=new.get(path)
        if candidate is None:
            errors.append('Required HTML file removed: '+path);continue
        text=' '.join(candidate['text'])
        for chunk in contract['text']:
            if len(chunk)>1 and chunk not in text and not waived(chunk):
                errors.append(path+': existing visible content removed: '+chunk[:100])
        for control in contract['controls']:
            if waived(control['label']):continue
            if not any(all(other.get(k)==v for k,v in control.items()) for other in candidate['controls']):
                errors.append(path+': existing control changed/removed: '+json.dumps(control,ensure_ascii=False)[:180])
    return errors[:20]


def require_preserved(before,after,request):
    errors=preservation_errors(before,after,request)
    if errors:raise ProjectError('فشل الحفاظ على ميزات المشروع: '+'; '.join(errors)[:2000])
    return {'status':'passed','scope':'HTML visible text and control identities/labels/references',
            'behavioral_equivalence':'not_proven'}
