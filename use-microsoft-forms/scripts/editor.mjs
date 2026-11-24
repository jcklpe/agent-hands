import {fail} from './schema.mjs';
export async function checkIdentity(page,profile){
 const name='Account manager for '+profile.displayName;
 const button=page.getByRole('button',{name,exact:true});await button.waitFor({timeout:45000});
 const dialog=page.getByRole('dialog',{name,exact:true});
 for(let i=0;i<5&&!await dialog.isVisible();i++){await button.click();await dialog.waitFor({timeout:3000}).catch(()=>{});}
 if(!await dialog.isVisible())fail('account_menu_unavailable','The Microsoft account menu did not open. No form mutation was sent.');
 const words=(await dialog.innerText()).toLowerCase().split(/\s+/);
 if(![profile.mail,profile.userPrincipalName].filter(Boolean).some(v=>words.includes(v.toLowerCase())))fail('account_mismatch','Forms account menu does not match the selected Microsoft account.');
 await dialog.getByRole('button',{name,exact:true}).click();await dialog.waitFor({state:'hidden'});
}
export async function saved(page){await page.waitForFunction(()=>document.querySelector('[data-automation-id="savingStatus"]')?.innerText.includes('Saved'),{timeout:30000});}
export async function readIntroduction(page){
 const title=page.getByRole('textbox',{name:'Form title',exact:true});
 if(!await title.isVisible())await page.getByRole('heading',{level:1}).getByRole('button',{name:/^Form title /}).click();
 const value=locator=>locator.evaluate(el=>'value' in el?el.value:el.innerText);
 const result={title:await value(title),description:await value(page.getByRole('textbox',{name:'Form description',exact:true}))};
 await page.getByRole('button',{name:'Settings',exact:true}).click();result.acceptResponses=await page.getByRole('checkbox',{name:'Options for responses Accept responses',exact:true}).isChecked();await page.getByRole('button',{name:'Settings Close',exact:true}).click();
 return result;
}
export async function introduction(page,spec){
 await page.getByRole('heading',{name:'Form title Untitled form',exact:true}).waitFor();
 if(!await page.getByRole('button',{name:'Quick start with',exact:true}).isVisible())fail('not_empty','Only an empty untitled form may be populated.');
 await page.getByRole('button',{name:'Settings',exact:true}).click();
 await page.getByRole('checkbox',{name:'Options for responses Accept responses',exact:true}).uncheck();
 await page.getByRole('button',{name:'Settings Close',exact:true}).click();await saved(page);
 await page.getByRole('heading',{name:'Form title Untitled form',exact:true}).getByRole('button').click();
 await page.getByRole('textbox',{name:'Form title',exact:true}).fill(spec.title);
 await page.getByRole('textbox',{name:'Form description',exact:true}).click();
 await page.getByRole('textbox',{name:'Form description',exact:true}).fill(spec.description);
 await page.getByRole('button',{name:'Style',exact:true}).focus();await page.keyboard.press('Tab');await saved(page);
}
export async function completeDescription(page,description){
 const box=page.getByRole('textbox',{name:'Form description',exact:true});
 if(!await box.isVisible())await page.getByRole('heading',{level:1}).getByRole('button',{name:/^Form title /}).click();
 await box.click();await box.fill(description);await page.getByRole('button',{name:'Settings',exact:true}).click();await page.getByRole('button',{name:'Settings Close',exact:true}).click();await saved(page);
}
export async function beginQuestion(page,question){
 const first=page.getByRole('button',{name:'Quick start with',exact:true});
 if(await first.isVisible())await first.click();
 else await page.getByRole('button',{name:'Add new question',exact:true}).click();
 await page.getByRole('button',{name:{text:'Text',choice:'Choice',date:'Date'}[question.type],exact:true}).click();
}
async function setSwitch(page,name,value){
 const control=page.getByRole('switch',{name,exact:true});const current=await control.getAttribute('aria-checked');
 if(!['true','false'].includes(current))fail('switch_unverified','The '+name+' switch has no verified state.');
 if((current==='true')!==value)await control.click();
}
export async function configureQuestion(page,question){
 try{
 if(await page.getByRole('menu').count())await page.keyboard.press('Escape');
 const title=page.getByRole('textbox',{name:/^Question title /});
 if(await title.count()===0)await page.locator('[data-automation-id="questionWrapper"]').last().click();
 await title.waitFor();
 if(await title.count()!==1)fail('question_unverified','Select exactly one question editor.');
 const current=await title.innerText();if(current!=='Question'&&current!==question.title)fail('stale_question','The active question contains unexpected wording; no overwrite was sent.');
 await title.click();await title.fill(question.title);
 await setSwitch(page,'Required',question.required);
 if(question.type==='text')await setSwitch(page,'Long answer',!!question.longAnswer);
 if(question.description){
  await page.getByRole('button',{name:'More settings for question',exact:true}).click();
  const subtitle=page.getByRole('menuitemcheckbox',{name:'Subtitle',exact:true});
  if(await subtitle.getAttribute('aria-checked')!=='true')await subtitle.click();else await page.keyboard.press('Escape');
  const input=page.getByRole('textbox',{name:/subtitle/i});
  if(await input.count()!==1)fail('subtitle_controls_unverified','Inspect the newly enabled subtitle field before filling it.');
  await input.click();await input.fill(question.description);
 }
 if(question.type==='choice'){
  await setSwitch(page,'Multiple answers',!!question.multiple);
  const options=page.getByRole('textbox',{name:'Choice Option Text Please enter a name for this option.',exact:true});
  if(await options.count()>question.options.length)fail('unexpected_options','The active choice question has extra options. No option was deleted.');
  while(await options.count()<question.options.length)await page.getByRole('button',{name:'Add option',exact:true}).click();
  for(let i=0;i<question.options.length;i++){
   const field=options.nth(i),value=await field.innerText();
   if(value!==question.options[i]&&!/^Option \d+$/.test(value)&&value!=='')fail('unexpected_option','An existing choice option has unexpected text. No overwrite was sent.');
   if(value!==question.options[i]){await field.click();await field.fill(question.options[i]);}
  }
 }
 await saved(page);
 }catch(error){if(!error.code){error.code='ui_step_failed';error.message=String(error.message).replace(/https?:\/\/[^\s]+/g,'[url]').slice(0,600);}throw error;}
}
export async function setBranching(page,questions){
 try{
 const first=questions.findIndex(q=>q.branches||q.next);
 if(first<0)return;
 if(await page.getByRole('heading',{name:'Branching options',exact:true}).isVisible())return await applyBranchDestinations(page,questions);
 const cards=page.locator('[data-automation-id="questionWrapper"], [data-automation-id="questionDesignerCard"]');
 if(await cards.count()!==questions.length)fail('question_count_mismatch','The editor question count differs from the specification.');
 const card=cards.nth(first);if(await card.getAttribute('data-automation-id')==='questionWrapper')await card.click();
 const title=await page.getByRole('textbox',{name:/^Question title /}).innerText();if(title!==questions[first].title)fail('question_mismatch','The selected branching question is not the expected one.');
 const branch=page.getByRole('menuitemcheckbox',{name:'Add branching',exact:true});
 if(!await branch.isVisible())await page.getByRole('button',{name:'More settings for question',exact:true}).click();
 await branch.focus();await branch.press('Enter');
 await page.getByRole('heading',{name:'Branching options',exact:true}).waitFor();
 return await applyBranchDestinations(page,questions);
 }catch(error){if(!error.code){error.code='branch_ui_failed';error.message=String(error.message).replace(/https?:\/\/[^\s]+/g,'[url]').slice(0,600);}throw error;}
}
export async function openBranching(page,questions){
 if(await page.getByRole('heading',{name:'Branching options',exact:true}).isVisible())return;
 const first=questions.findIndex(q=>q.branches||q.next);if(first<0)return;
 const cards=page.locator('[data-automation-id="questionWrapper"], [data-automation-id="questionDesignerCard"]');
 if(await cards.count()!==questions.length)fail('question_count_mismatch','The saved question count differs from the specification.');
 const card=cards.nth(first);if(await card.getAttribute('data-automation-id')==='questionWrapper')await card.click();
 await page.getByRole('button',{name:'More settings for question',exact:true}).click();
 const menu=page.getByRole('menuitemcheckbox',{name:'Add branching',exact:true});await menu.focus();await menu.press('Enter');
 await page.getByRole('heading',{name:'Branching options',exact:true}).waitFor();
}
export const normalized=value=>String(value).replace(/\s+/g,' ').trim();
export function expectedLabel(question,index){
 const type=question.type==='text'?(question.longAnswer?'Multi Line Text':'Single line text'):question.type==='choice'?(question.multiple?'Multiple choice':'Single choice'):'Date';
 return normalized((index+1)+'. Question title '+question.title+(question.description?' Question subtitle '+question.description:'')+' '+type+(question.required?' Required to answer':''));
}
export function branchLabel(questions,index,target){
 const position=questions.findIndex(q=>q.id===target);
 if(target==='end')return 'End of the form';
 if(position<0||position<=index)fail('invalid_branch','A saved branch target must be a later question or end.');
 return position===index+1?'Next':(position+1)+'. '+questions[position].title;
}
export function compareForm(spec,actual){
 if(actual.introduction.title!==spec.title||normalized(actual.introduction.description)!==normalized(spec.description)||actual.introduction.acceptResponses!==false)fail('introduction_unverified','Saved title, description or closed-response setting differs.');
 if(actual.questions.length!==spec.questions.length)fail('question_count_mismatch','Saved question count differs.');
 spec.questions.forEach((question,index)=>{
  const saved=actual.questions[index];
  if(normalized(saved.label)!==expectedLabel(question,index))fail('question_unverified','Saved question '+(index+1)+' differs in wording, subtitle, type or required state.');
  if(question.type==='choice'&&JSON.stringify(saved.options.map(normalized))!==JSON.stringify(question.options.map(normalized)))fail('options_unverified','Saved choices for question '+(index+1)+' differ in wording or order.');
 });
}
export async function verifyForm(page,spec){
 const intro=await readIntroduction(page);
 const questions=await page.locator('[data-automation-id="questionWrapper"]').evaluateAll(elements=>elements.map(el=>({label:el.getAttribute('aria-label'),options:[...el.querySelectorAll('[data-automation-id="questionChoiceOptionContainer"]')].map(v=>v.innerText)})));
 const actual={introduction:intro,questions};compareForm(spec,actual);
 let verifiedBranches=0;
 if(spec.questions.some(q=>q.branches||q.next)){
  await openBranching(page,spec.questions);
  for(let index=0;index<spec.questions.length;index++){
   const q=spec.questions[index];if(!q.branches&&!q.next)continue;
   const group=page.getByRole('radiogroup',{name:(index+1)+'. '+q.title,exact:true});
   if(!await group.isVisible()){const button=page.getByRole('button',{name:(index+1)+'. '+q.title+' Single choice'+(q.required?' Required to answer':''),exact:true});await button.focus();await button.press('Enter');await group.waitFor();}
   const rows=group.getByRole('radio');if(await rows.count()!==q.options.length)fail('branch_unverified','Branch option count differs.');
   for(let i=0;i<q.options.length;i++){
    const row=rows.nth(i),target=q.branches?.[q.options[i]]??q.next??spec.questions[index+1]?.id??'end';
    if(!normalized(await row.innerText()).startsWith(normalized(q.options[i])+' Go to '))fail('branch_unverified','Branch source option differs.');
    if(normalized(await row.getByRole('button').innerText())!==normalized(branchLabel(spec.questions,index,target)))fail('branch_unverified','Saved destination differs for question '+(index+1)+', option '+q.options[i]);
    verifiedBranches++;
   }
  }
  await page.getByRole('button',{name:'Back',exact:true}).click();
 }
 return {status:'form_verified',title:intro.title,questionCount:questions.length,verifiedBranches,acceptResponses:false};
}
export async function applyBranchDestinations(page,questions){
 for(let index=0;index<questions.length;index++){
  const question=questions[index];if(!question.branches&&!question.next)continue;
  if(question.type!=='choice'||question.multiple)fail('unsupported_branch','This editor currently supports single-choice answer branches only.');
  const group=page.getByRole('radiogroup',{name:(index+1)+'. '+question.title,exact:true});
  if(!await group.isVisible()){
   const button=page.getByRole('button',{name:(index+1)+'. '+question.title+' Single choice'+(question.required?' Required to answer':''),exact:true});
   await button.focus();await button.press('Enter');await group.waitFor();
  }
  const rows=group.getByRole('radio');if(await rows.count()!==question.options.length)fail('option_count_mismatch','Branching options differ from the specification.');
  for(let i=0;i<question.options.length;i++){
   const row=rows.nth(i),text=await row.innerText();if(!text.startsWith(question.options[i]))fail('option_mismatch','A branch option has unexpected wording.');
   const target=question.branches?.[question.options[i]]??question.next??questions[index+1]?.id??'end';
   const position=questions.findIndex(q=>q.id===target);
   const label=target==='end'?'End of the form':position===index+1?'Next':(position+1)+'. '+questions[position].title;
   const button=row.getByRole('button');if((await button.innerText()).trim()===label)continue;
   if(await button.getAttribute('aria-expanded')!=='true')await button.click();
   await row.getByRole('option',{name:label,exact:true}).click({timeout:5000});
   if((await button.innerText()).trim()!==label)fail('branch_unverified','The branch dropdown did not retain the requested destination.');
  }
 }
 await saved(page);await page.getByRole('button',{name:'Back',exact:true}).click();await saved(page);
}
export async function inspect(page){
 return {url:page.url(),ui:(await page.locator('body').ariaSnapshot()).replace(/https?:\/\/[^\s\n]+/g,'[link omitted]'),textboxes:await page.getByRole('textbox').evaluateAll(elements=>elements.map(el=>({label:el.getAttribute('aria-label'),tag:el.tagName,value:'value' in el?el.value:el.innerText}))),controls:await page.locator('[data-automation-id]').evaluateAll(elements=>elements.map(el=>({id:el.getAttribute('data-automation-id'),tag:el.tagName,role:el.getAttribute('role'),label:el.getAttribute('aria-label')})).slice(0,100))};
}
