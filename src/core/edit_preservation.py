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


def removed_control_labels(contracts,feature_contract):
    from src.core.feature_intent import validate_contract
    removals={c['feature'] for c in validate_contract(feature_contract).get('changes',[]) if c['operation']=='remove'}
    return control_labels_for_features(contracts,removals)


def control_labels_for_features(contracts,features):
    return {normalize(c['label']) for value in contracts.values() for c in value.get('controls',[]) if ('theme' in features and re.search(r'theme|dark|داكن|ليلي|مظلم',c['label'],re.I)) or ('login' in features and re.search(r'login|sign.?in|تسجيل الدخول|تسجيل دخول',c['label'],re.I))}


def contract_summary(files,requirements=()):
    complete=html_contract(files)
    summary={path:{'text':value['text'][:100],'controls':value['controls'][:50],
                   'bounded':len(value['text'])>100 or len(value['controls'])>50} for path,value in list(complete.items())[:10]}
    return {'version':1,'provenance':'accepted saved source; bounded orientation, full source is checked for edits',
            'requirements':list(requirements)[-20:],'html':summary}


def preservation_errors(before,after,user_request,contract=None):
    old,new=html_contract(before),html_contract(after);errors=[]
    q=normalize(user_request)
    removable_labels=removed_control_labels(old,contract)
    structured=bool(contract)
    if contract:
        from src.core.feature_intent import validate_contract
        forbidden=control_labels_for_features(new,validate_contract(contract).get('excluded',{}))
        if forbidden:errors.append('Explicitly excluded feature returned: '+', '.join(sorted(forbidden)))
    removal=bool(re.match(r'^(?:احذف|ازل|remove|delete)\b',q))
    # Only an explicitly named label is removable. A generic removal request is
    # not permission to remove all content or every control.
    def waived(label):
        label=normalize(label)
        if label in removable_labels:return True
        if structured:return False
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


def require_preserved(before,after,request,contract=None):
    errors=preservation_errors(before,after,request,contract)
    if errors:raise ProjectError('فشل الحفاظ على ميزات المشروع: '+'; '.join(errors)[:2000])
    return {'status':'passed','required_feature_contract':contract,'scope':'HTML visible text and control identities/labels/references',
            'behavioral_equivalence':'not_proven'}


def requested_web_features(contract):
    """Consume admission's contract; never reclassify conversation/source text."""
    from src.core.feature_intent import contract_features
    return contract_features(contract)


_ADD=r'^(?:اضف|ادرج|ضع|add|insert|include)\b'
_STOP=r'(?:ضمن|في|مع|تحت|الى|إلى|داخل|بجانب|بعد|قبل|لكي|حتى|under|in|with|to|inside|after|before)'


def requested_names(text):
    """Literal names the user asked to ADD («…», "…", باسم X, named/called X). Filenames are ignored.

    A small deterministic acceptance criterion from the user's own words: an add request that names
    the item must leave that name visible. Not a semantic judge of quality; removals never use it.
    """
    import re
    from src.core.user_commands import command_text
    q=command_text(text)
    if not q or not re.match(_ADD,q,re.I):return []
    names=[m for pair in re.findall(r'«([^»]{2,60})»|"([^"]{2,60})"|“([^”]{2,60})”',text) for m in pair if m]
    for m in re.finditer(r'(?:باسم|بعنوان|named|called|titled)\s+(.+?)(?=\s+'+_STOP+r'\b|[،,.؛;:!؟?]|$)',text,re.I):
        words=m.group(1).strip().split()
        if 1<=len(words)<=6:names.append(' '.join(words))
    return [n for n in dict.fromkeys(n.strip() for n in names) if n and not re.search(r'\.[a-z0-9]{1,5}$',n,re.I)]


def missing_requested_names(text,files,entry):
    names=requested_names(text)
    if not names or not entry:return []
    visible=' '.join(html_contract(files).get(entry,{}).get('text',[]))
    norm=lambda v:' '.join(v.casefold().split())
    return [n for n in names if norm(n) not in norm(visible)]
