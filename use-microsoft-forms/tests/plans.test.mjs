import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {preview,readPlan,apply,paths} from '../scripts/plans.mjs';
const spec={version:1,title:'Example',description:'',acceptResponses:false,questions:[{id:'name',title:'Name',type:'text',required:true}]};
const profile={id:'account-one',mail:'editor@example.test'};
function fixture(){const dir=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'forms-plan-')));return {dir,alias:'demo',owner:'owner-one'};}
test('preview detects payload or account tampering',()=>{
 const account=fixture();try{
  const plan=preview(account,profile,spec);assert.equal(readPlan(account,plan.id,plan.hash).spec.title,'Example');
  assert.throws(()=>readPlan(account,plan.id,'wrong'),{code:'preview_mismatch'});
  assert.throws(()=>readPlan({...account,owner:'other'},plan.id,plan.hash),{code:'preview_mismatch'});
 }finally{fs.rmSync(account.dir,{recursive:true,force:true});}
});
test('partial creation is recorded before question failure and never replayed',async()=>{
 const account=fixture();let creates=0;try{
  const plan=preview(account,profile,spec);
  const adapter={checkIdentity:async()=>{},requireNoExistingTitle:async()=>{},createForm:async()=>{assert.ok(fs.existsSync(paths(account,plan.id).journal));creates++;return {url:'https://forms.cloud.microsoft/Pages/DesignPageV2.aspx?id=synthetic'};},closeResponses:async()=>{},setIntroduction:async()=>{},addQuestion:async()=>{throw Object.assign(Error('network'),{code:'ui_unavailable'});}};
  const result=await apply(account,plan,profile,adapter);assert.equal(result.status,'partial_form_created');assert.ok(result.target.url);assert.equal(result.steps.at(-1).status,'dispatched');
  await assert.rejects(apply(account,plan,profile,adapter),{code:'already_dispatched'});assert.equal(creates,1);
 }finally{fs.rmSync(account.dir,{recursive:true,force:true});}
});
test('identity mismatch and duplicate title prevent the dispatch receipt and creation',async()=>{
 const account=fixture();try{
  const plan=preview(account,profile,spec);
  await assert.rejects(apply(account,plan,{id:'wrong'},{}),{code:'account_mismatch'});
  await assert.rejects(apply(account,plan,profile,{checkIdentity:async()=>{},requireNoExistingTitle:async()=>{throw Object.assign(Error('exists'),{code:'duplicate_title'});}}),{code:'duplicate_title'});
  assert.ok(!fs.existsSync(paths(account,plan.id).journal));
 }finally{fs.rmSync(account.dir,{recursive:true,force:true});}
});
