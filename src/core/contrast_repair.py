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
    grouped=defaultdict(list)
    for sample in report['samples']:
        if sample.get('unknown_backgrounds'):return None
        for value in sample['checks']:
            if not value.get('selector') or not re.fullmatch(r'body(?: > [a-z][a-z0-9-]*:nth-of-type\([1-9][0-9]*\))*',value['selector']):return None
            grouped[value['selector']].append((sample,value))
    rules=[];observations=[]
    for selector,values in grouped.items():
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
    style='\n<style data-neura-contrast="measured">\n'+'\n'.join(rules)+'\n</style>\n'
    result=dict(files);source=result[entry]
    match=re.search(r'</body\s*>',source,re.I)
    result[entry]=source[:match.start()]+style+source[match.start():] if match else source+style
    return result,{'mode':'measured_contrast_repair','changes':observations,'model_called':False,'scope':'solid backgrounds at measured viewports/states; candidate must be revalidated'}
