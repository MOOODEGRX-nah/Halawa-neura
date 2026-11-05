"""Bounded, isolated Qt static-preview checks before promotion of a candidate.

No app origin/token, native bridge, package scripts, Python or dependencies run.
The only executable generated content is static web JavaScript inside the same
CSP sandbox as the normal preview, in a separate disposable renderer process.
"""
import json
import re
import os
import signal
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from src.core.project_files import ProjectError


def check_candidate(files,preview,cancel,deadline,required=None):
    if not preview.get('supported'):
        return {'status':'not_applicable','reason':'Not a supported static website','native_code_executed':False}
    if any(isinstance(value,bytes) for value in files.values()):
        # JSON transport supports assets with an explicit base64 encoding.
        import base64
        values={k:({'base64':base64.b64encode(v).decode()} if isinstance(v,bytes) else v) for k,v in files.items()}
    else:values=files
    with tempfile.TemporaryDirectory(prefix='neura-candidate-') as folder:
        folder=Path(folder);source=folder/'candidate.json';result=folder/'result.json'
        source.write_text(json.dumps({'files':values,'preview':preview,'required':required or {}}),encoding='utf-8')
        env={**os.environ,'QT_QPA_PLATFORM':'offscreen','QTWEBENGINE_CHROMIUM_FLAGS':'--disable-gpu',
             'XDG_CACHE_HOME':str(folder/'cache'),'XDG_CONFIG_HOME':str(folder/'config')}
        env.pop('QTWEBENGINE_DISABLE_SANDBOX',None)
        with (folder/'renderer.log').open('w') as log:
            child=subprocess.Popen([sys.executable,'-B','-m','src.core.candidate_browser',str(source),str(result)],
                env=env,stdout=log,stderr=log,start_new_session=True)
            limit=min(deadline,time.monotonic()+30)
            try:
                while child.poll() is None:
                    if cancel.wait(.05) or time.monotonic()>limit:
                        raise ProjectError('انتهت مهلة فحص المعاينة أو أُلغي الطلب؛ لم يُحفظ المرشح')
                if child.returncode or not result.is_file():
                    raise ProjectError('تعذر تشغيل فحص المعاينة المعزول؛ لم يُحفظ المرشح')
                report=json.loads(result.read_text())
                if report.get('status')!='passed':
                    error=ProjectError('فشل فحص المعاينة: '+ '; '.join(report.get('errors',['unknown']))[:1500]);error.browser_report=report;raise error
                return report
            finally:
                if child.poll() is None:os.killpg(child.pid,signal.SIGKILL)
                child.wait()


