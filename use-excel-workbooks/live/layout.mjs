import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {execFile} from 'node:child_process';
import {promisify,parseArgs} from 'node:util';
import {randomUUID} from 'node:crypto';
import {ROOT,excelAccount,lockAccount,identifier,aliasName,writeJSON,readJSON,hash,markDispatch,fail} from './core.mjs';
import {targetFor} from './main.mjs';
import {openBrowser,browserIdentity} from '../../use-word-documents/scripts/browser.mjs';
import {requireWrite} from '../../use-word-documents/scripts/cloud.mjs';
import {startBridge} from './bridge.mjs';
import {openInstalledAddin} from './bootstrap.mjs';
import {validateLayout} from '../officejs/layout.mjs';
const exec=promisify(execFile),emit=x=>process.stdout.write(JSON.stringify(x,null,2)+'\n');
let browser,bridge,unlock,journal;
try {
  const {positionals:[command,rawAlias,...rest],values:o}=parseArgs({allowPositionals:true,options:{drive:{type:'string'},item:{type:'string'},file:{type:'string'},plan:{type:'string'},hash:{type:'string'},execute:{type:'boolean'}}});
  const allowed={preview:['drive','item','file'],apply:['plan','hash','execute'],verify:['plan']};
  if(rest.length||!allowed[command]||Object.keys(o).some(k=>!allowed[command].includes(k)))fail('invalid_arguments','Use layout preview ALIAS --drive ID --item ID --file JSON; apply ALIAS --plan UUID --hash HASH --execute; verify ALIAS --plan UUID.');
  const alias=aliasName(rawAlias),account=excelAccount(alias);unlock=lockAccount(account);
  const files=id=>{if(!/^[a-f0-9-]{36}$/.test(id||''))fail('invalid_plan','Use the stored UUID.');return {plan:path.join(account.excelDir,'plans',id+'.json'),journal:path.join(account.excelDir,'plans',id+'.journal.json')};};
  let plan,target,profile,spec;
  if(command==='preview') {
    if(!o.file||fs.statSync(o.file).size>1000000)fail('invalid_payload','Use a JSON file below 1 MB.');
    spec=validateLayout(readJSON(o.file));({target,profile}=await targetFor(alias,identifier(o.drive),identifier(o.item)));
  } else {
    plan=readJSON(files(o.plan).plan);const {digest,...content}=plan;
    if(digest!==hash(content)||plan.kind!=='excel-layout-v1'||plan.target.alias!==alias||(command==='apply'&&o.hash!==digest))fail('preview_mismatch','Stored preview mismatch.');
    spec=validateLayout(plan.spec);({target,profile}=await targetFor(alias,plan.target.drive,plan.target.item));
    if(JSON.stringify(target)!==JSON.stringify(plan.target))fail('target_mismatch','Workbook identity or location changed.');
  }
  async function saved(verify=false) {
    const dir=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'excel-layout-')));fs.chmodSync(dir,0o700);
    try {
      const file=path.join(dir,'saved.xlsx');
      await exec('bash',[path.join(ROOT,'use-microsoft-files/scripts/files'),'download',alias,target.item,'--drive',target.drive,'--out',file],{timeout:120000,maxBuffer:1000000});
      let args=['snapshot',file];
      if(verify) { const b=path.join(dir,'before.json'),s=path.join(dir,'spec.json');writeJSON(b,plan.savedBefore);writeJSON(s,spec);args=['verify',b,file,s]; }
      return JSON.parse((await exec('python3',[path.join(ROOT,'use-excel-workbooks/live/layout-readback.py'),...args],{timeout:30000,maxBuffer:16000000})).stdout);
    } finally {fs.rmSync(dir,{recursive:true,force:true});}
  }
  if(command==='verify') {const result=await saved(true);emit(result);if(result.status!=='saved_layout_verified')process.exitCode=1;}
  else {
    if(command==='apply') {
      if(!o.execute)fail('execute_required','Use --execute for the approved preview.');
      if(fs.existsSync(files(plan.id).journal))fail('already_dispatched','Use verify; never replay.');
      await requireWrite(alias);
    }
    bridge=await startBridge(account,target);browser=await openBrowser(account,target,true,bridge);await browserIdentity(browser.context,target,profile,false);await openInstalledAddin(browser,bridge,target);await bridge.waitReady();
    const ready=await bridge.command('layout-read',{request:{spec}},undefined,180000);
    if(ready.status!=='layout_ready')fail('layout_not_ready',ready.code||'Selected cells cannot receive this layout.');
    const baseline=await saved();
    if(command==='preview') {
      const content={kind:'excel-layout-v1',id:randomUUID(),target,spec,expected:ready.snapshot,savedBefore:baseline};plan={...content,digest:hash(content)};writeJSON(files(plan.id).plan,plan,true);
      emit({status:'preview',operation:plan.id,hash:plan.digest,name:target.name,sheets:spec.sheets,tables:spec.tables,ranges:spec.ranges.length,cells:spec.cells,limitation:'Same-cell coauthoring can race the final check; visual acceptance is separate.'});
    } else {
      if(hash(baseline)!==hash(plan.savedBefore)||JSON.stringify(ready.snapshot)!==JSON.stringify(plan.expected))fail('stale_preview','Saved workbook or selected cells changed after preview.');
      journal=files(plan.id).journal;
      const result=await bridge.command('layout-apply',{request:{spec,expected:plan.expected}},()=>markDispatch(journal,{id:plan.id,hash:plan.digest}),180000);
      // Release the coauthoring session before independent persistence checks; a native save acknowledgment alone is not cloud persistence.
      await browser.context.close();browser=null;await bridge.close();bridge=null;
      let check={status:'saved_layout_unverified'};
      if(result.status!=='refused_before_mutation') for(let i=0;i<5;i++) {check=await saved(true);if(check.status==='saved_layout_verified')break;await new Promise(r=>setTimeout(r,2000));}
      const outcome={operation:plan.id,...check,sessionStatus:result.status,code:result.code,replayAllowed:false};writeJSON(journal,outcome);emit(outcome);if(check.status!=='saved_layout_verified')process.exitCode=1;
    }
  }
} catch(e) {emit({status:journal&&fs.existsSync(journal)?'uncertain_after_dispatch':e.code||'failed',detail:e.code?e.message:'Layout failed; inspect the retained operation before another edit.'});process.exitCode=1;}
finally {try {if(browser)await browser.context.close();} finally {if(bridge)await bridge.close();unlock?.();}}
