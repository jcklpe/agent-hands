export function validateLinks(items){
 if(!Array.isArray(items)||!items.length||items.length>200)throw Error('Use 1–200 hyperlink targets.');
 const seen=new Set();
 for(const x of items){
  if(!x||Object.keys(x).some(k=>!['sheet','cell','expectedValue','oldAddress','newAddress','restoreText','restoreFont'].includes(k))||typeof x.sheet!=='string'||!x.sheet||x.sheet.length>31||!/^\$?[A-Z]{1,3}\$?[1-9][0-9]{0,6}$/.test(x.cell)||typeof x.expectedValue!=='string')throw Error('Invalid hyperlink target.');
  const restoring=x.restoreText!==undefined; if(restoring && (x.expectedValue!==''||typeof x.restoreText!=='string'||!x.restoreText||!x.restoreFont))throw Error('Restoration requires an empty cell, exact prior text and font.');
  if(!restoring&&(x.restoreText!==undefined||x.restoreFont!==undefined))throw Error('Restoration fields require a missing source link.');
  if(x.restoreFont && (Object.keys(x.restoreFont).some(k=>!['name','size','bold','italic','strikethrough','underline','color'].includes(k))||typeof x.restoreFont.name!=='string'||typeof x.restoreFont.size!=='number'))throw Error('Invalid restoration font.');
  const b=new URL(x.newAddress),a=x.oldAddress===null?b:new URL(x.oldAddress);
  if(a.protocol!=='https:'||b.protocol!=='https:'||a.origin!==b.origin||a.username||b.username||a.password||b.password||x.oldAddress===x.newAddress)throw Error('Use changed HTTPS addresses on the same origin.');
  const key=x.sheet+'!'+x.cell;if(seen.has(key))throw Error('Duplicate target.');seen.add(key);
 }
 return items;
}
export function createLinksAdapter(Excel,Office,guard){return async(action,request)=>{
 let dispatched=false;
 try{
  const items=validateLinks(request.items);if(items.some(x=>x.restoreText===undefined))throw Error('General hyperlink editing is disabled pending live rich-text preservation coverage.');await guard();
  if(!Office.context.requirements.isSetSupported('ExcelApi','1.7'))throw Error('ExcelApi 1.7 required.');
  if(action==='links-add'&&Office.context.document.mode!=='readWrite')throw Error('Workbook is read-only.');
  return await Excel.run(async context=>{
   const ranges=items.map(x=>{const r=context.workbook.worksheets.getItem(x.sheet).getRange(x.cell);r.load('values,formulas,hyperlink');return r;});await context.sync();
   for(let i=0;i<items.length;i++)if(String(ranges[i].values[0][0]??'')!==items[i].expectedValue||(ranges[i].hyperlink?.address??null)!==items[i].oldAddress||String(ranges[i].formulas[0][0]??'').startsWith('='))throw Error('Cell text, formula or hyperlink differs from the expected source.');
   if(action==='links-read')return {status:'links_ready',count:items.length};
   if(action!=='links-add')throw Error('Unsupported hyperlink operation.');
   await guard();dispatched=true;
   for(let i=0;i<items.length;i++){const item=items[i];ranges[i].hyperlink=item.restoreText!==undefined?{address:item.newAddress,textToDisplay:item.restoreText}:{address:item.newAddress};if(item.restoreFont)ranges[i].format.font.set(item.restoreFont);}
   await context.sync();for(const r of ranges)r.load('values,hyperlink');await context.sync();
   const ok=ranges.every((r,i)=>r.hyperlink?.address===items[i].newAddress&&String(r.values[0][0]??'')===(items[i].restoreText??items[i].expectedValue));
   if(ok){context.workbook.save(Excel.SaveBehavior.save);await context.sync();}
   return {status:ok?'links_session_verified':'uncertain_after_dispatch',count:items.length};
  });
 }catch(e){return {status:dispatched?'uncertain_after_dispatch':'refused_before_mutation',code:String(e.message||e)};}
};}