INSPECT=r'''(()=>{
 const selector=e=>{let parts=[];while(e&&e.tagName!=='BODY'){const tag=e.tagName.toLowerCase();if(!/^[a-z][a-z0-9-]*$/.test(tag))return null;const siblings=Array.from(e.parentElement?.children||[]).filter(x=>x.tagName===e.tagName);parts.unshift(tag+':nth-of-type('+(siblings.indexOf(e)+1)+')');e=e.parentElement;}return e?'body'+(parts.length?' > '+parts.join(' > '):''):null;};
 const visible=e=>{const r=e.getBoundingClientRect(),s=getComputedStyle(e);return r.width>0&&r.height>0&&s.visibility!=='hidden'&&s.display!=='none';};
 const rgba=s=>(s.match(/[\d.]+/g)||[]).map(Number);
 const rgb=s=>rgba(s).slice(0,3);
 const lum=a=>a.map(x=>{x/=255;return x<=.04045?x/12.92:((x+.055)/1.055)**2.4}).reduce((s,x,i)=>s+x*[.2126,.7152,.0722][i],0);
 let checks=[],unknown=0;
 for(const e of Array.from(document.querySelectorAll('body *')).filter(visible).slice(0,400)){
  if(!Array.from(e.childNodes).some(n=>n.nodeType===3&&n.textContent.trim()))continue;
  const style=getComputedStyle(e);let p=e,layers=[],complex=false,backgroundSelector=null;
  while(p){const s=getComputedStyle(p);if(s.backgroundImage!=='none'||Number(s.opacity)<1||s.filter!=='none'||s.mixBlendMode!=='normal'){complex=true;break;}
   const color=rgba(s.backgroundColor);if(color.length>=3){layers.push(color);if(color.length===3||color[3]===1){backgroundSelector=selector(p);break;}}p=p.parentElement;}
  let bg=[255,255,255];for(const c of layers.reverse()){const a=c.length===4?c[3]:1;bg=bg.map((v,i)=>c[i]*a+v*(1-a));}
  const foreground=rgba(style.color),a=foreground.length===4?foreground[3]:1,fg=foreground.slice(0,3).map((v,i)=>v*a+bg[i]*(1-a));
  if(complex){unknown++;continue;}
  if(fg.length===3&&bg.length===3){const l1=lum(fg),l2=lum(bg),ratio=(Math.max(l1,l2)+.05)/(Math.min(l1,l2)+.05);
   const large=parseFloat(style.fontSize)>=24||(parseFloat(style.fontSize)>=18.66&&Number(style.fontWeight)>=700);
   checks.push({selector:selector(e),text:e.textContent.trim().slice(0,80),ratio,foreground:fg,background:bg,background_selector:backgroundSelector,minimum:large?3:4.5});}
 }
 const dark=Array.from(document.querySelectorAll('button,[role=button],input[type=checkbox]')).find(e=>visible(e)&&/dark|theme|داكن|مظلم/i.test(e.textContent+' '+e.id+' '+(e.getAttribute('aria-label')||'')));
 const controls=Array.from(document.querySelectorAll('a,button,input,select,textarea')).filter(visible).map(e=>({tag:e.tagName.toLowerCase(),label:e.textContent.trim().replace(/\s+/g,' '),id:e.getAttribute('id'),href:e.getAttribute('href'),name:e.getAttribute('name'),type:e.getAttribute('type')}));
 return JSON.stringify({body_classes:Array.from(document.body.classList).filter(x=>/^[a-zA-Z_][a-zA-Z0-9_-]*$/.test(x)),controls,visible_text:document.body.innerText.replace(/\s+/g,' '),overflow:document.documentElement.scrollWidth>innerWidth+2,checks,unknown_backgrounds:unknown,dark_available:!!dark});
})()'''
TOGGLE=r'''(()=>{const e=Array.from(document.querySelectorAll('button,[role=button],input[type=checkbox]')).find(e=>/dark|theme|داكن|مظلم/i.test(e.textContent+' '+e.id+' '+(e.getAttribute('aria-label')||'')));if(e){e.click();return true;}return false;})()'''


