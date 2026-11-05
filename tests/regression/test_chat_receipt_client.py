"""Run shipped chat reconciliation with durable snapshots, including restored cards."""
import subprocess
from pathlib import Path


def test_cards_follow_durable_jobs_after_restore_reconnect_and_failure():
    script=r'''
const vm=require('vm'),fs=require('fs'),assert=require('assert/strict');
let state='failed',outcome=null,reads=0,events={},saved=[];
const body={textContent:'يجري توليد الملفات'},card={dataset:{projectJobId:'j_'+'a'.repeat(32)},querySelector:s=>s==='[data-job-text]'?body:null};
const id=card.dataset.projectJobId;
const context={sid:'qa',hist:[{role:'user',content:'Create CV'},{role:'assistant',content:'يجري توليد الملفات',project_job_id:id}],TOKEN:'QA',window:{addEventListener(n,f){events[n]=f;}},document:{querySelectorAll:s=>s==='[data-project-job-id]'&&!card.dataset.projectJobId?[]:[card]},
api:async(path,options)=>{if(path==='/vault/save')saved.push(JSON.parse(options.body));return {ok:true,json:async()=>{if(path==='/vault/save')return {};
if(path.startsWith('/chat/status'))return {job_id:id};reads++;return {job_id:id,state,error:state==='failed'?'OOM':null,execution:outcome};}};},
note(){},finalize(){throw Error('Unexpected destructive rerender')},sleep:async()=>{},crypto:require('crypto'),setTimeout,AbortController};
vm.runInNewContext(fs.readFileSync('web/chat.js','utf8'),context);
(async()=>{
 const chat=context.window.NeuraChat;
 await chat.restoreStatus();assert.match(body.textContent,/OOM/);assert.equal(card.dataset.jobState,'failed');assert.equal(context.hist[1].content,body.textContent);
 state='completed';outcome={outcome:'no_change',changed_files:[]};await chat.updateReceipt(id,'حُفظت المراجعة 999');
 assert.match(body.textContent,/لم يتغير/);assert.doesNotMatch(body.textContent,/999/);
 outcome={outcome:'saved',base_revision:1,result_revision:2,changed_files:['index.html'],browser:{status:'passed'}};
 await chat.restoreStatus();assert.match(body.textContent,/2/);assert.equal(card.dataset.jobState,'completed');
 state='cancelled';await events.online();assert.match(body.textContent,/لم يُحفظ/);
 context.hist=[{role:'user',content:'Unmatched old request'},{role:'assistant',content:'أُنشئ المشروع. يجري توليد الملفات'}];
 card.dataset={historyIndex:'1'};card.querySelector=()=>body;
 await chat.restoreStatus();assert.match(body.textContent,/سجل بدء قديم/);assert.equal(card.dataset.jobState,'unknown');
 assert.ok(reads>=4);assert.ok(saved.some(s=>s.messages[1].project_job_id===id));
 console.log('durable failed/no_change/saved/cancelled card reconciliation passed');
})().catch(e=>{console.error(e);process.exitCode=1});
'''
    subprocess.run(['node','-e',script],cwd=Path(__file__).resolve().parents[2],check=True,text=True)
