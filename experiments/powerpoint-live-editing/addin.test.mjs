import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const source=fs.readFileSync(new URL('./addin.js',import.meta.url),'utf8');
async function fixture(jobs,{stale=false,wrongTarget=false,failAfterMutation=false,shapeType='TextBox'}={}) {
  const names=['Title','Description','ALPHA','BETA','Preservation'];
  const texts=['Disposable PowerPoint coauthoring test','Synthetic content only. No real work records.','Agent target ALPHA: Original text.','Second editor target BETA: Browser concurrent edit.','Preservation check: Keep this bold text.'];
  if(stale)texts[2]='Agent target ALPHA: Intervening edit.';
  let mutations=0,finished;const reports=[],done=new Promise(r=>finished=r);
  const shapes=names.map((name,i)=>({
    id:String(i),name,type:shapeType,
    textFrame:{textRange:{
      load(){},
      get text(){return texts[i];},
      getSubstring(start,length){
        return {set text(value){texts[i]=texts[i].slice(0,start)+value+texts[i].slice(start+length);mutations++;}};
      }
    }}
  }));
  const context={
    presentation:{slides:{load(){},items:[{id:'slide1',shapes:{load(){},items:shapes}}]}},
    sync:async()=>{if(failAfterMutation&&mutations)throw new Error('Lost acknowledgment');}
  };
  const target={origin:'https://example.sharepoint.com',canonicalPath:'/sites/demo/Test.pptx'};
  const settings={get(){return true;},set(){},saveAsync(cb){cb({status:'ok'});},refreshAsync(cb){cb({status:'ok'});}};
  const sandbox={URL,document:{getElementById(){return{ textContent:''};}},window:{agentHandsRunToken:'synthetic'},setTimeout:cb=>setTimeout(cb,0),Office:{onReady:async()=>{},AsyncResultStatus:{Succeeded:'ok'},DocumentMode:{ReadWrite:'readWrite'},context:{host:'PowerPoint',platform:'OfficeOnline',requirements:{isSetSupported:()=>true},document:{mode:'readWrite',settings,getFilePropertiesAsync(cb){cb({status:'ok',value:{url:target.origin+(wrongTarget?'/sites/demo/Other.pptx':target.canonicalPath)}});}}}},PowerPoint:{ShapeType:{textBox:'TextBox',geometricShape:'GeometricShape'},run:async cb=>cb(context)},fetch:async(route,options)=>{
    let value;
    if(route==='./config')value={target,maxText:200000};
    else if(route==='./next'){if(jobs.length)value=jobs.shift();else{finished();throw new Error('End fixture');}}
    else {const report=JSON.parse(options.body);reports.push(report);value={ok:true};}
    return{ok:true,json:async()=>value};
  }};
  await vm.runInNewContext(source,sandbox);
  if(!wrongTarget)await done;
  return {texts,mutations,reports};
}
const edit={slideId:'slide1',shapeId:'2',name:'ALPHA',before:'Agent target ALPHA: Original text.',find:'Original text.',replacement:'Headless edit.',after:'Agent target ALPHA: Headless edit.'};
test('substring edit preserves another editor and refuses a stale repeat',async()=>{
  const r=await fixture([{id:'read',action:'read'},{id:'edit',action:'replace',edit},{id:'repeat',action:'replace',edit}]);
  assert.equal(r.mutations,1);assert.equal(r.texts[2],edit.after);assert.equal(r.texts[3],'Second editor target BETA: Browser concurrent edit.');
  assert.equal(r.reports.find(x=>x.id==='edit').status,'session_text_verified');assert.equal(r.reports.find(x=>x.id==='repeat').code,'stale_preview');
});
test('changed text and wrong presentation cannot be edited',async()=>{
  const stale=await fixture([{id:'edit',action:'replace',edit}],{stale:true});assert.equal(stale.mutations,0);assert.equal(stale.reports.at(-1).code,'stale_preview');
  const other=await fixture([{id:'edit',action:'replace',edit}],{wrongTarget:true});assert.equal(other.mutations,0);assert.equal(other.reports.length,0);
});
test('a failure after dispatch remains uncertain and is not retried',async()=>{
  const r=await fixture([{id:'edit',action:'replace',edit}],{failAfterMutation:true});assert.equal(r.mutations,1);assert.equal(r.reports.at(-1).status,'uncertain_after_dispatch');
});
test('text-bearing geometric fixture shapes work but groups remain refused',async()=>{
  const supported=await fixture([{id:'edit',action:'replace',edit}],{shapeType:'GeometricShape'});assert.equal(supported.mutations,1);
  const grouped=await fixture([{id:'edit',action:'replace',edit}],{shapeType:'Group'});assert.equal(grouped.mutations,0);assert.equal(grouped.reports.at(-1).code,'unsupported_fixture_shapes');
});
