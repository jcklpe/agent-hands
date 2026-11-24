#!/usr/bin/env node
import {requireWrite} from '../../use-word-documents/scripts/cloud.mjs';
import fs from 'node:fs';
import path from 'node:path';
import readline from 'node:readline';
import {parseArgs,promisify} from 'node:util';
import {execFile} from 'node:child_process';
import {ROOT,loadAccount,lockAccount,readJSON,writeJSON,aliasName,privateDir} from '../../use-word-documents/scripts/core.mjs';
import {launchOwnedBrowser} from '../../use-word-documents/scripts/browser.mjs';
import {validateSpec,digest,fail} from './schema.mjs';
import {preview,readPlan,paths,apply as applyPlan} from './plans.mjs';
import {extremePath} from './preview-paths.mjs';
const exec=promisify(execFile), emit=value=>process.stdout.write(JSON.stringify(value)+'\n');
const help='forms apply ALIAS --plan ID --hash SHA256 --execute --allow-form-write\nforms verify ALIAS --plan ID\nforms visual ALIAS --plan ID --out ABSOLUTE_DIRECTORY\nforms validate --spec FILE\nforms preview ALIAS --spec FILE --url EXACT_EMPTY_FORM_DESIGN_URL\nforms author ALIAS --plan ID --hash SHA256 --execute --allow-form-write\nforms status ALIAS --plan ID\nAuthor accepts bounded commands on stdin: inspect, introduce, begin, configure, build-remaining, branch, verify, quit. It never sends invitations or submits responses.';
let context,release;
async function cleanup(){const closing=context,unlock=release;context=null;release=null;try{if(closing)await closing.close();}finally{if(unlock)unlock();}}
const stop=()=>{void cleanup().finally(()=>process.exit(130));};process.once('SIGINT',stop);process.once('SIGTERM',stop);
try{
 const {positionals,values}=parseArgs({allowPositionals:true,strict:true,options:{spec:{type:'string'},url:{type:'string'},plan:{type:'string'},hash:{type:'string'},out:{type:'string'},execute:{type:'boolean'},'allow-form-write':{type:'boolean'},resume:{type:'boolean'},help:{type:'boolean'}}});
 const [command,alias,...rest]=positionals;
 if(values.help||!command)console.log(help);
 else{
  const allowed={validate:['spec'],preview:['spec','url'],apply:['plan','hash','execute','allow-form-write'],author:['plan','hash','execute','allow-form-write','resume'],status:['plan'],verify:['plan'],visual:['plan','out']};
  if(rest.length||!allowed[command]||Object.keys(values).some(k=>!allowed[command].includes(k)))fail('invalid_arguments','Use forms --help.');
  if(command==='validate'){const spec=validateSpec(readJSON(values.spec));emit({status:'valid',hash:digest(spec),title:spec.title,questionCount:spec.questions.length});}
  else{
   const account=loadAccount(aliasName(alias));if(['apply','author'].includes(command))await requireWrite(alias);
   if(command==='status'){const file=paths(account,values.plan);emit(fs.existsSync(file.journal)?readJSON(file.journal):{status:'not_dispatched'});}
   else{
    const profile=JSON.parse((await exec('bash',[path.join(ROOT,'setup-microsoft-services/scripts/authorize'),'profile',alias,'--json'],{timeout:120000,maxBuffer:1000000})).stdout);
    if(command==='preview'){const plan=preview(account,profile,readJSON(values.spec),values.url);emit({status:'preview',operation:plan.id,hash:plan.hash,target:plan.target,account:profile.userPrincipalName,spec:plan.spec});}
    else if(command==='apply'){
     if(!values.execute||!values['allow-form-write'])fail('execute_required','Apply requires --execute and --allow-form-write for the reviewed form.');
     const plan=readPlan(account,values.plan,values.hash);if(plan.change)fail('invalid_plan','Use the subtitle command for this amendment.');
     release=lockAccount(account);context=await launchOwnedBrowser(account,true);let page=await context.newPage();for(const other of context.pages())if(other!==page)await other.close();
     const api=await import('./editor.mjs');
     await page.goto('https://forms.cloud.microsoft/Pages/DesignPageV2.aspx',{waitUntil:'domcontentloaded',timeout:60000});
     const adapter={
      checkIdentity:async()=>api.checkIdentity(page,profile),
      requireNoExistingTitle:async title=>{
       await page.keyboard.press('Escape');await page.getByRole('tab',{name:'My forms',exact:true}).click();await page.getByRole('textbox',{name:'Search box',exact:true}).waitFor();
       await page.waitForFunction(()=>/Displaying \d+ collections and \d+ forms/.test(document.body.innerText),{timeout:30000});
       const names=await page.getByRole('button').evaluateAll(els=>els.map(el=>el.getAttribute('aria-label')||el.innerText));
       if(names.some(name=>name.includes('Open Form of '+title+'. ')))fail('duplicate_title','A displayed form already uses this title. Select its exact target instead of creating another.');
      },
      createForm:async()=>{
       if(plan.target)await page.goto(plan.target,{waitUntil:'domcontentloaded',timeout:60000});
       else{const popup=page.waitForEvent('popup',{timeout:30000});await page.getByRole('button',{name:'Create a new form',exact:true}).click();page=await popup;}
       await page.getByRole('heading',{name:'Form title Untitled form',exact:true}).waitFor({timeout:45000});
       const url=new URL(page.url());if(!url.searchParams.get('id'))fail('created_form_unidentified','The new editor has no exact form ID; inspect Forms before any new creation.');
       await api.checkIdentity(page,profile);
       if(!await page.getByRole('button',{name:'Quick start with',exact:true}).isVisible())fail('not_empty','The selected draft is not empty. No existing questions will be overwritten.');
       return {url:page.url()};
      },
      closeResponses:async()=>{await page.getByRole('button',{name:'Settings',exact:true}).click();await page.getByRole('checkbox',{name:'Options for responses Accept responses',exact:true}).uncheck();await page.getByRole('button',{name:'Settings Close',exact:true}).click();await api.saved(page);},
      setIntroduction:async()=>api.introduction(page,plan.spec),
      addQuestion:async question=>{await api.beginQuestion(page,question);await api.configureQuestion(page,question);},
      setBranching:async questions=>api.setBranching(page,questions),
      reopenAndRead:async target=>{await page.goto(target.url,{waitUntil:'domcontentloaded',timeout:60000});await api.checkIdentity(page,profile);return api.verifyForm(page,plan.spec);},
      verify:async(spec,result)=>{if(result.status!=='form_verified')fail('form_unverified','Saved form readback failed.');}
     };
     const result=await applyPlan(account,plan,profile,adapter);emit(result);if(result.status!=='form_verified')process.exitCode=1;
    }
    else if(command==='verify'||command==='visual'){
     const prior=readJSON(paths(account,values.plan).plan),plan=readPlan(account,values.plan,prior.hash);
     if(profile.id!==plan.accountId)fail('account_mismatch','The selected account differs from preview.');
     release=lockAccount(account);context=await launchOwnedBrowser(account,true);const page=await context.newPage();for(const other of context.pages())if(other!==page)await other.close();
     const journal=paths(account,plan.id).journal;const stored=fs.existsSync(journal)?readJSON(journal):null;const target=plan.target??stored?.target?.url;
     if(!target)fail('target_unverified','There is no identified saved form. Inspect the retained creation receipt.');
     await page.goto(target,{waitUntil:'domcontentloaded',timeout:60000});const api=await import('./editor.mjs');await api.checkIdentity(page,profile);const result=await api.verifyForm(page,plan.spec);
     if(command==='visual'){
      if(!values.out||!path.isAbsolute(values.out))fail('output_required','Choose an absolute private output directory.');privateDir(values.out);
      await page.getByRole('button',{name:'Preview',exact:true}).click();await page.getByRole('button',{name:'Back',exact:true}).waitFor();
      await page.screenshot({path:path.join(values.out,'desktop.png'),fullPage:true});
      await page.getByRole('tab',{name:'Mobile View',exact:true}).click();await page.screenshot({path:path.join(values.out,'mobile.png'),fullPage:true});
      await page.getByRole('tab',{name:'Computer View',exact:true}).click();
      const checks=[];
      const questionName=index=>new RegExp('^\\d+\\. '+plan.spec.questions[index].title.replace(/[.*+?^${}()|[\]\\]/g,'\\$&'));
      const heading=index=>page.getByRole('heading',{name:questionName(index)});
      for(const mode of ['more','fewer']){
       const route=extremePath(plan.spec,mode);
       for(const choice of route.choices){
        const question=plan.spec.questions[choice.index],group=page.getByRole(question.multiple?'group':'radiogroup',{name:questionName(choice.index)});
        const checkbox=group.getByRole('checkbox',{name:choice.option,exact:true});const control=await checkbox.count()?checkbox:group.getByRole('radio',{name:choice.option,exact:true});await control.click();
        if(choice.targetIndex<plan.spec.questions.length)await heading(choice.targetIndex).waitFor();
       }
       for(let i=0;i<plan.spec.questions.length;i++)if(await heading(i).isVisible()!==route.visited.includes(i))fail('preview_path_unverified','Question '+(i+1)+' visibility differs on the '+mode+' preview path. No response was submitted.');
       checks.push({path:mode,visibleQuestionCount:route.visited.length,branchChoices:route.choices.length,passed:true});
       await page.screenshot({path:path.join(values.out,mode+'-followups.png'),fullPage:true});
      }
      writeJSON(path.join(values.out,'preview-checks.json'),{checks,responseSubmitted:false});
      emit({status:'preview_checked',output:values.out,checks,responseSubmitted:false});
     }
     const file=paths(account,plan.id).journal;if(fs.existsSync(file)){const state=readJSON(file);state.status='form_verified';state.verification=result;state.verified=new Date().toISOString();writeJSON(file,state);}
     emit({...result,operation:plan.id,target});
    }
    else{
     if(!values.execute||!values['allow-form-write'])fail('execute_required','Author requires --execute and --allow-form-write after authorization of this target and content.');
     const plan=readPlan(account,values.plan,values.hash);if(profile.id!==plan.accountId)fail('account_mismatch','The Microsoft account differs from preview.');
     if(plan.change)fail('invalid_plan','Use forms-subtitle apply for a subtitle amendment, not the empty-form author command.');
     const files=paths(account,plan.id);
     if(fs.existsSync(files.journal)&&!values.resume)fail('already_dispatched','Inspect the existing operation; use explicit --resume only after readback reconciliation.');
     if(!plan.target)fail('target_required','This initial surface populates an explicitly selected empty draft; supply its exact design URL in preview.');
     release=lockAccount(account);context=await launchOwnedBrowser(account,true);
     const page=await context.newPage();for(const other of context.pages())if(other!==page)await other.close();
     await page.goto(plan.target,{waitUntil:'domcontentloaded',timeout:60000});
     const editor=async()=>import('./editor.mjs');
     await (await editor()).checkIdentity(page,profile);
     const state=fs.existsSync(files.journal)?readJSON(files.journal):{kind:'forms-author-v1',operation:plan.id,hash:plan.hash,target:plan.target,status:'ready',introduced:false,completed:0,active:null,steps:[]};
     if(values.resume){
      if(state.hash!==plan.hash||state.target!==plan.target||state.completed!==0||state.active!==null)fail('resume_unverified','This initial resume supports only a complete introduction with zero questions. Inspect other partial results separately.');
      let actual=await (await editor()).readIntroduction(page);
      if(actual.title===plan.spec.title&&actual.description===''&&actual.acceptResponses===false&&await page.getByRole('button',{name:'Quick start with',exact:true}).isVisible()){
       const step={name:'complete empty description',status:'dispatched',time:new Date().toISOString()};state.steps.push(step);writeJSON(files.journal,state);
       await (await editor()).completeDescription(page,plan.spec.description);actual=await (await editor()).readIntroduction(page);step.status='returned';writeJSON(files.journal,state);
      }
      emit({status:'introduction_readback',actual,empty:await page.getByRole('button',{name:'Quick start with',exact:true}).isVisible()});
      const descriptionText=value=>value.replace(/\r\n/g,'\n').replace(/\n+/g,'\n').replace(/\u00a0/g,' ').trim();
      if(actual.title!==plan.spec.title||descriptionText(actual.description)!==descriptionText(plan.spec.description)||actual.acceptResponses!==false||!await page.getByRole('button',{name:'Quick start with',exact:true}).isVisible())fail('resume_unverified','The saved introduction and empty form do not match the preview. No mutation was replayed.');
      state.introduced=true;state.status='introduction_reconciled';state.reconciled=new Date().toISOString();writeJSON(files.journal,state);
     }else writeJSON(files.journal,state,true);
     const mutation=async(name,fn)=>{const step={name,status:'dispatched',time:new Date().toISOString()};state.steps.push(step);state.status='uncertain_after_dispatch';writeJSON(files.journal,state);try{await fn();step.status='returned';state.status='authoring';writeJSON(files.journal,state);}catch(error){step.code=error.code||'ui_error';writeJSON(files.journal,state);throw error;}};
     const execute=async action=>{
      const api=await editor();
      if(action==='inspect')return api.inspect(page);
      if(action==='introduce'){
       if(state.introduced||state.steps.length)fail('already_dispatched','Introduction was already attempted. Inspect the draft before another operation.');
       await mutation('introduction',()=>api.introduction(page,plan.spec));state.introduced=true;writeJSON(files.journal,state);return {status:'introduction_saved'};
      }
      if(action==='begin'){
       if(!state.introduced||state.active!==null||state.completed>=plan.spec.questions.length)fail('invalid_stage','There is no next unstarted question at this stage.');
       state.active=state.completed;writeJSON(files.journal,state);await mutation('begin '+plan.spec.questions[state.active].id,()=>api.beginQuestion(page,plan.spec.questions[state.active]));return {status:'question_started',question:plan.spec.questions[state.active]};
      }
      if(action==='configure'){
       if(state.active===null)fail('invalid_stage','Start the next question first.');
       await mutation('configure '+plan.spec.questions[state.active].id,()=>api.configureQuestion(page,plan.spec.questions[state.active]));state.completed++;state.active=null;writeJSON(files.journal,state);return {status:'question_saved',completed:state.completed};
      }
      if(action==='build-remaining'){
       while(state.completed<plan.spec.questions.length){if(state.active===null)await execute('begin');await execute('configure');}return {status:'questions_saved',completed:state.completed};
      }
      if(action==='branch'){
       if(state.active!==null||state.completed!==plan.spec.questions.length)fail('invalid_stage','Finish all questions before branching.');await mutation('branching',()=>api.setBranching(page,plan.spec.questions));return {status:'branching_saved'};
      }
      if(action==='verify')return api.verifyForm(page,plan.spec);
      fail('invalid_command','Use inspect, introduce, begin, configure, build-remaining, branch, verify or quit.');
     };
     emit({status:'author_ready',operation:plan.id,target:plan.target});
     const input=readline.createInterface({input:process.stdin,crlfDelay:Infinity});
     for await(const line of input){const action=line.trim();if(!action)continue;if(action==='quit'){emit({status:'author_closed',completed:state.completed,active:state.active});break;}try{emit(await execute(action));}catch(error){emit({status:error.code||'ui_error',detail:/^[a-z][a-z_]+$/.test(error.code||'')?error.message:'The UI step failed; inspect its recorded state before another write.',completed:state.completed,active:state.active});}}
    }
   }
  }
 }
}catch(error){emit({status:error.code||'failed',detail:String(error.message).replace(/https?:\/\/[^\s]+/g,'[url]').slice(0,600)});process.exitCode=1;}
finally{await cleanup();process.removeListener('SIGINT',stop);process.removeListener('SIGTERM',stop);}
