"""Owned QA metadata probe; no model generation, shell, admin or production data.

Use with an existing run discovery file. Optional --pause-for-ui exposes the
stale state until the run's continue-metadata file appears (180s deadline).
"""
import argparse,json,os,sys,threading,time,urllib.error,urllib.parse
from argparse import Namespace
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from verify_neura import Run
from verification.live import Client


def metadata(run,client,pause=False):
    projects=client.call('/projects')['projects']
    candidate=next((p for p in projects if {'index.html','style.css','script.js','logo.svg'}<={x['path'] for x in p['files']}),None)
    if not candidate:raise ValueError('Owned four-file static QA site required; no unrelated project is selected')
    pid=candidate['project_id'];root=run.profile/'data/workspace'
    metadata_path=next(p for p in root.glob('*/.neura/project.json') if json.loads(p.read_text())['project_id']==pid)
    directory=metadata_path.parent.parent.resolve()
    if not directory.is_relative_to(root.resolve()):raise ValueError('QA confinement failed')
    # A timed-out UI checkpoint deliberately leaves its owned fixture stale.
    # Reconcile that reviewed test-only source before starting a new attempt.
    current=client.call('/projects/'+pid)
    if current['source_freshness']=='stale':
        client.call('/projects/'+pid+'/reindex',{'expected_revision':current['project_revision']})
    before=client.call('/stats')['totals']['requests'];source=client.call('/projects/'+pid+'/file?path=index.html')
    meta=client.call('/projects/'+pid+'/file',{'path':'index.html','content':source['content']+'\n<!-- QA-A -->\n',
        'expected_revision':source['project_revision'],'expected_sha256':source['sha256']},'PUT')
    path=directory/'index.html';stamp=path.stat();raw=path.read_bytes();assert b'<!-- QA-A -->' in raw
    path.write_bytes(raw.replace(b'<!-- QA-A -->',b'<!-- QA-B -->'));os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    stale=client.call('/projects/'+pid);question=client.call('/projects/'+pid+'/question',{'question':'ما هي لغات المشروع؟'})
    evidence={'instance_id':client.info['instance_id'],'project_id':pid,'source_files_directory':str(directory),
        'same_stat':{'size_before':stamp.st_size,'size_after':path.stat().st_size,'mtime_before':stamp.st_mtime_ns,'mtime_after':path.stat().st_mtime_ns,
            'metadata':stale,'answer':question}}
    target=run.out/'artifacts/metadata-probe.json';target.write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    if pause:
        ready=run.out/'artifacts/metadata-stale-ready.json';ready.write_text(json.dumps({'project_id':pid}))
        end=time.monotonic()+180
        while not (run.out/'continue-metadata').exists() and time.monotonic()<end:threading.Event().wait(.1)
        if not (run.out/'continue-metadata').exists():raise TimeoutError('Metadata UI checkpoint deadline; stale evidence retained')
    rebuilt=client.call('/projects/'+pid+'/reindex',{'expected_revision':meta['project_revision']})
    note=directory/('qa-note-'+run.result['run_id']+'.md');assert not note.exists();note.write_text('# Owned QA note\n')
    added=client.call('/projects/'+pid);with_note=client.call('/projects/'+pid+'/reindex',{'expected_revision':rebuilt['project_revision']})
    note.unlink();deleted=client.call('/projects/'+pid);without_note=client.call('/projects/'+pid+'/reindex',{'expected_revision':with_note['project_revision']})
    logo=directory/'logo.svg';moved=directory/'moved-qa-logo.svg';assert logo.is_file() and not moved.exists()
    try:
        logo.rename(moved);renamed=client.call('/projects/'+pid)
        try:client.call('/projects/'+pid+'/reindex',{'expected_revision':without_note['project_revision']});rejected=False
        except urllib.error.HTTPError as exc:rejected=exc.code in (400,409,422)
    finally:
        if moved.exists():moved.rename(logo)
    final=client.call('/projects/'+pid);context=client.call('/projects/'+pid+'/context',{'paths':['style.css']})
    direct=client.call('/projects/'+pid+'/file?path=style.css');answer=client.call('/projects/'+pid+'/question',{'question':'ما هي لغات المشروع؟'})
    after=client.call('/stats')['totals']['requests']
    evidence.update(rebuilt=rebuilt,added_stale=added['source_freshness'],with_note_languages=with_note['languages'],
        deleted_stale=deleted['source_freshness'],without_note_languages=without_note['languages'],renamed_stale=renamed['source_freshness'],missing_reference_rejected=rejected,
        final=final,answer=answer,actual_source_read=context['files'][0]['content']==direct['content'],model_requests_before=before,model_requests_after=after,
        freshness_boundary='Every metadata read and write boundary hashes bounded source files, including unchanged stats; no watcher. These disk reads are not model context injection.')
    passed=stale['source_freshness']=='stale' and question['stale'] and added['source_freshness']=='stale' and deleted['source_freshness']=='stale' and 'Markdown' in with_note['languages'] and 'Markdown' not in without_note['languages'] and rejected and final['source_freshness']=='current' and before==after and evidence['actual_source_read']
    evidence['passed']=passed;target.write_text(json.dumps(evidence,ensure_ascii=False,indent=2));print(json.dumps({'passed':passed,'project_id':pid,'revision':final['project_revision'],'model_requests_before':before,'model_requests_after':after},indent=2))
    # The main runner imports this probe only after concurrent UI checkpoints,
    # preserving one writer for results.json.
    return int(not passed)


