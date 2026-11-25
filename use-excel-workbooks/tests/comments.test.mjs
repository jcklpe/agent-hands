import test from 'node:test';
import assert from 'node:assert/strict';
import {createCommentsAdapter,validateComments} from '../officejs/comments.mjs';
const input=[{sheet:'Inventory',cell:'J6',expectedValue:'existing',content:'Historical evidence'}];
function host({value='existing',occupied=false,readOnly=false,fail=false}={}){
 let writes=0;
 const collection={items:occupied?[{getLocation:()=>({address:'Inventory!J6',load(){}})}]:[],load(){},add(range,content){writes++;return {content,load(){}};}};
 const context={workbook:{comments:collection,worksheets:{getItem:()=>({getRange:()=>({values:[[value]],load(){}})})}},async sync(){if(fail&&writes)throw Error('connection lost');}};
 return {run:createCommentsAdapter({ContentType:{plain:'Plain'},run:fn=>fn(context)},{context:{document:{mode:readOnly?'readOnly':'readWrite'},requirements:{isSetSupported:()=>true}}},async()=>{}),writes:()=>writes};
}
test('comment import preserves cells and checks content',async()=>{const h=host();assert.equal((await h.run('comments-add',{items:input})).status,'comments_session_verified');assert.equal(h.writes(),1);});
for(const config of [{value:'changed'},{occupied:true},{readOnly:true}])test('refuses before mutation '+JSON.stringify(config),async()=>{const h=host(config);assert.equal((await h.run('comments-add',{items:input})).status,'refused_before_mutation');assert.equal(h.writes(),0);});
test('read does not write and partial dispatch remains uncertain',async()=>{const h=host({fail:true});assert.equal((await h.run('comments-read',{items:input})).status,'comments_ready');assert.equal(h.writes(),0);assert.equal((await h.run('comments-add',{items:input})).status,'uncertain_after_dispatch');assert.equal(h.writes(),1);});
test('bounds and duplicate targets are enforced',()=>{assert.throws(()=>validateComments([...input,...input]));assert.throws(()=>validateComments([{...input[0],content:'x'.repeat(30001)}]));});
