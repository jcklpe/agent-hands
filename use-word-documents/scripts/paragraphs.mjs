import fs from 'node:fs';
import path from 'node:path';
import {execFile} from 'node:child_process';
import {promisify,parseArgs} from 'node:util';
import {ROOT,aliasName,identifier,loadAccount,lockAccount,readJSON,writeJSON,operationFiles,makePlan,hash,markDispatch,fail} from './core.mjs';
import {startBridge} from './bridge.mjs';
import {openBrowser,browserIdentity} from './browser.mjs';
import {cloudTarget,requireWrite} from './cloud.mjs';
import {privateTempDir} from './temporary.mjs';
import {paragraphSnapshot,paragraphMode,verifyParagraphs,validateParagraphs,validateResolutionTargets} from './paragraph-core.mjs';
const exec=promisify(execFile),emit=x=>process.stdout.write(JSON.stringify(x,null,2)+'\n');
let browser,bridge,release,journal;
try {
  const {positionals:[command,alias,...rest],values:o}=parseArgs({allowPositionals:true,options:{drive:{type:'string'},item:{type:'string'},spec:{type:'string'},plan:{type:'string'},hash:{type:'string'},execute:{type:'boolean'}}});
  const allowed={preview:['drive','item','spec'],apply:['plan','hash','execute'],verify:['plan']};
  if(rest.length||!allowed[command]||Object.keys(o).some(k=>!allowed[command].includes(k)))fail('invalid_arguments','Use paragraphs preview ALIAS --drive ID --item ID --spec JSON; apply ALIAS --plan ID --hash HASH --execute; verify ALIAS --plan ID.');
  const account=loadAccount(aliasName(alias));release=lockAccount(account);
  let plan,target,profile,spec,files;
  if(command==='preview') {spec=validateParagraphs(readJSON(o.spec));({target,profile}=await cloudTarget(alias,identifier(o.drive),identifier(o.item)));}
  else {
    files=operationFiles(account,o.plan);plan=readJSON(files.plan);const {hash:digest,...content}=plan;
    if(digest!==hash(content)||plan.kind!=='word-paragraphs-v1'||plan.target.alias!==alias||(command==='apply'&&o.hash!==digest))fail('preview_mismatch','Stored preview mismatch.');
    spec=validateParagraphs(plan.spec);({target,profile}=await cloudTarget(alias,plan.target.drive,plan.target.item));
    if(JSON.stringify(target)!==JSON.stringify(plan.target))fail('target_mismatch','Document identity or location changed.');
  }
  async function snapshot() {
    const dir=privateTempDir('agent-hands-word-readback-');
    try {const file=path.join(dir,'saved.docx');await exec('bash',[path.join(ROOT,'use-microsoft-files/scripts/files'),'download',alias,target.item,'--drive',target.drive,'--out',file],{timeout:120000,maxBuffer:1000000});return paragraphSnapshot(fs.readFileSync(file));}
    finally {fs.rmSync(dir,{recursive:true,force:true});}
  }
  if(command==='verify') {const result=verifyParagraphs(plan.savedBefore,await snapshot(),spec,plan.mode);emit(result);if(result.status!=='saved_paragraphs_verified')process.exitCode=1;}
  else {
    if(command==='apply') {if(!o.execute)fail('execute_required','Use --execute.');if(fs.existsSync(files.journal))fail('already_dispatched','Use verify; never replay.');await requireWrite(alias);}
    bridge=await startBridge(account,target);browser=await openBrowser(account,target,true,bridge);await browserIdentity(browser.context,target,profile);await bridge.waitReady();
    const read=await bridge.command('read');if(read.status!=='read_ok')fail('read_failed','Word did not return document paragraphs.');
    const baseline=await snapshot(),mode=paragraphMode(baseline,read.paragraphs);
    validateResolutionTargets(baseline,spec);
    const ready=await bridge.command('paragraphs-inspect',{before:read.paragraphs,spec});if(ready.status!=='paragraphs_ready')fail('edit_refused',ready.code||'Paragraph changes are unsupported.');
    if(command==='preview') {
      plan={...makePlan(target,{}),kind:'word-paragraphs-v1',spec,before:read.paragraphs,savedBefore:baseline,mode};const {hash:unused,...content}=plan;plan.hash=hash(content);writeJSON(operationFiles(account,plan.id).plan,plan,true);
      emit({status:'preview',operation:plan.id,hash:plan.hash,name:target.name,edits:spec.paragraphs.filter(x=>x.after!==undefined),formatCount:spec.paragraphs.filter(x=>x.format).length,links:spec.links,append:spec.append,resolveComments:spec.resolveComments||[],limitation:'Same-paragraph edits can race the final check. Saved verification and visual acceptance remain required.'});
    } else {
      if(hash(baseline)!==hash(plan.savedBefore)||JSON.stringify(read.paragraphs)!==JSON.stringify(plan.before))fail('stale_preview','Document changed after preview.');
      await browserIdentity(browser.context,target,profile);journal=files.journal;
      const result=await bridge.command('paragraphs-apply',{before:plan.before,spec},()=>markDispatch(journal,plan));
      await browser.context.close();browser=null;await bridge.close();bridge=null;
      let check={status:'saved_paragraphs_unverified'};
      if(result.status!=='refused_before_mutation')for(let i=0;i<5;i++){check=verifyParagraphs(plan.savedBefore,await snapshot(),spec,plan.mode);if(check.status==='saved_paragraphs_verified')break;await new Promise(r=>setTimeout(r,2000));}
      const outcome={operation:plan.id,...check,sessionStatus:result.status,code:result.code};writeJSON(journal,outcome);emit(outcome);if(check.status!=='saved_paragraphs_verified')process.exitCode=1;
    }
  }
}catch(e){emit({status:journal&&fs.existsSync(journal)?'uncertain_after_dispatch':e.code||'failed',detail:e.code?e.message:'Paragraph operation failed; inspect its retained state before retrying.'});process.exitCode=1;}
finally{try{if(browser)await browser.context.close();}finally{if(bridge)await bridge.close();release?.();}}