def main(source,destination):
    import base64
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QUrl,QCoreApplication,QEvent
    from PySide6.QtWebEngineCore import QWebEnginePage,QWebEngineProfile,QWebEngineUrlRequestInterceptor
    from PySide6.QtWebEngineWidgets import QWebEngineView
    from src.core.project_preview import PreviewServer
    payload=json.loads(Path(source).read_text());preview=payload['preview']
    files={k:(base64.b64decode(v['base64']) if isinstance(v,dict) else v) for k,v in payload['files'].items()}
    class Snapshot:
        def preview_snapshot(self,*_):
            return {'entry_point':preview['entry_point'],'preview':preview},{p:files[p] for p in preview['assets']}
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    import threading
    server=PreviewServer(Snapshot());cap={}
    class Parent(BaseHTTPRequestHandler):
        def log_message(self,*_):pass
        def do_GET(self):
            if self.path!='/':self.send_error(404);return
            body=('<!doctype html><style>html,body{margin:0;width:100%;height:100%}iframe{border:0;width:100%;height:100%}</style><iframe sandbox="allow-scripts" src="'+cap['url']+'"></iframe>').encode()
            self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)))
            self.send_header('Content-Security-Policy',"default-src 'none'; style-src 'unsafe-inline'; frame-src "+cap['origin']);self.end_headers();self.wfile.write(body)
    parent=ThreadingHTTPServer(('127.0.0.1',0),Parent);parent.daemon_threads=True
    parent_origin='http://127.0.0.1:'+str(parent.server_port)
    cap=server.issue('candidate',parent_origin,0)
    threading.Thread(target=parent.serve_forever,daemon=True).start()
    prefix=cap['url'].rsplit('/',1)[0]+'/'
    app=QApplication(['neura-candidate']);profile=QWebEngineProfile()
    class Requests(QWebEngineUrlRequestInterceptor):
        def interceptRequest(self,info):
            url=info.requestUrl().toString()
            if not (url.startswith(prefix) or url==parent_origin+'/' or url.startswith('data:')):info.block(True)
    class Page(QWebEnginePage):
        def acceptNavigationRequest(self,url,kind,main):return url.toString()==parent_origin+'/' if main else url.toString().startswith(prefix)
        def createWindow(self,*_):return None
    interceptor=Requests();profile.setUrlRequestInterceptor(interceptor)
    page=Page(profile);page.permissionRequested.connect(lambda permission:permission.deny());view=QWebEngineView();view.setPage(page);view.resize(1280,800);view.show()
    def pump(duration=.2):
        end=time.monotonic()+duration
        while time.monotonic()<end:app.processEvents();time.sleep(.005)
    def js(code):
        out=[];frames=[f for f in page.mainFrame().children() if f.url().toString().startswith(prefix)]
        if not frames:raise ValueError('No isolated preview frame')
        frames[0].runJavaScript(code,1,lambda value:out.append(value));end=time.monotonic()+5
        while not out and time.monotonic()<end:pump(.01)
        if not out:raise TimeoutError('Renderer inspection timed out')
        return out[0]
    report={'status':'failed','errors':[],'samples':[],'scope':'480/1280px overflow and sampled computed text contrast; optional dark control click',
            'native_code_executed':False,'javascript_executed':'CSP sandbox, separate Qt process','limitations':['Not full behavioral equivalence','Gradients/complex compositing require visual review','No authentication/payment/service verification']}
    try:
        loaded=[];page.loadFinished.connect(lambda ok:loaded.append(ok));page.load(QUrl(parent_origin+'/'))
        end=time.monotonic()+10
        while not loaded and time.monotonic()<end:pump(.01)
        if not loaded or not loaded[0]:raise ValueError('Candidate page did not load')
        for width in (1280,480):
            view.resize(width,800);pump(.25)
            sample=json.loads(js(INSPECT));sample.update(width=width,mode='initial');report['samples'].append(sample)
        if report['samples'][0]['dark_available']:
            js(TOGGLE);pump(.4)
            for width in (1280,480):
                view.resize(width,800);pump(.2);sample=json.loads(js(INSPECT));sample.update(width=width,mode='toggled');report['samples'].append(sample)
        if len(report['samples'])==4:
            report['theme_changed']=any([(x['foreground'],x['background']) for x in report['samples'][i]['checks']]!=[(x['foreground'],x['background']) for x in report['samples'][i+2]['checks']] for i in (0,1))
            if not report['theme_changed']:report['errors'].append('Theme control did not change observed appearance')
        required=payload.get('required') or {}
        report['required_features']=[name for name in ('theme','login') if required.get(name)]
        if required.get('theme'):
            if not report['samples'][0]['dark_available']:report['errors'].append('Required theme control did not initialize; preview persistent storage is unavailable')
            else:
                initial={v['selector']:v['background'] for s in report['samples'] if s['mode']=='initial' and s['width']==1280 for v in s['checks']}
                toggled={v['selector']:v['background'] for s in report['samples'] if s['mode']=='toggled' and s['width']==1280 for v in s['checks']}
                if not any(initial[p]!=toggled[p] for p in initial.keys()&toggled.keys()):report['errors'].append('Required theme did not change observed content surface backgrounds')
        if required.get('login') and any(not any(re.search(r'login|sign.?in|دخول',c['label'],re.I) for c in s['controls']) for s in report['samples']):report['errors'].append('Required Login placeholder is not visible')
        for sample in report['samples']:
            if sample['unknown_backgrounds']:report['errors'].append('Complex backgrounds require rendered visual review; readability not verified')
            for control in required.get('controls',[]):
                if not any(all(item.get(k)==v for k,v in control.items()) for item in sample['controls']):report['errors'].append('Required visible control missing: '+str(control))
            for text in required.get('text',[]):
                # CSS text-transform may change rendered casing without changing source.
                # Source/controls remain checked exactly by the preservation contract.
                if len(text)>1 and text.casefold() not in sample['visible_text'].casefold():report['errors'].append('Required visible content missing: '+text[:80])
            if sample['overflow']:report['errors'].append(str(sample['width'])+'px horizontal overflow')
            failures=[x for x in sample['checks'] if x['ratio']+.02<x['minimum']]
            if failures:report['errors'].append(sample['mode']+' low text contrast: '+json.dumps(failures[:3],ensure_ascii=False))
        report['status']='failed' if report['errors'] else 'passed'
    except Exception as exc:report['errors'].append(str(exc))
    finally:
        Path(destination).write_text(json.dumps(report,ensure_ascii=False,indent=2))
        view.close();page.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);profile.deleteLater();QCoreApplication.sendPostedEvents(None,QEvent.DeferredDelete);server.stop();parent.shutdown();parent.server_close()


if __name__=='__main__':main(*sys.argv[1:])
