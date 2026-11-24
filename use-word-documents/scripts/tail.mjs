#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {parseArgs} from 'node:util';
import {ROOT,aliasName,identifier,loadAccount,lockAccount,readJSON,writeJSON,operationFiles,makePlan,hash,markDispatch,fail,sleep} from './core.mjs';
import {startBridge} from './bridge.mjs';
import {openBrowser,browserIdentity} from './browser.mjs';
import {cloudTarget,requireWrite} from './cloud.mjs';
import {privateTempDir} from './temporary.mjs';
import {bodySnapshot,tailEdit,sameParagraphs} from './tail-core.mjs';
const exec=promisify(execFile), emit=value=>process.stdout.write(JSON.stringify(value,null,2)+'\n');
async function snapshot(target){
 const dir=privateTempDir('agent-hands-word-readback-');
 try{
  const file=path.join(dir,'body.docx');
  await exec('bash',[path.join(ROOT,'use-microsoft-files/scripts/files'),'download',target.alias,target.item,'--drive',target.drive,'--out',file],{maxBuffer:1_000_000,timeout:120000});
  return bodySnapshot(fs.readFileSync(file));
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
}
function checkPlan(plan,expected){
 const {hash:digest,...content}=plan;
 if(digest!==hash(content)||digest!==expected||plan.edit.kind!=='replace-tail')fail('preview_mismatch','The stored tail preview does not match the supplied hash.');
 const {anchor,label,url,replacements}=plan.edit;
 const rebuilt=tailEdit(plan.edit.before,{anchor,label,url,replacements});
 if(!sameParagraphs(rebuilt.after,plan.edit.after))fail('preview_mismatch','The stored tail result is inconsistent.');
}
let browser,bridge,release,dispatch,active;
async function cleanup(){const closing=browser,closingBridge=bridge,unlock=release;browser=null;bridge=null;release=null;try{if(closing)await closing.context.close();}finally{try{if(closingBridge)await closingBridge.close();}finally{if(unlock)unlock();}}}
const signal=()=>{void cleanup().finally(()=>process.exit(130));};
process.once('SIGINT',signal);process.once('SIGTERM',signal);
try{
 const {positionals,values}=parseArgs({allowPositionals:true,strict:true,options:{drive:{type:'string'},item:{type:'string'},spec:{type:'string'},plan:{type:'string'},hash:{type:'string'},execute:{type:'boolean'},help:{type:'boolean'}}});
 const [command,alias,...rest]=positionals;
 if(values.help||!command){console.log('word-tail preview ALIAS --drive DRIVE --item ITEM --spec JSON_FILE\nword-tail apply ALIAS --plan ID --hash SHA256 --execute\nword-tail verify ALIAS --plan ID');}
 else{
  const allowed={preview:['drive','item','spec'],apply:['plan','hash','execute'],verify:['plan']};
  if(rest.length||!allowed[command]||Object.keys(values).some(k=>!allowed[command].includes(k)))fail('invalid_arguments','Use word-tail --help.');
  const account=loadAccount(aliasName(alias));release=lockAccount(account);
  let target,profile,plan,files;
  if(command==='preview')({target,profile}=await cloudTarget(alias,identifier(values.drive),identifier(values.item)));
  else{
   files=operationFiles(account,values.plan);plan=readJSON(files.plan);checkPlan(plan,command==='apply'?values.hash:plan.hash);active=plan;
   if(plan.target.alias!==alias)fail('account_mismatch','Preview belongs to another account.');
   ({target,profile}=await cloudTarget(alias,plan.target.drive,plan.target.item));
   for(const key of ['origin','guid','pathname','canonicalPath'])if(target[key]!==plan.target[key])fail('target_mismatch','The document identity changed after preview.');
   if(command==='verify'){
    const current=await snapshot(target),status=sameParagraphs(current,plan.edit.after)?'cloud_text_verified':sameParagraphs(current,plan.edit.before)?'original_text_observed':'cloud_conflict_or_unverified';
    emit({status,operation:plan.id,replayAllowed:false});if(status!=='cloud_text_verified')process.exitCode=1;
   }
   if(command==='apply'&&(!values.execute||fs.existsSync(files.journal)))fail(fs.existsSync(files.journal)?'already_dispatched':'execute_required','Apply requires --execute and an operation that has never been dispatched. Use verify after uncertainty.');
  }
  if(command!=='verify'){
   if(command==='apply')await requireWrite(alias);
   bridge=await startBridge(account,target);browser=await openBrowser(account,target,true,bridge);
   await browserIdentity(browser.context,target,profile);await bridge.waitReady();
   const read=await bridge.command('read');
   if(read.status!=='read_ok')fail('read_failed','Word did not return document paragraphs.');
   const cloud=await snapshot(target);
   if(!sameParagraphs(read.paragraphs,cloud))fail('cloud_baseline_mismatch','The complete Word body and cloud body differ. Wait for coauthoring synchronization and preview again.');
   if(command==='preview'){
    const spec=readJSON(values.spec),edit=tailEdit(read.paragraphs,spec);plan=makePlan(target,edit);writeJSON(operationFiles(account,plan.id).plan,plan,true);
    emit({status:'tail_preview',operation:plan.id,hash:plan.hash,name:target.name,removeFrom:edit.anchor,removedParagraphCount:edit.before.length-edit.after.length+1,replacements:edit.replacements,link:{label:edit.label,url:edit.url},after:edit.after});
   }else{
    if(!sameParagraphs(read.paragraphs,plan.edit.before))fail('stale_preview','Document text changed since preview; no mutation was sent.');
    await browserIdentity(browser.context,target,profile);dispatch=files.journal;
    const result=await bridge.command('replace-tail',{edit:plan.edit},()=>markDispatch(files.journal,plan));
    writeJSON(files.journal,{operation:plan.id,hash:plan.hash,status:result.status,time:new Date().toISOString()});
    let verified=false;
    if(result.status!=='refused_before_mutation')for(let i=0;i<6;i++){if(sameParagraphs(await snapshot(target),plan.edit.after)){verified=true;break;}await sleep(2000);}
    const final={status:verified?'cloud_text_verified':result.status==='refused_before_mutation'?result.status:'uncertain_after_dispatch',operation:plan.id,sessionStatus:result.status,code:result.code,replayAllowed:false};writeJSON(files.journal,final);emit(final);if(!verified)process.exitCode=1;
   }
  }
 }
}catch(error){emit({status:dispatch&&fs.existsSync(dispatch)?'uncertain_after_dispatch':error.code||'failed',...(active?{operation:active.id}:{}),detail:/^[a-z][a-z_]+$/.test(error.code||'')?error.message:'Tail operation failed; inspect its status and do not replay a dispatched mutation.'});process.exitCode=1;}
finally{await cleanup();process.removeListener('SIGINT',signal);process.removeListener('SIGTERM',signal);}
