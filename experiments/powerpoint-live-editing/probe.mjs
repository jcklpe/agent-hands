import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {randomUUID,randomBytes} from 'node:crypto';
import {ROOT,loadAccount,lockAccount,readJSON,writeJSON,privateDir,fail,sleep,hash,sameDocument} from '../../use-word-documents/scripts/core.mjs';
import {openBrowser,browserIdentity} from '../../use-word-documents/scripts/browser.mjs';
import {requireWrite} from '../../use-word-documents/scripts/cloud.mjs';
import {startBridge,manifest} from './bridge.mjs';
import {openAddinAutomatically} from './bootstrap.mjs';

const here=path.dirname(fileURLToPath(import.meta.url)), state=path.join(here,'state'), exec=promisify(execFile);
const emit=value=>console.log(JSON.stringify(value));
async function provider(script,args,json=true) {
  try {const r=await exec('bash',[path.join(ROOT,script),...args],{timeout:120000,maxBuffer:2000000});return json?JSON.parse(r.stdout):r.stdout;}
  catch {fail('provider_failed','The bounded Microsoft provider command failed. No mutation was retried.');}
}
export async function targetFor(test) {
  const meta=await provider('use-microsoft-files/scripts/files',['meta',test.alias,test.item,'--drive',test.drive,'--json']);
  if(meta.id!==test.item||meta.parentReference?.driveId!==test.drive||meta.name!==test.name||!/^Agent Hands PowerPoint coauthoring test \d{4}-\d{2}-\d{2}\.pptx$/.test(meta.name)||!meta.file||meta.size>1000000) fail('target_mismatch','Only the selected small disposable PPTX is permitted.');
  const parent=await provider('use-microsoft-files/scripts/files',['meta',test.alias,meta.parentReference.id,'--drive',test.drive,'--json']);
  const url=new URL(meta.webUrl),folder=new URL(parent.webUrl),guid=(url.searchParams.get('sourcedoc')||'').replace(/[{}]/g,'').toLowerCase();
  if(url.protocol!=='https:'||url.username||url.password||url.port||!/(^|\.)sharepoint\.com$/.test(url.hostname)||parent.id!==meta.parentReference.id||folder.origin!==url.origin||folder.search||folder.hash||folder.username||folder.password||/[\\/]/.test(meta.name)||!/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(guid))fail('unsupported_target','Canonical presentation identity could not be established.');
  const site=url.pathname.match(/^\/(personal|sites|teams)\/[^/]+(?=\/)/)?.[0]||'';
  return {...test,origin:url.origin,pathname:decodeURIComponent(url.pathname),canonicalPath:decodeURIComponent(folder.pathname).replace(/\/$/,'')+'/'+meta.name,guid,webUrl:url.href,identityUrl:`${url.origin}${site}/_api/web/currentuser?$select=Email,LoginName`};
}
async function inspect(browser) {
  await sleep(10000);
  const frames=[];
  for(const frame of browser.page.frames()) {
    let origin;try{const url=new URL(frame.url());if(url.protocol!=='https:')continue;origin=url.origin;}catch{continue;}
    const controls=await frame.locator('[role=tab],button,[role=button]').evaluateAll(nodes=>nodes.slice(0,150).map(n=>({role:n.getAttribute('role')||n.tagName,name:n.getAttribute('aria-label')||n.innerText||'',visible:!!n.getClientRects().length}))).catch(()=>[]);
    frames.push({name:frame.name(),origin,controls});
  }
  writeJSON(path.join(state,'inspection.json'),frames);
  await browser.page.screenshot({path:path.join(state,'owned-editor.png')});
  emit({status:'owned_editor_inspected',frameCount:frames.length});
}
async function main() {
  const [action,flag]=process.argv.slice(2);
  if(!['inspect','inspect-catalog','prepare','read','preview','apply'].includes(action)||(['prepare','apply'].includes(action)?flag!=='--execute':flag!==undefined))fail('invalid_arguments','Use inspect, inspect-catalog, prepare --execute, read, preview or apply --execute.');
  privateDir(state);
  const test=readJSON(path.join(state,'test.json')),base=loadAccount(test.alias);
  const release=lockAccount(base);let browser,bridge;
  const cleanup=async()=>{if(browser){const b=browser;browser=null;await b.context.close();}if(bridge){const b=bridge;bridge=null;await b.close();}release();};
  let stopping=false;
  const stop=()=>{if(!stopping){stopping=true;void cleanup().finally(()=>process.exit(130));}};
  process.once('SIGINT',stop);process.once('SIGTERM',stop);
  try {
    const target=await targetFor(test),profile=await provider('setup-microsoft-services/scripts/authorize',['profile',test.alias,'--json']);
    let extra;
    const settings=path.join(state,'addin-config.json');
    if(fs.existsSync(settings))extra=readJSON(settings);
    else {extra={addinId:randomUUID(),secret:randomBytes(24).toString('hex')};writeJSON(settings,extra,true);}
    const account={...base,...extra};
    if(['prepare','apply'].includes(action))await requireWrite(test.alias);
    if(!action.startsWith('inspect'))bridge=await startBridge(account,target);
    browser=await openBrowser(account,target,true,bridge);
    await browser.page.setViewportSize({width:1600,height:1000});
    await browserIdentity(browser.context,target,profile);
    if(action==='inspect-catalog') {
      let frame;
      for(let attempt=0;attempt<80;attempt++){frame=browser.page.frames().find(f=>/^WacFrame_PowerPoint_\d+$/.test(f.name()));if(frame&&await frame.getByRole('tab',{name:'Home',exact:true}).isVisible())break;await sleep(250);}
      if(!frame||!sameDocument(browser.page.url(),target))fail('target_mismatch','The expected editor is unavailable.');
      await sleep(5000);
      const advanced=frame.getByText('Advanced...',{exact:true});
      const addins=frame.getByRole('button',{name:'Add-ins',exact:true});
      if(!await advanced.isVisible()){await addins.focus();await addins.press('Enter');}
      await sleep(3000);
      writeJSON(path.join(state,'addin-menu.json'),{text:(await frame.locator('body').innerText()).slice(-12000),pages:browser.context.pages().length,button:await addins.evaluate(el=>el.outerHTML)});
      if(await advanced.isVisible())await advanced.click();
    }
    if(action.startsWith('inspect')){await inspect(browser);return;}
    if(action==='prepare') {
      fs.writeFileSync(path.join(state,'manifest.xml'),manifest(account),{mode:0o600});
      const preparation=await openAddinAutomatically(browser,bridge,account,target);
      const ready=await bridge.waitReady();
      const result=ready.automaticStartup?{status:'startup_already_enabled'}:await bridge.command('enable-startup');
      writeJSON(path.join(state,'preparation.json'),{preparation,result});
      emit({preparation,...result});
      if(!['startup_saved','startup_already_enabled'].includes(result.status))fail(result.code||'preparation_failed','The add-in connected but startup was not saved; inspect the private preparation report.');
      await sleep(8000);return;
    }
    await bridge.waitReady();
    const read=await bridge.command('read');
    writeJSON(path.join(state,'latest-read.json'),read);
    if(read.status!=='read_ok')fail(read.code||'read_failed','The PowerPoint read was refused; inspect the private report.');
    if(action==='read'){emit(read);return;}
    if(action==='preview') {
      const candidate=read.shapes.filter(s=>s.name==='ALPHA'&&s.text==='Agent target ALPHA: Original text.');
      if(candidate.length!==1)fail('fixture_changed','The disposable ALPHA baseline is not unique.');
      const s=candidate[0],find='Original text.',replacement='Headless Office.js edit verified.';
      const plan={id:randomUUID(),target,edit:{...s,before:s.text,find,replacement,after:s.text.replace(find,replacement)}};
      writeJSON(path.join(state,'plan.json'),{...plan,hash:hash(plan)},true);emit({status:'preview_ready',before:plan.edit.before,after:plan.edit.after});return;
    }
    const stored=readJSON(path.join(state,'plan.json')),{hash:digest,...plan}=stored;
    if(digest!==hash(plan)||plan.target.item!==target.item||plan.target.drive!==target.drive||plan.target.guid!==target.guid||plan.target.canonicalPath!==target.canonicalPath||!sameDocument(browser.page.url(),target))fail('preview_mismatch','The preview or target changed.');
    const journal=path.join(state,`dispatch-${plan.id}.json`);
    if(fs.existsSync(journal))fail('already_dispatched','Reconcile the saved dispatch; never replay it.');
    const result=await bridge.command('replace',{edit:plan.edit},()=>writeJSON(journal,{id:plan.id,hash:digest,status:'uncertain_after_dispatch'},true));
    writeJSON(journal,{id:plan.id,hash:digest,result});emit(result);
    if(result.status!=='session_text_verified')fail(result.code||'edit_unverified','The edit result is unverified; inspect the dispatch receipt and cloud state before any further mutation.');
    await sleep(10000);
  } catch(error) {
    writeJSON(path.join(state,'last-error.json'),{code:error.code||'probe_error',message:error.message});
    if(browser)await inspect(browser).catch(()=>{});
    throw error;
  } finally {process.removeListener('SIGINT',stop);process.removeListener('SIGTERM',stop);if(!stopping)await cleanup();}
}
if(process.argv[1]===fileURLToPath(import.meta.url))main().catch(error=>{emit({status:'failed',code:error.code||'probe_error',message:error.code?error.message:'Inspect the owned PowerPoint probe without retrying mutations.'});process.exitCode=1;});
