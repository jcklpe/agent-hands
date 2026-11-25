import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {parseArgs} from 'node:util';
import {randomUUID} from 'node:crypto';
import {ROOT,excelAccount,lockAccount,identifier,aliasName,writeJSON,readJSON,hash,markDispatch,fail} from './core.mjs';
import {targetFor} from './main.mjs';
import {openBrowser,browserIdentity} from '../../use-word-documents/scripts/browser.mjs';
import {requireWrite} from '../../use-word-documents/scripts/cloud.mjs';
import {startBridge} from './bridge.mjs';
import {openInstalledAddin} from './bootstrap.mjs';
import {validateLinks} from '../officejs/links.mjs';
const exec=promisify(execFile),emit=x=>process.stdout.write(JSON.stringify(x,null,2)+'\n');
let browser,bridge,unlock,activeJournal;
try{
 const {positionals:[command,rawAlias,...rest],values:o}=parseArgs({allowPositionals:true,options:{drive:{type:'string'},item:{type:'string'},file:{type:'string'},plan:{type:'string'},hash:{type:'string'},execute:{type:'boolean'}}});
 const allowed={preview:['drive','item','file'],apply:['plan','hash','execute'],verify:['plan']};
 if(rest.length||!allowed[command]||Object.keys(o).some(k=>!allowed[command].includes(k)))fail('invalid_arguments','Use links preview ALIAS --drive ID --item ID --file JSON; apply ALIAS --plan UUID --hash HASH --execute; verify ALIAS --plan UUID.');
 const alias=aliasName(rawAlias),account=excelAccount(alias);unlock=lockAccount(account);
 const files=id=>{if(!/^[a-f0-9-]{36}$/.test(id||''))fail('invalid_plan','Use the stored UUID.');return {plan:path.join(account.excelDir,'plans',id+'.json'),journal:path.join(account.excelDir,'plans',id+'.journal.json')};};
 let plan,target,profile,items;
 if(command==='preview'){
  if(!o.file||fs.statSync(o.file).size>2000000)fail('invalid_payload','Use a JSON file below 2 MB.');
  items=validateLinks(readJSON(o.file));({target,profile}=await targetFor(alias,identifier(o.drive),identifier(o.item)));
 }else{
  plan=readJSON(files(o.plan).plan);const {digest,...content}=plan;
  if(digest!==hash(content)||plan.kind!=='excel-add-links-v1'||plan.target.alias!==alias||(command==='apply'&&o.hash!==digest))fail('preview_mismatch','Stored preview mismatch.');
  items=validateLinks(plan.items);({target,profile}=await targetFor(alias,plan.target.drive,plan.target.item));
  if(JSON.stringify(target)!==JSON.stringify(plan.target))fail('target_mismatch','Workbook identity or location changed.');
 }
 async function verify(){
  const dir=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'excel-links-')));fs.chmodSync(dir,0o700);
  try{
   const file=path.join(dir,'saved.xlsx'),spec=path.join(dir,'expected.json');writeJSON(spec,items);
   await exec('bash',[path.join(ROOT,'use-microsoft-files/scripts/files'),'download',alias,target.item,'--drive',target.drive,'--out',file],{timeout:120000,maxBuffer:1000000});
   const r=await exec('python3',[path.join(ROOT,'use-excel-workbooks/live/links-readback.py'),file,spec],{timeout:30000,maxBuffer:1000000});return JSON.parse(r.stdout);
  }finally{fs.rmSync(dir,{recursive:true,force:true});}
 }
 if(command==='verify'){emit(await verify());}
 else{
  if(command==='apply'){
   if(!o.execute)fail('execute_required','Use --execute for the approved preview.');
   if(fs.existsSync(files(plan.id).journal))fail('already_dispatched','Use verify; never replay.');
   await requireWrite(alias);
  }
  bridge=await startBridge(account,target);browser=await openBrowser(account,target,true,bridge);await browserIdentity(browser.context,target,profile,false);await openInstalledAddin(browser,bridge,target);await bridge.waitReady(90000);
  const ready=await bridge.command('links-read',{request:{items}});
  if(ready.status!=='links_ready')fail('links_not_ready',ready.code||'Selected cells cannot receive links.');
  if(command==='preview'){
   const content={kind:'excel-add-links-v1',id:randomUUID(),target,items};plan={...content,digest:hash(content)};writeJSON(files(plan.id).plan,plan,true);
   emit({status:'preview',operation:plan.id,hash:plan.digest,target,count:items.length,characters:items.reduce((n,x)=>n+x.newAddress.length,0),limits:'Changes only existing hyperlinks with matching text and source address; formula cells are refused.'});
  }else{
   const journal=files(plan.id).journal;activeJournal=journal;markDispatch(journal,{status:'uncertain_after_dispatch',operation:plan.id});
   const result=await bridge.command('links-add',{request:{items}});writeJSON(journal,{...result,operation:plan.id,replayAllowed:false});
   const saved=await verify();writeJSON(journal,{...result,...saved,operation:plan.id,replayAllowed:false});emit({operation:plan.id,...saved,sessionStatus:result.status});
  }
 }
}catch(e){emit({status:activeJournal&&fs.existsSync(activeJournal)?'uncertain_after_dispatch':'failed',code:e.code||'links_failed',detail:e.message});process.exitCode=1;}
finally{try{if(browser)await browser.context.close();}finally{if(bridge)await bridge.close();if(unlock)unlock();}}
