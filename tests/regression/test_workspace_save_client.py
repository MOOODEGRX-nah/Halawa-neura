"""Run the shipped workspace state machine against a delayed save response in Node.

This is a client regression, not desktop evidence. Packaged Qt reproductions are
kept separately in qa_workspace_save_race.py.
"""
import subprocess
from pathlib import Path


def test_new_edits_and_target_survive_delayed_save_response():
    root=Path(__file__).resolve().parents[2]
    script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict');
const nodes=new Map();
function node(){return {value:'',textContent:'',children:[],open:false,dataset:{},
 classList:{add(){},remove(){},contains(){return false},toggle(){}},
 style:{setProperty(){}},setAttribute(){},addEventListener(){},append(...children){this.children.push(...children)},
 replaceChildren(...children){this.children=children},close(){this.open=false},focus(){},showModal(){this.open=true}};}
const el=id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id)};
const original='<h1>CV</h1>',sent=original+'<!-- sent -->',newest=sent+'<!-- newer -->';
const base={project_id:'p_'+'a'.repeat(32),display_name:'QA',type:'other',project_revision:1,
 source_freshness:'current',generation_status:'idle',summary:'QA',files:[{path:'index.html',sha256:'1'.repeat(64)},{path:'style.css',sha256:'9'.repeat(64)}],preview:{supported:false,reason:'QA'}};
const revision=n=>({...base,project_revision:n,files:base.files.map(f=>f.path==='index.html'?{...f,sha256:String(n).repeat(64)}:f)});
let pending=null,puts=[];
async function api(path,options){
 if(path==='/chat/context')return {ok:true,json:async()=>({})};
 if(path==='/workspace/preferences')return {ok:true,json:async()=>({swapped:false,ratio:50,last_project:null})};
 if(options.method==='PUT'){
  puts.push(JSON.parse(options.body));
  return new Promise(resolve=>{pending=()=>resolve({ok:true,json:async()=>revision(puts.length+1)});});
 }
 if(path.endsWith('/file?path=index.html'))return {ok:true,json:async()=>({path:'index.html',content:original,binary:false,sha256:'1'.repeat(64),project_revision:1})};
 if(path==='/projects/'+base.project_id)return {ok:true,json:async()=>base};
 throw Error('Unexpected request: '+path);
}
const window={addEventListener(){}};
const context={window,sid:'qa_session',document:{getElementById:el,createElement:node,createTextNode:text=>({textContent:text}),body:node()},api,
 esc:text=>text,showPage(){},confirm(){throw Error('Unexpected discard dialog')},TextEncoder,TextDecoder,setTimeout,clearTimeout,URL};
vm.runInNewContext(fs.readFileSync('web/workspace.js','utf8'),context);
(async()=>{
 const workspace=window.NeuraWorkspace;
 await workspace.openProject(base.project_id);
 el('ws-editor').value=sent;el('ws-editor').oninput();
 const first=el('ws-save').onclick();assert.equal(puts.length,1);assert.equal(workspace.dirty,true);
 el('ws-editor').value=newest;el('ws-editor').oninput();
 el('ws-editor').onkeydown({key:'s',ctrlKey:true,preventDefault(){}});
 el('ws-file-list').children.find(b=>b.textContent==='style.css').onclick();
 assert.equal(puts.length,1);assert.equal(el('ws-path').textContent,'index.html');
 pending();await first;
 assert.equal(el('ws-editor').value,newest);assert.equal(workspace.dirty,true);assert.equal(el('ws-save').disabled,false);
 const second=el('ws-save').onclick();assert.equal(puts.length,2);
 assert.equal(puts[1].content,newest);assert.equal(puts[1].expected_revision,2);assert.equal(puts[1].expected_sha256,'2'.repeat(64));
 pending();await second;assert.equal(workspace.dirty,false);assert.equal(el('ws-editor').value,newest);
})().catch(error=>{process.stderr.write(error.stack);process.exitCode=1});
'''
    result=subprocess.run(['node','-e',script],cwd=root,capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
