"""Typed, server-compiled web interactions authorized by validated user intent.

This is a supported theme operation, not an arbitrary script or cloud skill.
Its compiled source is still a private candidate and must pass every gate.
"""
import json
import re
from src.core.project_files import ProjectError
from src.core.project_store import digest

THEME_ID='neura-theme-toggle'
THEME_ATTRIBUTE='data-neura-theme'
SURFACES='body,body div,body header,body nav,body main,body section,body article,body aside,body footer'


def theme_contract():
    return {'version':1,'feature':'theme','implementation':'server_compiled_required_interaction',
        'control':{'selector':'#'+THEME_ID,'event':'click','label':'تبديل الوضع الداكن / Theme'},
        'state':{'selector':'body','attribute':THEME_ATTRIBUTE,'values':['light','dark'],'initial':'light'},
        'surfaces':SURFACES.split(','),'css_states':['body['+THEME_ATTRIBUTE+'="'+mode+'"]' for mode in ('light','dark')],
        'palette':{'light':{'background':'#f5f5f5','foreground':'#171717'},'dark':{'background':'#171717','foreground':'#eeeeee'}},
        'storage':'none'}


def compile_theme(files,path):
    """Exact unique HTML boundaries only. No repair of unmatched HTML anchors."""
    if path not in files or not path.endswith(('.html','.htm')):raise ProjectError('تفاعل theme يحتاج ملف HTML محددًا')
    source=files[path]
    if not isinstance(source,str):raise ProjectError('ملف HTML غير نصي')
    if re.search(r'\b'+THEME_ID+r'\b|\b'+THEME_ATTRIBUTE+r'\b',source):raise ProjectError('معرفات عقد التفاعل موجودة مسبقًا؛ لا يُخمن ربط بديل')
    if source.count('</head>')!=1 or source.count('</body>')!=1:raise ProjectError('حدود تفاعل HTML مفقودة أو ملتبسة؛ لم يُحفظ المرشح')
    contract=theme_contract();rules=[]
    for mode,palette in contract['palette'].items():
        state='body['+THEME_ATTRIBUTE+'="'+mode+'"]'
        # Qualify every affected surface with the same manual state; no OS media
        # condition can disconnect the control from its actual rendered surface.
        surfaces=','.join(state+selector[4:] for selector in contract['surfaces'])
        rules.append(surfaces+'{background-color:'+palette['background']+'!important;color:'+palette['foreground']+'!important}')
        rules.append(state+' *{color:'+palette['foreground']+'!important}')
        rules.append(state+' button,'+state+' input,'+state+' select,'+state+' textarea{background-color:'+palette['background']+'!important}')
    rules.append('#'+THEME_ID+'{display:block;position:static;max-width:100%;margin:1rem;padding:.6rem 1rem;border:1px solid currentColor;border-radius:.4rem;cursor:pointer}')
    style='<style data-neura-interaction="theme">\n'+'\n'.join(rules)+'\n</style>\n'
    markup='<button id="'+THEME_ID+'" type="button" aria-pressed="false">'+contract['control']['label']+'</button>\n'
    script='<script data-neura-interaction="theme">\n(()=>{const root=document.body;const button=document.getElementById('+json.dumps(THEME_ID)+');const state='+json.dumps(THEME_ATTRIBUTE)+';root.setAttribute(state,"light");button.addEventListener("click",()=>{const dark=root.getAttribute(state)!=="dark";root.setAttribute(state,dark?"dark":"light");button.setAttribute("aria-pressed",String(dark));});})();\n</script>\n'
    from src.core.bounded_edits import apply_exact
    candidate=apply_exact(files,path,[{'before':'</head>','after':style+'</head>'},{'before':'</body>','after':markup+script+'</body>'}],source)
    return candidate,{**contract,'path':path,'base_sha256':digest(source),'compiled_sha256':digest(candidate[path])}


def present_contract(files,entry):
    source=files.get(entry,'')
    if isinstance(source,str) and 'data-neura-interaction="theme"' in source:return theme_contract()
    return None
