import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {prepareAddin} from '../scripts/bootstrap.mjs';
import {previewShapes,makePlan,verifyPlan,operationFiles,markDispatch,targetFromMetadata} from '../scripts/core.mjs';
const shape={slideId:'256#10',shapeId:'4',name:'Text box',type:'TextBox',supported:true,text:'Target old text.'};
test('preview selects exact slide and shape and rejects ambiguous/unsupported edits',()=>{
 const edit=previewShapes([shape,{...shape,slideId:'257#11'}],shape.slideId,shape.shapeId,'old','new');
 assert.equal(edit.after,'Target new text.');
 for(const candidate of [[shape,shape],[{...shape,supported:false}],[{...shape,text:'old old'}],[{...shape,text:'😀 old'}]])assert.throws(()=>previewShapes(candidate,shape.slideId,shape.shapeId,'old','new'));
 assert.throws(()=>previewShapes([shape],shape.slideId,shape.shapeId,'old','new\nparagraph'),{code:'unsupported_edit'});
 const plan=makePlan({alias:'example'},edit);verifyPlan(plan,plan.hash);
 assert.throws(()=>verifyPlan({...plan,edit:{...edit,after:'corrupt'}},plan.hash),{code:'preview_mismatch'});
 assert.throws(()=>verifyPlan(plan,'wrong'),{code:'preview_mismatch'});
});
test('durable dispatch refuses replay and plan filenames cannot escape private storage',()=>{
 const dir=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'powerpoint-plan-')));fs.mkdirSync(path.join(dir,'plans'));
 try{
  const plan=makePlan({},previewShapes([shape],shape.slideId,shape.shapeId,'old','new'));
  const files=operationFiles({pptDir:dir},plan.id);markDispatch(files.journal,plan);
  assert.equal(JSON.parse(fs.readFileSync(files.journal)).status,'uncertain_after_dispatch');
  assert.throws(()=>markDispatch(files.journal,plan),{code:'already_dispatched'});
  assert.throws(()=>operationFiles({pptDir:dir},'../../escape'),{code:'invalid_plan'});
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
test('metadata rejects another item, wrong extension and non-SharePoint origin',()=>{
 const meta={id:'item',name:'Deck.pptx',file:{},parentReference:{driveId:'drive'},webUrl:'https://example.sharepoint.com/sites/demo/Deck.pptx'};
 assert.equal(targetFromMetadata('example','drive','item',meta).name,'Deck.pptx');
 for(const changes of [{id:'other'},{name:'Deck.docx'},{webUrl:'https://evil.test/Deck.pptx'}])assert.throws(()=>targetFromMetadata('example','drive','item',{...meta,...changes}));
});
test('writes without execute and arbitrary browser overrides fail before account access',()=>{
 for(const [entry,args,expected] of [
  ['../../setup-microsoft-services/scripts/powerpoint-browser.mjs',['prepare','example','--drive','drive','--item','item'],'execute_required'],
  ['../scripts/powerpoint.mjs',['apply','example','--plan','missing','--hash','missing'],'execute_required'],
  ['../scripts/powerpoint.mjs',['read','example','--profile','ordinary-chrome'],'ERR_PARSE_ARGS_UNKNOWN_OPTION']
 ]){
  let result;try{execFileSync(process.execPath,[fileURLToPath(new URL(entry,import.meta.url)),...args],{encoding:'utf8'});assert.fail('Unexpected success');}catch(e){result=JSON.parse(e.stdout);}
  assert.equal(result.status,expected);assert.ok(!JSON.stringify(result).includes('ordinary-chrome'));
 }
});

test('known cloud startup waits for its add-in instead of racing ribbon setup',async()=>{
 const target={origin:'https://example.sharepoint.com',pathname:'/sites/demo/Deck.pptx'};
 const browser={page:{url:()=>target.origin+target.pathname}};
 const bridge={waitReady:async timeout=>{assert.equal(timeout,90000);}};
 assert.equal(await prepareAddin(browser,bridge,{},target,true),'already_running');
 await assert.rejects(prepareAddin(browser,{waitReady:async()=>{throw Object.assign(new Error('late'),{code:'addin_setup_required'});}}, {},target,true),{code:'automatic_setup_incomplete'});
});
