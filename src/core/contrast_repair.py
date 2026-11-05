"""Small deterministic CSS repair from measured candidate colors, never fixture text.

Only solid/composited backgrounds observed by our isolated renderer are eligible.
The result is still an untrusted candidate and must pass all gates again.
"""
import re
from collections import defaultdict


def luminance(rgb):
    linear=[v/255/12.92 if v/255<=.04045 else ((v/255+.055)/1.055)**2.4 for v in rgb]
    return sum(a*b for a,b in zip(linear,(.2126,.7152,.0722)))


def contrast(foreground,background):
    a,b=luminance(foreground),luminance(background)
    return (max(a,b)+.05)/(min(a,b)+.05)


def repair_contrast(files,entry,report,user_request):
    if not report or not report.get('errors') or any('low text contrast:' not in e for e in report['errors']):return None
    if re.search(r'لون (?:النص|الخط)|text colo[u]?r|font colo[u]?r',user_request,re.I):return None
    if entry not in files or not isinstance(files[entry],str):return None
    # The iframe inherits the app's color-scheme. Never use a light-only
    # foreground correction in a dark media environment (or vice versa).
    schemes={sample.get('color_scheme') for sample in report['samples']}
    if schemes- {None}:
        if not schemes <= {'light','dark'}:return None
        scoped=[];observed=[];rule_count=0
        for scheme in sorted(schemes):
            samples=[{k:v for k,v in sample.items() if k!='color_scheme'} for sample in report['samples'] if sample.get('color_scheme')==scheme]
            failed=any(value['ratio']+.02<value['minimum'] for sample in samples for value in sample['checks'])
            if not failed:continue
            correction=repair_contrast(files,entry,{**report,'samples':samples},user_request)
            if not correction:return None
            _,receipt=correction
            rule_count+=len(receipt['rules'])
            scoped.append('@media (prefers-color-scheme: '+scheme+') {\n'+'\n'.join(receipt['rules'])+'\n}')
            observed.extend({**value,'color_scheme':scheme} for value in receipt['changes'])
        if not scoped or rule_count>30:return None
        return append_repair(files,entry,scoped,observed)
    states={sample.get('interaction_state') for sample in report['samples']}
    if states <= {'light','dark'} and states:
        scoped=[];observed=[]
        for state in sorted(states):
            samples=[{k:v for k,v in sample.items() if k!='interaction_state'} for sample in report['samples'] if sample.get('interaction_state')==state]
            if not any(v['ratio']+.02<v['minimum'] for sample in samples for v in sample['checks']):continue
            correction=repair_contrast(files,entry,{**report,'samples':samples},user_request)
            if not correction:return None
            _,receipt=correction
            scoped.extend(rule.replace('body','body[data-neura-theme="'+state+'"]',1) for rule in receipt['rules'])
            observed.extend({**value,'interaction_state':state} for value in receipt['changes'])
        if not scoped or len(scoped)>30:return None
        return append_repair(files,entry,scoped,observed)
    grouped=defaultdict(list)
    for sample in report['samples']:
        if sample.get('unknown_backgrounds'):return None
        for value in sample['checks']:
            if not value.get('selector') or not re.fullmatch(r'body(?: > [a-z][a-z0-9-]*:nth-of-type\([1-9][0-9]*\))*',value['selector']):return None
            grouped[value['selector']].append((sample,value))
    rules=[];observations=[]
    # If a requested dark theme changes text to light but leaves an opaque light
    # content surface unchanged, repair that measured surface, not its text back
    # to black (which would erase the theme). No fixture names or DOM IDs.
    surfaces={};theme=None
    initial=[s for s in report['samples'] if s['mode']=='initial']
    toggled=[s for s in report['samples'] if s['mode']=='toggled']
    if re.search(r'dark|داكن|مظلم',user_request,re.I) and not re.search(r'#[0-9a-f]{3,8}\b|لون الخلفية|background colo[u]?r',user_request,re.I) and initial and toggled:
        added=set(toggled[0]['body_classes'])-set(initial[0]['body_classes'])
        if len(added)==1 and re.fullmatch(r'[a-zA-Z_][a-zA-Z0-9_-]*',next(iter(added))):
            theme=next(iter(added));old={v['selector']:v for v in initial[0]['checks']}
            for sample in toggled:
                for value in sample['checks']:
                    prev=old.get(value['selector']);owner=value.get('background_selector')
                    if owner and re.fullmatch(r'body(?: > [a-z][a-z0-9-]*:nth-of-type\([1-9][0-9]*\))*',owner) and prev and value['ratio']<value['minimum'] and luminance(value['foreground'])>.65 and luminance(value['background'])>.65 and value['background']==prev['background'] and luminance(prev['foreground'])<.3:
                        surfaces[owner]=[23,23,23]
            for owner in surfaces:
                rules.append('body.'+theme+owner[4:]+'{background-color:#171717!important}')
                observations.append({'selector':owner,'reason':'requested dark theme has light text on unchanged opaque light surface','method':'measured theme-scoped surface correction'})
    for selector,values in grouped.items():
        values=[(sample,{**value,'background':surfaces[value['background_selector']],'ratio':contrast(value['foreground'],surfaces[value['background_selector']])}) if sample['mode']=='toggled' and value.get('background_selector') in surfaces else (sample,value) for sample,value in values]
        if all(v['ratio']+.02>=v['minimum'] for _,v in values):continue
        eligible=[rgb for rgb in ([0,0,0],[255,255,255]) if all(contrast(rgb,v['background'])>=v['minimum'] for _,v in values)]
        if eligible:
            color='#000' if eligible[0]==[0,0,0] else '#fff'
            rules.append(selector+'{color:'+color+'!important}')
        else:
            initial={tuple(s['body_classes']) for s,_ in values if s['mode']=='initial'}
            toggled={tuple(s['body_classes']) for s,_ in values if s['mode']=='toggled'}
            if len(initial)!=1 or len(toggled)!=1:return None
            added=set(next(iter(toggled)))-set(next(iter(initial)))
            if len(added)!=1:return None
            theme=next(iter(added))
            for mode,prefix in [('initial','body:not(.'+theme+')'),('toggled','body.'+theme)]:
                relevant=[v for s,v in values if s['mode']==mode]
                eligible=[rgb for rgb in ([0,0,0],[255,255,255]) if all(contrast(rgb,v['background'])>=v['minimum'] for v in relevant)]
                if not eligible:return None
                rules.append(prefix+selector[4:]+'{color:'+('#000' if eligible[0]==[0,0,0] else '#fff')+'!important}')
        observations.append({'selector':selector,'reason':'measured text/background contrast','method':'bounded black/white foreground correction'})
    if not rules or len(rules)>30:return None
    return append_repair(files,entry,rules,observations)


def append_repair(files,entry,rules,observations):
    style='\n<style data-neura-contrast="measured">\n'+'\n'.join(rules)+'\n</style>\n'
    result=dict(files);source=result[entry]
    match=re.search(r'</body\s*>',source,re.I)
    result[entry]=source[:match.start()]+style+source[match.start():] if match else source+style
    return result,{'mode':'measured_contrast_repair','changes':observations,'rules':rules,'model_called':False,'scope':'solid backgrounds at measured viewports/states/color schemes; candidate must be revalidated'}
