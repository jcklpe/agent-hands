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
