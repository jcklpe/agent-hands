import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import {initialize,launchOwnedBrowser,launchOptions} from '../../use-word-documents/scripts/browser.mjs';
import {startBridge} from '../scripts/bridge.mjs';
import {previewShapes} from '../scripts/core.mjs';

test('real headless PowerPoint bridge edits only the selected shape and leaves another browser alone',async()=>{
 const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'powerpoint-browser-'))), listener=net.createServer();
 await new Promise(r=>listener.listen(0,'127.0.0.1',r));const port=listener.address().port;await new Promise(r=>listener.close(r));
 const account=await initialize('demo',port,root), sentinelAccount=await initialize('sentinel',port,root);
 const target={origin:'https://example.sharepoint.com',canonicalPath:'/sites/demo/Test.pptx',pathname:'/sites/demo/Test.pptx',guid:''};
 const bridge=await startBridge(account,target);let context,sentinel;
 try{
  const launch=launchOptions(account);assert.equal(launch.chromiumSandbox,true);assert.ok(launch.ignoreDefaultArgs.includes('--password-store=basic'));
  sentinel=await launchOwnedBrowser(sentinelAccount);const untouched=await sentinel.newPage();await untouched.goto('data:text/html,<title>Unrelated tabs</title>');
  context=await launchOwnedBrowser(account,true,bridge);
  await context.route('https://appsforoffice.microsoft.com/**',r=>r.fulfill({contentType:'text/javascript',body:''}));
  await context.addInitScript(target=>{
   const f=window.fixture={texts:['Target old text.','Other editor text.'],mutations:0,failSync:false,settings:{}};
   const shapes=f.texts.map((_,i)=>({id:String(i+1),name:'Shape '+i,type:'TextBox',textFrame:{textRange:{load(){},get text(){return f.texts[i];},getSubstring(start,length){return {set text(value){f.texts[i]=f.texts[i].slice(0,start)+value+f.texts[i].slice(start+length);f.mutations++;}};}}}}));
   window.Office={onReady:async()=>{},AsyncResultStatus:{Succeeded:'ok'},DocumentMode:{ReadWrite:'readWrite'},context:{host:'PowerPoint',platform:'OfficeOnline',requirements:{isSetSupported:()=>true},document:{mode:'readWrite',getFilePropertiesAsync:cb=>cb({status:'ok',value:{url:target.origin+target.pathname}}),settings:{get:k=>f.settings[k],set:(k,v)=>f.settings[k]=v,saveAsync:cb=>cb({status:'ok'}),refreshAsync:cb=>cb({status:'ok'})}}}};
   window.PowerPoint={ShapeType:{textBox:'TextBox',geometricShape:'GeometricShape'},run:async cb=>cb({presentation:{slides:{load(){},items:[{id:'256#1',shapes:{load(){},items:shapes}}]}},sync:async()=>{if(f.failSync&&f.mutations>1)throw new Error('Lost reply');}})};
  },target);
  const page=await context.newPage();await page.goto(bridge.origin+bridge.prefix+'index.html?et=');await bridge.waitReady(5000);
  assert.equal((await bridge.command('enable-startup')).status,'startup_saved');
  const read=await bridge.command('read');const edit=previewShapes(read.shapes,'256#1','1','old','new');
  await page.evaluate(()=>{fixture.texts[1]='Other editor changed text.';});
  assert.equal((await bridge.command('replace',{edit})).status,'session_text_verified');
  assert.deepEqual(await page.evaluate(()=>fixture.texts),['Target new text.','Other editor changed text.']);
  assert.equal((await bridge.command('replace',{edit})).code,'stale_preview');assert.equal(await page.evaluate(()=>fixture.mutations),1);
  const next=previewShapes((await bridge.command('read')).shapes,'256#1','1','new','later');
  await page.evaluate(()=>{fixture.failSync=true;});
  assert.equal((await bridge.command('replace',{edit:next})).status,'uncertain_after_dispatch');assert.equal(await page.evaluate(()=>fixture.mutations),2);
  await context.close();context=null;assert.equal(await untouched.title(),'Unrelated tabs');
 }finally{if(context)await context.close();if(sentinel)await sentinel.close();await bridge.close();fs.rmSync(root,{recursive:true,force:true});}
});
