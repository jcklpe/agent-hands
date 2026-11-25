export function validateComments(items) {
 if(!Array.isArray(items)||!items.length||items.length>200)throw Error('Use 1–200 comment targets.');
 const seen=new Set();let size=0;
 for(const x of items){
  if(!x||Object.keys(x).some(k=>!['sheet','cell','content','expectedValue'].includes(k))||typeof x.sheet!=='string'||!x.sheet||x.sheet.length>31||!/^\$?[A-Z]{1,3}\$?[1-9][0-9]{0,6}$/.test(x.cell)||typeof x.expectedValue!=='string'||typeof x.content!=='string'||!x.content.trim()||x.content.length>30000)throw Error('Invalid bounded comment target.');
  const key=x.sheet+'!'+x.cell;if(seen.has(key))throw Error('Duplicate comment target.');seen.add(key);size+=x.content.length;
 }
 if(size>1000000)throw Error('Comment batch exceeds one million characters.');
 return items;
}
export function createCommentsAdapter(Excel,Office,guard){
 return async (action,request)=>{
  let dispatched=false;
  try{
   const items=validateComments(request.items);await guard();
   if(action==='comments-add' && Office.context.document.mode!=='readWrite')throw Error('Workbook is read-only.');
   if(!Office.context.requirements.isSetSupported('ExcelApi','1.10'))throw Error('ExcelApi 1.10 is required.');
   return await Excel.run(async context=>{
    const comments=context.workbook.comments;comments.load('items/id');
    const ranges=items.map(x=>{const r=context.workbook.worksheets.getItem(x.sheet).getRange(x.cell);r.load('values');return r;});await context.sync();
    const locations=comments.items.map(c=>{const l=c.getLocation();l.load('address');return l;});await context.sync();
    const occupied=new Set(locations.map(l=>l.address.replace(/'/g,'').replace(/\$/g,'')));
    for(let i=0;i<items.length;i++){
     const x=items[i];if(occupied.has(x.sheet+'!'+x.cell.replace(/\$/g,'')))throw Error('Target already has a comment; preserved without change.');
     if(String(ranges[i].values[0][0]??'')!==x.expectedValue)throw Error('Cell changed since inspection; no comments written.');
    }
    if(action==='comments-read')return {status:'comments_ready',count:items.length};
    if(action!=='comments-add')throw Error('Unsupported comment operation.');
    await guard();dispatched=true;
    const added=items.map((x,i)=>comments.add(ranges[i],x.content,Excel.ContentType.plain));
    await context.sync();for(const c of added)c.load('content');await context.sync();
    if(added.some((c,i)=>c.content!==items[i].content))return {status:'uncertain_after_dispatch',count:items.length};
    return {status:'comments_session_verified',count:items.length};
   });
  }catch(e){return {status:dispatched?'uncertain_after_dispatch':'refused_before_mutation',code:String(e.message||e)};}
 };
}
