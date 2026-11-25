// Preserve the displayed runs when replacing an HTTPS reference. Formula cells always refuse.
const fail=code=>{throw Object.assign(new Error(code),{code});};
export function validateReferences(items) {
  if(!Array.isArray(items)||!items.length||items.length>200)fail('invalid_reference_count');const seen=new Set();
  for(const x of items) {
    if(!x||Object.keys(x).some(k=>!['sheet','cell','before','oldAddress','newAddress','replacements','allowStrikeRemoval'].includes(k))||typeof x.sheet!=='string'||!x.sheet||x.sheet.length>31||!/^[A-Z]{1,3}[1-9][0-9]{0,6}$/.test(x.cell)||typeof x.before!=='string'||x.before.length>32767||!Array.isArray(x.replacements)||x.replacements.length>8||(x.allowStrikeRemoval!==undefined&&typeof x.allowStrikeRemoval!=='boolean'))fail('invalid_reference');
    const urlpair=(a,b)=>{try{a=new URL(a);b=new URL(b);if(a.protocol!=='https:'||b.protocol!=='https:'||a.origin!==b.origin||a.username||a.password||b.username||b.password)fail('invalid_url');}catch{fail('invalid_url');}};
    if(x.oldAddress!==null||x.newAddress!==null)urlpair(x.oldAddress??x.newAddress,x.newAddress);
    for(const r of x.replacements){if(!r||Object.keys(r).some(k=>!['before','after'].includes(k)))fail('invalid_replacement');urlpair(r.before,r.after);if(x.before.split(r.before).length!==2)fail('ambiguous_reference');}
    const key=x.sheet+'!'+x.cell;if(seen.has(key))fail('duplicate_reference');seen.add(key);
  }
  return items;
}
function changedRuns(runs,replacements) {
  let result=structuredClone(runs);
  for(const change of replacements) {
    const full=result.map(r=>r.text).join(''),start=full.indexOf(change.before),end=start+change.before.length;let offset=0,inserted=false;const next=[];
    if(start<0||full.indexOf(change.before,start+1)>=0)fail('ambiguous_reference');
    for(const r of result) {const a=offset,b=offset+r.text.length;offset=b;if(b<=start||a>=end){next.push(r);continue;}if(a<start)next.push({...r,text:r.text.slice(0,start-a)});if(!inserted){next.push({...r,text:change.after});inserted=true;}if(b>end)next.push({...r,text:r.text.slice(end-a)});}
    result=next;
  }
  return result;
}
export function createReferencesAdapter(Excel,Office,guard) {return async(action,request)=>{
  let dispatched=false;
  try {
    const items=validateReferences(request.items);await guard();if(!Office.context.requirements.isSetSupported('ExcelApi','1.18'))fail('excel_api_1_18_required');
    if(!['references-read','references-apply'].includes(action))fail('unsupported_operation');if(action==='references-apply'&&Office.context.document.mode!=='readWrite')fail('read_only');
    return await Excel.run(async context=>{
      const ranges=items.map(x=>{const r=context.workbook.worksheets.getItem(x.sheet).getRange(x.cell);r.load('values,formulas,hyperlink');r.format.font.load('name,size,bold,italic,color,underline,strikethrough');return r;});
      const props=ranges.map(r=>r.getCellProperties({textRuns:true}));await context.sync();
      const expected=ranges.map((r,i)=>{const value=r.values[0][0];if(value!==items[i].before||String(r.formulas[0][0]).startsWith('=')||(r.hyperlink?.address??null)!==items[i].oldAddress)fail('stale_reference');const f=r.format.font;return {runs:JSON.parse(JSON.stringify(props[i].value[0][0].textRuns)),font:{name:f.name,size:f.size,bold:f.bold,italic:f.italic,color:f.color,underline:f.underline,strikethrough:f.strikethrough}};});
      if(expected.some((x,i)=>!Array.isArray(x.runs)||x.runs.map(r=>r.text).join('')!==items[i].before))fail('text_runs_unavailable');
      const cleanRuns=runs=>runs.map(r=>({text:r.text,font:Object.fromEntries(Object.entries(r.font||{}).filter(([k,v])=>['name','size','bold','italic','color','underline','strikethrough','subscript','superscript','tintAndShade'].includes(k)&&v!==null))}));
      const after=expected.map((x,i)=>changedRuns(cleanRuns(x.runs),items[i].replacements));
      if(action==='references-apply') {if(!Array.isArray(request.restoration)||request.restoration.length!==items.length)fail('saved_font_baseline_required');for(let i=0;i<items.length;i++){const v=request.restoration[i];if(!v||!v.base||!Array.isArray(v.runs)||v.runs.map(r=>r.text).join('')!==after[i].map(r=>r.text).join(''))fail('invalid_font_restoration');for(const f of [v.base,...v.runs.map(r=>r.font)])if(!f||Object.keys(f).some(k=>!['name','size','bold','italic','color','underline','strikethrough','subscript','superscript'].includes(k))||['bold','italic','strikethrough','subscript','superscript'].some(k=>typeof f[k]!=='boolean'))fail('invalid_font_restoration');}}
      if(action==='references-read')return {status:'references_ready',expected,after};
      if(JSON.stringify(expected)!==JSON.stringify(request.expected))fail('stale_formatting');
      await guard();dispatched=true;
      for(let i=0;i<items.length;i++)if(!request.restoreOnly&&items[i].newAddress!==null)ranges[i].hyperlink={address:items[i].newAddress,textToDisplay:after[i].map(r=>r.text).join('')};
      await context.sync();
      for(let i=0;i<items.length;i++){ranges[i].format.font.set(Object.fromEntries(Object.entries(request.restoration[i].base).filter(([k])=>!['subscript','superscript'].includes(k))));ranges[i].setCellProperties([[{textRuns:request.restoration[i].runs}]]);}
      await context.sync();context.workbook.save(Excel.SaveBehavior.save);await context.sync();
      return {status:'references_save_returned',expectedAfter:after,savedFileVerified:false};
    });
  }catch(e){return {status:dispatched?'uncertain_after_dispatch':'refused_before_mutation',code:e.code||'office_error'};}
};}
