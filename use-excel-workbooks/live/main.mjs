import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {parseArgs} from 'node:util';
import {randomUUID} from 'node:crypto';
import {ROOT,excelAccount,targetFromMetadata,lockAccount,identifier,aliasName,writeJSON,readJSON,hash,markDispatch,fail} from './core.mjs';
import {openBrowser,browserIdentity} from '../../use-word-documents/scripts/browser.mjs';
import {requireWrite} from '../../use-word-documents/scripts/cloud.mjs';
import {startBridge,manifest} from './bridge.mjs';
import {openInstalledAddin} from './bootstrap.mjs';
import {validateRequest,validateRuns,sameColoredText} from '../officejs/text-runs.mjs';
const exec=promisify(execFile),emit=o=>process.stdout.write(JSON.stringify(o,null,2)+'\n');
async function provider(script,args){const r=await exec('bash',[path.join(ROOT,script),...args],{maxBuffer:2000000,timeout:120000});return r.stdout;}
export async function targetFor(alias,drive,item){
 const profile=JSON.parse(await provider('setup-microsoft-services/scripts/authorize',['profile',alias,'--json']));
 const meta=JSON.parse(await provider('use-microsoft-files/scripts/files',['meta',alias,item,'--drive',drive,'--json']));
 if(!Number.isSafeInteger(meta.size)||meta.size>20000000)fail('file_too_large','Workbook must be at most 20 MB.');
 const parent=JSON.parse(await provider('use-microsoft-files/scripts/files',['meta',alias,meta.parentReference.id,'--drive',drive,'--json']));
 return {profile,target:targetFromMetadata(alias,drive,item,meta,parent)};
}
async function readSaved(target,selection){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'excel-text-runs-'));fs.chmodSync(dir,0o700);
 try{
  const file=path.join(dir,'readback.xlsx');
  await provider('use-microsoft-files/scripts/files',['download',target.alias,target.item,'--drive',target.drive,'--out',file]);
  const r=await exec('python3',[path.join(ROOT,'use-excel-workbooks/live/readback.py'),file,selection.sheet,selection.cell],{timeout:30000,maxBuffer:1000000});
  return JSON.parse(r.stdout);
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
}
const cleanRead=read=>{const {status,id,...snapshot}=read;return snapshot;};
export async function main(argv){
 let browser,bridge,unlock,journal,dispatched=false;
 try{
  const {positionals,values:o}=parseArgs({args:argv,allowPositionals:true,strict:true,options:{drive:{type:'string'},item:{type:'string'},sheet:{type:'string'},cell:{type:'string'},file:{type:'string'},plan:{type:'string'},hash:{type:'string'},execute:{type:'boolean'},help:{type:'boolean'}}});
  const [command,rawAlias,...extra]=positionals;
  if(!command||o.help||command==='help'){emit({usage:['excel-live configure ALIAS --drive ID --item ID --execute','excel-live read ALIAS --drive ID --item ID --sheet NAME --cell B2','excel-live preview ALIAS --drive ID --item ID --sheet NAME --cell B2 --file runs.json','excel-live apply ALIAS --plan UUID --hash SHA256 --execute','excel-live verify ALIAS --plan UUID'],setup:'Requires the owned Microsoft Office browser account. Configure prints the manifest path for the authorized disposable workbook; complete its add-in upload in that separate window. No whole-file upload.'});return;}
  const allowed={configure:['drive','item','execute'],read:['drive','item','sheet','cell'],preview:['drive','item','sheet','cell','file'],apply:['plan','hash','execute'],verify:['plan']};
  if(!allowed[command]||extra.length||Object.keys(o).some(k=>!allowed[command].includes(k)))fail('invalid_arguments','Use help for supported options.');
  if(['apply','configure'].includes(command)&&!o.execute)fail('execute_required','This operation requires --execute.');
  const alias=aliasName(rawAlias),account=excelAccount(alias);unlock=lockAccount(account);
  let plan,selection,target,profile;
  const files=id=>{if(!/^[a-f0-9-]{36}$/.test(id||''))fail('invalid_plan','Use the preview operation ID.');return {plan:path.join(account.excelDir,'plans',id+'.json'),journal:path.join(account.excelDir,'plans',id+'.journal.json')};};
  if(['apply','verify'].includes(command)){
   const f=files(o.plan);plan=readJSON(f.plan);journal=f.journal;
   const {digest,...content}=plan;
   if(digest!==hash(content)||plan.kind!=='excel-text-runs-v1'||plan.id!==o.plan||plan.target.alias!==alias||(command==='apply'&&digest!==o.hash))fail('preview_mismatch','Stored preview or supplied hash does not match.');
   selection=validateRequest(plan.selection);validateRuns(plan.runs);
   ({target,profile}=await targetFor(alias,identifier(plan.target.drive),identifier(plan.target.item)));
   if(JSON.stringify(target)!==JSON.stringify(plan.target))fail('target_mismatch','Workbook identity changed.');
   if(command==='verify'){
    const saved=await readSaved(target,selection),ok=!saved.formula&&sameColoredText(saved.runs,plan.runs);
    const verification={status:ok?'saved_runs_verified':'saved_runs_unverified',replayAllowed:false,operation:plan.id};
    if(fs.existsSync(journal))writeJSON(journal,{...readJSON(journal),reconciliation:verification.status,reconciledAt:new Date().toISOString()});
    emit(verification);if(!ok)process.exitCode=1;return;
   }
   if(fs.existsSync(journal))fail('already_dispatched','Use verify; do not replay a dispatched operation.');
  }else{
   ({target,profile}=await targetFor(alias,identifier(o.drive),identifier(o.item)));
   if(command!=='configure')selection=validateRequest({sheet:o.sheet,cell:o.cell});
  }
  if(['apply','configure'].includes(command))await requireWrite(alias);
  bridge=await startBridge(account,target);
  if(command==='configure'){
   const file=path.join(account.excelDir,'manifest.xml');fs.writeFileSync(file,manifest(account),{mode:0o600});
   emit({status:'setup_required',manifest:file,instructions:'In the separate Agent Hands window, upload this manifest through Excel Add-ins and open Excel tools. Only the selected workbook is authorized.'});
  }
  browser=await openBrowser(account,target,command!=='configure',bridge);
  await browserIdentity(browser.context,target,profile,command==='configure');
  if(command!=='configure')await openInstalledAddin(browser,bridge,target);
  await bridge.waitReady(command==='configure'?600000:90000);
  if(command==='configure'){emit({status:'addin_session_connected',automaticStartupChanged:false});return;}
  const read=await bridge.command('read',{request:selection});
  if(read.status!=='read_ok')fail(read.code||'read_failed','Excel refused the selected text cell.');
  const expected=cleanRead(read);
  if(command==='read'){emit(read);return;}
  if(command==='preview'){
   if(!o.file||!fs.statSync(o.file).isFile()||fs.statSync(o.file).size>1000000)fail('invalid_runs_file','Use a JSON runs file of at most 1 MB.');
   const runs=validateRuns(JSON.parse(fs.readFileSync(o.file,'utf8')));
   const saved=await readSaved(target,selection);
   if(saved.formula||saved.text!==expected.text)fail('cloud_baseline_mismatch','Saved text differs from the session; wait for synchronization.');
   const content={kind:'excel-text-runs-v1',id:randomUUID(),target,selection,expected,runs};
   plan={...content,digest:hash(content)};writeJSON(files(plan.id).plan,plan,true);
   emit({status:'preview',operation:plan.id,hash:plan.digest,before:expected,after:runs,limitation:'Same-cell coauthor edits can race after the final check.'});return;
  }
  if(JSON.stringify(expected)!==JSON.stringify(plan.expected))fail('stale_preview','Cell text or formatting changed.');
  const savedBefore=await readSaved(target,selection);
  if(savedBefore.formula||savedBefore.text!==plan.expected.text)fail('cloud_baseline_mismatch','Saved text changed.');
  await browserIdentity(browser.context,target,profile);
  const result=await bridge.command('write',{request:{...selection,expected:plan.expected,runs:plan.runs}},()=>{markDispatch(journal,{id:plan.id,hash:plan.digest});dispatched=true;});
  await browser.context.close();browser=null;await bridge.close();bridge=null;
  let verified=false;
  if(result.status!=='refused_before_mutation')for(let n=0;n<6;n++){
   const saved=await readSaved(target,selection);verified=!saved.formula&&sameColoredText(saved.runs,plan.runs);if(verified)break;await new Promise(r=>setTimeout(r,2000));
  }
  const outcome={status:verified?'saved_runs_verified':result.status==='refused_before_mutation'?result.status:'uncertain_after_dispatch',operation:plan.id,sessionStatus:result.status,replayAllowed:false};
  writeJSON(journal,outcome);emit(outcome);if(!verified)process.exitCode=1;
 }catch(e){emit({status:dispatched?'uncertain_after_dispatch':e.code||'failed',detail:/^[a-z_]+$/.test(e.code||'')?e.message:'Check the owned Office browser setup and provider access. No mutation is automatically retried.'});process.exitCode=1;}
 finally{
  let closed=true;
  try{if(browser)await browser.context.close();}catch{closed=false;}
  try{if(bridge)await bridge.close();}catch{closed=false;}
  if(closed)unlock?.();
  else{emit({status:'cleanup_incomplete',detail:'The owned session may still be active. Its lock is retained; inspect before another operation.'});process.exitCode=1;}
 }
}
