import test from 'node:test';
import assert from 'node:assert/strict';
import '../addin/paragraphs.js';
import {verifyParagraphs} from '../scripts/paragraph-core.mjs';
const {validate,run}=globalThis.AgentHandsParagraphs;
const spec={paragraphs:[{index:0,before:'Original answer',after:'Updated answer'}],links:[],append:[]};
test('bounded paragraph input rejects duplicate targets, executable fields and unsafe links',()=>{for(const s of [{...spec,script:'execute'},{...spec,paragraphs:[...spec.paragraphs,...spec.paragraphs]},{...spec,links:[{before:'https://example.test/a',after:'https://different.test/a'}]}])assert.throws(()=>validate(s));});
for(const cause of ['tracking','stale','revision'])test('paragraph refuses '+cause+' before mutation',async()=>{let saved=false;const p={text:cause==='stale'?'Different answer':'Original answer',getComments:()=>({items:[],load(){}}),getRange:()=>({getTrackedChanges:()=>({items:cause==='revision'?[{}]:[],load(){}})})};const c={document:{body:{paragraphs:{items:[p],load(){}}},changeTrackingMode:cause==='tracking'?'TrackAll':'Off',load(){},save(){saved=true;}},async sync(){}};const result=await run(c,{action:'paragraphs-apply',before:['Original answer'],spec},{},async()=>{});assert.equal(result.status,'refused_before_mutation');assert.equal(saved,false);});
test('manual-break range is expanded and verified before replacement',async()=>{let changed;const before='Keep first\vsecond tail',after='Keep corrected tail',span={text:'first\vsecon',load(){},insertText:t=>{changed=t;}};const p={text:before,font:{},getComments:()=>({items:[{id:'1'}],load(){}}),getRange:()=>({getTrackedChanges:()=>({items:[],load(){}}),search:term=>({items:[{text:term,expandTo:()=>span}],load(){}})})};const c={document:{body:{paragraphs:{items:[p],load(){}}},changeTrackingMode:'Off',load(){},save(){}},async sync(){}};const result=await run(c,{action:'paragraphs-apply',before:[before],spec:{paragraphs:[{index:0,before,after}],links:[],append:[]}},{},async()=>{});assert.equal(result.status,'paragraphs_save_returned');assert.equal(changed,'correcte');});

test('resolution verifies exact author and content, preserves other threads, and never deletes',async()=>{
 let saved=0;const comments=[{id:'native-guid',authorName:'Reviewer',content:'Keep this source.\r',resolved:false},{id:'other',authorName:'Other',content:'Unrelated',resolved:false}];
 const context={document:{body:{paragraphs:{items:[],load(){}},getComments:()=>({items:comments,load(){}})},changeTrackingMode:'Off',load(){},save(){saved++;}},async sync(){}};
 const approved={paragraphs:[],links:[],append:[],resolveComments:[{id:'package-id',authorName:'Wrong reviewer',content:'Keep this source.'}]};
 let result=await run(context,{action:'paragraphs-apply',before:[],spec:approved},{},async()=>{});assert.equal(result.status,'refused_before_mutation');assert.equal(saved,0);
 approved.resolveComments[0].authorName='Reviewer';result=await run(context,{action:'paragraphs-apply',before:[],spec:approved},{},async()=>{});assert.equal(result.status,'paragraphs_save_returned');assert.equal(comments[0].resolved,true);assert.equal(comments[1].resolved,false);assert.equal(saved,1);
});

test('accepts only the exact added revision and refuses mismatched authors',async()=>{
 let accepted=0;const change={type:'Added',author:'Reviewer',date:new Date('2026-01-01T12:00:00Z'),text:'Approved.',accept(){accepted++;}};
 const ctx={document:{body:{paragraphs:{items:[],load(){}},getTrackedChanges:()=>({items:[change],load(){}})},changeTrackingMode:'Off',load(){},save(){}},async sync(){}};
 const spec={paragraphs:[],links:[],append:[],acceptInsertions:[{id:'1',author:'Other',date:'2026-01-01T12:00:00Z',text:'Approved.'}]};
 assert.equal((await run(ctx,{action:'paragraphs-apply',before:[],spec},{},async()=>{})).status,'refused_before_mutation');assert.equal(accepted,0);
 spec.acceptInsertions[0].author='Reviewer';assert.equal((await run(ctx,{action:'paragraphs-apply',before:[],spec},{},async()=>{})).status,'paragraphs_save_returned');assert.equal(accepted,1);
});

test('whole-body replacement refuses review evidence and escapes literal text',async()=>{
 let html;const body={paragraphs:{items:[{text:'Old'}],load(){}},getComments:()=>({items:[{id:'keep'}],load(){}}),getTrackedChanges:()=>({items:[],load(){}}),insertHtml(x){html=x;}};
 const ctx={document:{body,changeTrackingMode:'Off',load(){},save(){}},async sync(){}};const spec={paragraphs:[],links:[],append:[],replaceBody:[{text:'A < B & C',format:{style:'Normal',size:11}}]};
 assert.equal((await run(ctx,{action:'paragraphs-apply',before:['Old'],spec},{},async()=>{})).status,'refused_before_mutation');assert.equal(html,undefined);
 body.getComments=()=>({items:[],load(){}});assert.equal((await run(ctx,{action:'paragraphs-apply',before:['Old'],spec},{},async()=>{})).status,'paragraphs_save_returned');assert.ok(html.includes('A &lt; B &amp; C'));assert.ok(!html.includes('A < B'));
});
