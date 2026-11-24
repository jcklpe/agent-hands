import fs from 'node:fs';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {digest,validateSpec,fail} from './schema.mjs';
import {privateDir,readJSON,writeJSON,noSymlinks} from '../../use-word-documents/scripts/core.mjs';

export function paths(account,id){
 if(!/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(id||''))fail('invalid_plan','Use an operation ID returned by preview.');
 const dir=path.join(account.dir,'forms-plans');privateDir(dir);
 return {plan:path.join(dir,id+'.json'),journal:path.join(dir,id+'.journal.json')};
}
export function validateTarget(target){
 if(target===null)return;
 let url;try{url=new URL(target);}catch{fail('invalid_target','Use the exact Forms design URL.');}
 if(!['https://forms.cloud.microsoft','https://forms.office.com'].includes(url.origin)||url.pathname!=='/Pages/DesignPageV2.aspx'||!url.searchParams.get('id')||url.username||url.password||url.hash||[...url.searchParams.keys()].some(k=>!['id','subpage','origin','topview','branchingelementid'].includes(k)))fail('invalid_target','Use an HTTPS Microsoft Forms design URL with an id and no authentication parameters.');
}
export function preview(account,profile,input,target=null){
 const spec=validateSpec(input);
 validateTarget(target);
 const content={kind:'agent-hands-forms-create-v1',id:randomUUID(),created:new Date().toISOString(),alias:account.alias,owner:account.owner,accountId:profile.id,accountNames:[profile.mail,profile.userPrincipalName].filter(Boolean),target,spec};
 if(!content.accountId||!content.accountNames.length)fail('account_unverified','Microsoft setup did not return an exact account identity.');
 const plan={...content,hash:digest(content)};writeJSON(paths(account,plan.id).plan,plan,true);return plan;
}
export function readPlan(account,id,expected){
 const file=paths(account,id).plan;noSymlinks(file);const plan=readJSON(file),{hash,...content}=plan;
 if(plan.kind!=='agent-hands-forms-create-v1'||plan.alias!==account.alias||plan.owner!==account.owner||hash!==digest(content)||hash!==expected)fail('preview_mismatch','The stored form preview, account or supplied hash differs.');
 validateSpec(plan.spec);validateTarget(plan.target);return plan;
}
export async function apply(account,plan,profile,adapter){
 const files=paths(account,plan.id);
 if(profile.id!==plan.accountId)fail('account_mismatch','The selected Microsoft account changed since preview.');
 if(fs.existsSync(files.journal))fail('already_dispatched','This form operation has a dispatch record. Inspect its saved form; do not create another form by replaying it.');
 await adapter.checkIdentity(plan.accountNames);
 await adapter.requireNoExistingTitle(plan.spec.title);
 const state={kind:'agent-hands-forms-dispatch-v1',operation:plan.id,hash:plan.hash,status:'uncertain_after_dispatch',steps:[],created:new Date().toISOString()};
 writeJSON(files.journal,state,true);
 const step=async(name,action)=>{
  state.steps.push({name,status:'dispatched',time:new Date().toISOString()});writeJSON(files.journal,state);
  const result=await action();state.steps.at(-1).status='returned';writeJSON(files.journal,state);return result;
 };
 try{
  const target=await step('create form',()=>adapter.createForm());
  if(!target?.url)fail('created_form_unidentified','Creation returned without an exact form URL. Inspect Forms manually before any new create.');
  state.target=target;writeJSON(files.journal,state);
  await step('close response collection',()=>adapter.closeResponses());
  await step('set title and description',()=>adapter.setIntroduction(plan.spec.title,plan.spec.description));
  for(const question of plan.spec.questions)await step('question '+question.id,()=>adapter.addQuestion(question));
  await step('set branching',()=>adapter.setBranching(plan.spec.questions));
  state.status='saved_unverified';writeJSON(files.journal,state);
  const actual=await adapter.reopenAndRead(target);
  await adapter.verify(plan.spec,actual);
  state.status='form_verified';state.verified=new Date().toISOString();writeJSON(files.journal,state);return state;
 }catch(error){
  state.status=state.target?'partial_form_created':'uncertain_after_dispatch';state.code=/^[a-z][a-z_]+$/.test(error.code||'')?error.code:'authoring_failed';writeJSON(files.journal,state);
  return state;
 }
}
