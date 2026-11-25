import {sameDocument,fail,sleep} from './core.mjs';
// Open an already installed command only; no sideload or startup setting is changed here.
export async function openInstalledAddin(browser,bridge,target){
 const guard=()=>{if(!sameDocument(browser.page.url(),target))fail('target_mismatch','Workbook identity changed during add-in setup.');};
 guard();
 try{await bridge.waitReady(1000);return;}catch(e){if(e.code!=='addin_setup_required')throw e;}
 await browser.page.setViewportSize({width:1800,height:1000});
 let frame;
 for(let i=0;i<80;i++){
  frame=browser.page.frames().find(f=>/^WacFrame_Excel_\d+$/.test(f.name())&&(()=>{try{return new URL(f.url()).hostname.endsWith('.officeapps.live.com')}catch{return false}})());
  if(frame&&await frame.getByRole('tab',{name:'Home',exact:true}).isVisible())break;
  await sleep(250);
 }
 if(!frame)fail('addin_setup_required','Excel editor did not load.');
 guard();await frame.getByRole('tab',{name:'Insert',exact:true}).click();
 guard();await frame.getByRole('tab',{name:'Home',exact:true}).click();
 try{await frame.getByRole('group',{name:'Agent Hands',exact:true}).waitFor({state:'attached',timeout:20000});}catch{fail('addin_setup_required','The installed Excel bridge group is unavailable. Configure this workbook before editing.');}
 const button=frame.getByRole('button',{name:'Open Excel tools',exact:true});
 if(await button.isVisible()){guard();await button.click();return;}
 const more=frame.getByRole('button',{name:'More Options',exact:true});
 if(await more.isVisible()){
  guard();await more.click();
  const item=frame.getByRole('menuitem',{name:'Open Excel tools',exact:true});
  try{await item.waitFor({state:'visible',timeout:3000});}catch{}
  if(await item.isVisible()){guard();await item.click();return;}
  await more.press('Escape');
 }
 fail('addin_setup_required','The Excel bridge is not installed or its command is unavailable. Configure the selected workbook; no content was edited.');
}