def browser_security(run,client):
    """Serve an owned beacon, never contact an unrelated service or launch tools."""
    from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
    import urllib.request
    sys.path[:0]=[str(run.target),str(run.vendor)]
    from src.core.project_store import ProjectStore
    hits=[]
    class Beacon(BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path);self.send_response(200);self.end_headers();self.wfile.write(b'owned QA beacon')
        do_POST=do_GET
        def log_message(self,*args):pass
    beacon=ThreadingHTTPServer(('127.0.0.1',0),Beacon);beacon.daemon_threads=True
    worker=threading.Thread(target=beacon.serve_forever,daemon=True);worker.start()
    before={'history':client.call('/skills/history'),'grants':client.call('/skills/grants'),'projects':client.call('/projects')['projects']}
    store=ProjectStore(run.profile/'data')
    pid=store.create('فحص عزل المتصفح N057','Owned adversarial fixture; NOT model-generated','static_web')['project_id']
    payload="""const checks={};
try{checks.parent=parent.document.title}catch(e){checks.parent='blocked'};
try{localStorage.setItem('qa','x');checks.storage='allowed'}catch(e){checks.storage='blocked'};
checks.bridge=typeof qt==='undefined'&&typeof QWebChannel==='undefined';
try{parent.NeuraSkills.perform('open_website',{destination:'https://example.com/'});checks.tool='allowed'}catch(e){checks.tool='blocked'};
const targets=[['authorize',APP+'/skills/authorize'],['execute',APP+'/skills/execute'],['vault',APP+'/vault/sessions'],['projects',APP+'/projects'],['unrelated',BEACON+'/beacon'],['metadata','.neura/project.json'],['private','private.txt']];
Promise.all(targets.map(async([name,url])=>{try{await fetch(url,{method:['authorize','execute'].includes(name)?'POST':'GET',headers:{'Content-Type':'application/json'},...(['authorize','execute'].includes(name)?{body:JSON.stringify({name:'open_website',args:{destination:'https://example.com/'}})}:{})});checks[name]='allowed'}catch(e){checks[name]='blocked'}})).then(()=>document.querySelector('#checks').textContent=JSON.stringify(checks));""".replace('APP',json.dumps(client.info['url'])).replace('BEACON',json.dumps('http://127.0.0.1:'+str(beacon.server_port)))
    meta=store.commit(pid,{'index.html':'<html lang="ar" dir="rtl"><h1>فحص عزل المتصفح N057</h1><p>بيانات QA ومحاولات ممنوعة فقط</p><pre id="checks">pending</pre><script src="checks.js"></script></html>',
        'checks.js':payload,'private.txt':'QA-only private text, excluded from preview'},0)
    store.close()
    preview=client.call('/projects/'+pid+'/preview',{'expected_revision':meta['project_revision']})
    info={'project_id':pid,'instance_id':client.info['instance_id'],'model':'controlled fixture, no inference',
        'preview':preview,'before':before,'unrelated_port':beacon.server_port}
    target=run.out/'artifacts/browser-isolation.json';target.write_text(json.dumps(info,ensure_ascii=False,indent=2))
    print(json.dumps({'project_id':pid,'ready':True}),flush=True)
    try:
        end=time.monotonic()+1200
        while not (run.out/'finish-browser-security').exists() and time.monotonic()<end:threading.Event().wait(.1)
        after={'history':client.call('/skills/history'),'grants':client.call('/skills/grants')}
        info.update(after=after,beacon_hits=hits,zero_privileged_side_effects=before['history']==after['history'] and before['grants']==after['grants'] and not hits,
            ui_completed=(run.out/'finish-browser-security').exists(),scope='Browser assertions and screenshots recorded separately; zero-effects alone is not a complete isolation pass.')
        target.write_text(json.dumps(info,ensure_ascii=False,indent=2));print(json.dumps({'zero_privileged_side_effects':info['zero_privileged_side_effects'],'ui_completed':info['ui_completed']}),flush=True)
        return int(not(info['zero_privileged_side_effects'] and info['ui_completed']))
    finally:
        beacon.shutdown();beacon.server_close();worker.join(timeout=3)


