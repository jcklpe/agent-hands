import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import {tailEdit} from '../scripts/tail-core.mjs';
const script=fs.readFileSync(new URL('../addin/app.js',import.meta.url),'utf8');
async function run(before,edit){
 let text=[...before],writes=0,reported;
 const paragraphs={load(){},get items(){return text.map((value,index)=>({text:value,getRange(kind){return {insertText(replacement){assert.equal(kind,'Content');writes++;text[index]=replacement;},expandTo(){return {insertHtml(html){writes++;const label=html.match(/>([^<>]+)<\/a>/)[1];text=text.slice(0,index).concat(label);}};}};}}));}};
 const context={sync:async()=>{},document:{save(){},body:{paragraphs,getRange(){return {};}}}};
 let served=false;
 const target={origin:'https://example.test',pathname:'/Note.docx'};
 const job={id:'one',action:'replace-tail',edit};
 const sandbox={URL,console,document:{getElementById:()=>({textContent:''})},window:{agentHandsRunToken:'test'},setTimeout:fn=>{queueMicrotask(fn);return 0;},Word:{run:async fn=>fn(context),RangeLocation:{start:'Start',end:'End',content:'Content'},InsertLocation:{replace:'Replace'}},Office:{context:{host:'Word',platform:'OfficeOnline',requirements:{isSetSupported:()=>true},document:{mode:'ReadWrite',getFilePropertiesAsync:fn=>fn({status:'ok',value:{url:'https://example.test/Note.docx'}}),settings:{get:()=>true}}},DocumentMode:{ReadWrite:'ReadWrite'},AsyncResultStatus:{Succeeded:'ok'},onReady:async()=>{}},fetch:async(url,options)=>{
  const route=url.split('/').at(-1);let result;
  if(route==='config')result={target,maxText:200000};
  else if(route==='next'){if(served)throw Error('done');served=true;result=job;}
  else if(route==='report'){const body=JSON.parse(options.body);if(body.id!=='ready')reported=body;result={ok:true};}
  return {ok:true,json:async()=>result};
 }};
 await vm.runInNewContext(script,sandbox);
 assert.ok(reported);return {text,writes,reported};
}
test('actual add-in operation preserves the prefix and returns saved tail result',async()=>{
 const before=['Title','The appendix follows.','','Draft appendix','Question one'];
 const edit=tailEdit(before,{anchor:'Draft appendix',label:'Separate draft',url:'https://example.test/draft',replacements:[{before:'The appendix follows.',after:'See the separate draft.'}]});
 const result=await run(before,edit);
 assert.equal(result.reported.status,'save_returned');assert.deepEqual(result.text,edit.after);assert.equal(result.writes,2);
});
test('actual add-in refuses changed coauthor text before any mutation',async()=>{
 const original=['Title','Draft appendix','Question one'];
 const edit=tailEdit(original,{anchor:'Draft appendix',label:'Separate draft',url:'https://example.test/draft',replacements:[]});
 const result=await run(['Title','Human notes','Draft appendix','Question one'],edit);
 assert.equal(result.reported.status,'refused_before_mutation');assert.equal(result.writes,0);assert.ok(result.text.includes('Human notes'));
});
