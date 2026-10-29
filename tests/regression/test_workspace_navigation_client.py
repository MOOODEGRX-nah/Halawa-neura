"""A late project fetch must not undo an explicit return to chat (Node DOM doubles)."""
import subprocess
from pathlib import Path


def test_return_to_chat_survives_pending_project_job_fetch():
    script=r'''
const fs=require('fs'),vm=require('vm'),assert=require('assert/strict'),nodes=new Map();
function node(){return {value:'',textContent:'',children:[],open:false,dataset:{},
 classList:{add(){},remove(){},toggle(){},contains(){return false}},style:{setProperty(){}},
 setAttribute(){},addEventListener(){},append(...x){this.children.push(...x)},
 replaceChildren(...x){this.children=x},close(){this.open=false},focus(){},showModal(){this.open=true}};}
const el=id=>{if(!nodes.has(id))nodes.set(id,node());return nodes.get(id)};
const pid='p_'+'a'.repeat(32),jid='j_'+'b'.repeat(32),views=[];
const meta={project_id:pid,display_name:'QA',project_revision:1,generation_status:'completed',
 source_freshness:'current',type:'other',summary:'QA',files:[{path:'main.py'}],
 preview:{supported:false,reason:'Python is not executed'},latest_job_id:jid};
const response=value=>({ok:true,json:async()=>value});let finishJob;
async function api(path){
 if(path==='/workspace/preferences')return response({swapped:false,ratio:50,last_project:null});
 if(path==='/projects/'+pid)return response(meta);
 if(path.endsWith('/file?path=main.py'))return response({path:'main.py',content:'pass\n',binary:false,sha256:'1'.repeat(64),project_revision:1});
 if(path==='/project-jobs/'+jid)return new Promise(resolve=>{finishJob=()=>resolve(response({job_id:jid,project_id:pid,state:'completed',last_seq:0,draft_files:{}}))});
 throw Error(path);
}
const window={addEventListener(){}},context={window,document:{getElementById:el,createElement:node,createTextNode:text=>({textContent:text}),body:node()},
 api,esc:x=>x,showPage:p=>views.push(p),confirm:()=>true,TextEncoder,TextDecoder,URL,setTimeout,clearTimeout};
vm.runInNewContext(fs.readFileSync('web/workspace.js','utf8'),context);
(async()=>{
 const opening=window.NeuraWorkspace.openProject(pid);
 for(let i=0;i<30&&!finishJob;i++)await new Promise(resolve=>setTimeout(resolve,1));
 assert.ok(finishJob,'job lookup must be pending');
 el('ws-return').onclick();assert.equal(views.at(-1),'chat');
 finishJob();await opening;
 assert.equal(views.at(-1),'chat','late workspace navigation erased explicit return to chat');
 assert.equal(el('ws-editor').value,'pass\n');
})().catch(error=>{process.stderr.write(error.stack);process.exitCode=1});
'''
    result=subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[2],capture_output=True,text=True,timeout=10)
    assert result.returncode==0,result.stderr