def api_scope(run,client):
    """Current HTTP negative cases and owned session CRUD; no model or mail."""
    import urllib.request
    evidence={'instance_id':client.info['instance_id'],'health':client.verify(),'cases':[]}
    def check(name,fn,expected=200):
        try:body=fn();status=200
        except urllib.error.HTTPError as exc:
            status=exc.code;raw_body=exc.read(8192)
            try:body=json.loads(raw_body)
            except ValueError:body={'text':raw_body.decode('utf-8','replace')}
        evidence['cases'].append({'name':name,'expected_http':expected,'actual_http':status,'response':body,'passed':status==expected})
        return body
    check('draft_only_no_send',lambda:client.call('/tool/call',{'tool':'draft_email','args':{'to_address':'qa@example.invalid','subject':'QA draft only','body':'Owned test. No mail sent.'}}))
    check('harvest_not_implemented',lambda:client.call('/vault/harvest',{}),501)
    check('tts_unavailable',lambda:client.call('/tts',{'text':'مرحبا','lang':'ar'}),501)
    check('stt_unavailable',lambda:client.call('/stt',{}),501)
    check('unknown_tool',lambda:client.call('/tool/call',{'tool':'qa_missing','args':{}}),501)
    check('no_pending_execution',lambda:client.call('/tool/pending'))
    check('no_reminder_api',lambda:client.call('/reminders'),404)
    def raw(path,headers):
        with client.opener.open(urllib.request.Request(client.info['url']+path,headers=headers),timeout=10) as response:return json.loads(response.read(8192))
    check('private_missing_auth',lambda:raw('/projects',{}),403)
    check('host_rejected',lambda:raw('/health',{'Host':'evil.invalid'}),400)
    check('foreign_origin_rejected',lambda:raw('/projects',{'X-Neura-Token':client.token,'Origin':'https://evil.invalid'}),403)
    history=client.call('/skills/history');before=client.call('/stats')['totals']['requests']
    for text in ['لا تفتح يوتيوب','"افتح ديسكورد"','```افتح Brave```']:
        check('injection_no_dispatch_'+text,lambda text=text:client.call('/chat/dispatch',{'text':text,'session_id':'qa_negative','request_id':'r_'+str(int(time.time()*1000))+'_'+__import__('uuid').uuid4().hex}))
    evidence['no_injection_side_effects']=history==client.call('/skills/history') and before==client.call('/stats')['totals']['requests']
    name='qa_crud_'+run.result['run_id'];other=name+'_other'
    initial=[{'role':'user','content':'Synthetic QA session only'}]
    check('session_save',lambda:client.call('/vault/save',{'session':name,'messages':initial}))
    check('session_other_save',lambda:client.call('/vault/save',{'session':other,'messages':[{'role':'user','content':'other'}]}))
    check('session_update',lambda:client.call('/vault/save',{'session':name,'messages':initial+[{'role':'assistant','content':'QA update'}]}))
    value=check('session_read',lambda:client.call('/vault/sessions/'+name))
    sys.path[:0]=[str(run.target),str(run.vendor)]
    from src.core.vault import ConversationVault
    evidence['new_storage_instance_same']=ConversationVault(run.profile/'data').get(name)==value
    evidence['other_session_separate']=client.call('/vault/sessions/'+other)['messages']==[{'role':'user','content':'other'}]
    check('delete_owned_session',lambda:client.call('/vault/sessions/'+name,method='DELETE'))
    check('deleted_session_missing',lambda:client.call('/vault/sessions/'+name),404)
    check('delete_other_owned_session',lambda:client.call('/vault/sessions/'+other,method='DELETE'))
    evidence['stats']=client.call('/stats');evidence['history']=client.call('/skills/history')
    evidence['passed']=all(x['passed'] for x in evidence['cases']) and evidence['new_storage_instance_same'] and evidence['other_session_separate'] and evidence['no_injection_side_effects']
    (run.out/'artifacts/packaged-extra-api.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2))
    print(json.dumps({'cases':len(evidence['cases']),'passed':evidence['passed'],'failures':[x['name'] for x in evidence['cases'] if not x['passed']]}))
    return int(not evidence['passed'])


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',required=True);p.add_argument('--target-root',required=True);p.add_argument('--pause-for-ui',action='store_true');p.add_argument('--probe',choices=['metadata','browser-security','api'],default='metadata');a=p.parse_args()
    run=Run(Namespace(target_root=a.target_root,vendor_dir=None,resume=a.run,profile_root=None,output_root=None))
    client=Client(run,json.loads((run.out/'artifacts/backend.json').read_text()))
    raise SystemExit(metadata(run,client,a.pause_for_ui) if a.probe=='metadata' else browser_security(run,client) if a.probe=='browser-security' else api_scope(run,client))
