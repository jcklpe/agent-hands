#!/usr/bin/env node
import {requireWrite} from '../../use-word-documents/scripts/cloud.mjs';
import fs from 'node:fs';
import path from 'node:path';
import {execFile} from 'node:child_process';
import {parseArgs,promisify} from 'node:util';
import {ROOT,loadAccount,lockAccount,aliasName,readJSON,writeJSON,noSymlinks} from '../../use-word-documents/scripts/core.mjs';
import {launchOwnedBrowser} from '../../use-word-documents/scripts/browser.mjs';
import {preview,readPlan,paths} from './plans.mjs';
import {digest,validateSpec,fail} from './schema.mjs';
import * as editor from './editor.mjs';
const exec=promisify(execFile),emit=v=>console.log(JSON.stringify(v));
let context,release;
try{
 const {positionals,values}=parseArgs({allowPositionals:true,strict:true,options:{'source-plan':{type:'string'},question:{type:'string'},'text-file':{type:'string'},plan:{type:'string'},hash:{type:'string'},execute:{type:'boolean'},'allow-form-write':{type:'boolean'},help:{type:'boolean'}}});
 const [command,alias,...extra]=positionals,allowed={preview:['source-plan','question','text-file'],apply:['plan','hash','execute','allow-form-write']};
 if(values.help||!command){console.log('forms-subtitle preview ALIAS --source-plan ID --question QUESTION_ID --text-file FILE\nforms-subtitle apply ALIAS --plan ID --hash SHA256 --execute --allow-form-write');}
 else{
  if(extra.length||!allowed[command]||Object.keys(values).some(k=>!allowed[command].includes(k)))fail('invalid_arguments','Use forms-subtitle --help.');
  const account=loadAccount(aliasName(alias));if(command==='apply')await requireWrite(alias);
  const profile=JSON.parse((await exec('bash',[path.join(ROOT,'setup-microsoft-services/scripts/authorize'),'profile',alias,'--json'],{timeout:120000,maxBuffer:1000000})).stdout);
  let source,after,plan,index;
  if(command==='preview'){
   const stored=readJSON(paths(account,values['source-plan']).plan);source=readPlan(account,stored.id,stored.hash);
   index=source.spec.questions.findIndex(q=>q.id===values.question);if(index<0)fail('invalid_question','Use a question ID from the retained form specification.');
   noSymlinks(values['text-file']);if(fs.statSync(values['text-file']).size>16000)fail('input_too_large','Subtitle input exceeds the bounded text-file size.');
   const text=fs.readFileSync(values['text-file'],'utf8').replace(/\r?\n$/,'');
   after=structuredClone(source.spec);after.questions[index].description=text;validateSpec(after);
  }else{
   if(!values.execute||!values['allow-form-write'])fail('execute_required','Apply requires --execute and --allow-form-write after approval of the exact change.');
   plan=readPlan(account,values.plan,values.hash);if(!plan.change||plan.change.action!=='replace-subtitle')fail('invalid_plan','Use a subtitle preview.');
   source=readPlan(account,plan.change.sourceOperation,plan.change.sourceHash);index=source.spec.questions.findIndex(q=>q.id===plan.change.question);
   if(index<0||source.target!==plan.target)fail('preview_mismatch','The source question or target differs.');
   after=structuredClone(source.spec);after.questions[index].description=plan.spec.questions[index]?.description;
   if(digest(after)!==digest(plan.spec))fail('preview_mismatch','The preview changes more than the selected subtitle.');
   if(fs.existsSync(paths(account,plan.id).journal))fail('already_dispatched','This subtitle change has a receipt; use forms verify and do not replay it.');
  }
  if(profile.id!==source.accountId)fail('account_mismatch','Selected Microsoft account differs from the source preview.');
  release=lockAccount(account);context=await launchOwnedBrowser(account,true);const page=await context.newPage();for(const other of context.pages())if(other!==page)await other.close();
  await page.goto(source.target,{waitUntil:'domcontentloaded',timeout:60000});await editor.checkIdentity(page,profile);await editor.verifyForm(page,source.spec);
  if(command==='preview'){
   plan=preview(account,profile,after,source.target);const {hash,...body}=plan;
   body.change={action:'replace-subtitle',sourceOperation:source.id,sourceHash:source.hash,question:values.question};
   plan={...body,hash:digest(body)};writeJSON(paths(account,plan.id).plan,plan);
   emit({status:'subtitle_preview',operation:plan.id,hash:plan.hash,target:plan.target,question:values.question,before:source.spec.questions[index].description??'',after:after.questions[index].description});
  }else{
   const file=paths(account,plan.id).journal;writeJSON(file,{operation:plan.id,hash:plan.hash,status:'uncertain_after_dispatch',target:plan.target},true);
   try{
    const cards=page.locator('[data-automation-id="questionWrapper"], [data-automation-id="questionDesignerCard"]');const card=cards.nth(index);if(await card.getAttribute('data-automation-id')==='questionWrapper')await card.click();
    const title=page.getByRole('textbox',{name:/^Question title /});if(await title.innerText()!==source.spec.questions[index].title)fail('question_mismatch','The selected question changed.');
    const subtitle=page.getByRole('textbox',{name:/subtitle/i});if(await subtitle.count()!==1||await subtitle.innerText()!==(source.spec.questions[index].description??''))fail('stale_subtitle','The current subtitle differs from preview.');
    await subtitle.click();await subtitle.fill(after.questions[index].description);await editor.saved(page);
    await page.goto(plan.target,{waitUntil:'domcontentloaded',timeout:60000});await editor.checkIdentity(page,profile);const result=await editor.verifyForm(page,plan.spec);
    writeJSON(file,{operation:plan.id,hash:plan.hash,status:'form_verified',target:plan.target,verification:result});emit({...result,operation:plan.id,target:plan.target});
   }catch(error){writeJSON(file,{operation:plan.id,hash:plan.hash,status:'uncertain_after_dispatch',target:plan.target,code:error.code||'ui_error'});throw error;}
  }
 }
}catch(error){emit({status:error.code||'failed',detail:String(error.message).replace(/https?:\/\/[^\s]+/g,'[url]').slice(0,500)});process.exitCode=1;}
finally{if(context)await context.close();if(release)release();}
