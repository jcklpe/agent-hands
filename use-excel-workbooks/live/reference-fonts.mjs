// Derive complete effective text-run fonts from the retained read-only package snapshot, not a mixed range's aggregate font.
const fail=code=>{throw Object.assign(new Error(code),{code});};
export function referenceFormatting(snapshot,items){
 const font=(tree,base={bold:false,italic:false,strikethrough:false,underline:'None',subscript:false,superscript:false})=>{
  const f={...base};if(tree?.[0].endsWith('}rPr'))Object.assign(f,{bold:false,italic:false,strikethrough:false,underline:'None',subscript:false,superscript:false});for(const [tag,attrs] of tree?.[3]||[]){const k=tag.split('}').at(-1),v=attrs.val;
   if(['name','rFont'].includes(k))f.name=v;
   else if(k==='sz')f.size=Number(v);
   else if(['b','i','strike'].includes(k))f[{b:'bold',i:'italic',strike:'strikethrough'}[k]]=!['0','false','off'].includes(v);
   else if(k==='color'){if(!/^(?:[a-fA-F0-9]{2})?[a-fA-F0-9]{6}$/.test(attrs.rgb||''))fail('unresolved_font_color');f.color='#'+attrs.rgb.slice(-6);}
   else if(k==='u'){const map={single:'Single',double:'Double',singleAccounting:'SingleAccountant',doubleAccounting:'DoubleAccountant',none:'None'};f.underline=map[v||'single'];if(!f.underline)fail('unsupported_underline');}
   else if(k==='vertAlign'){f.subscript=v==='subscript';f.superscript=v==='superscript';}
   else if(!['family','charset','scheme'].includes(k))fail('unsupported_font_property');
  }return f;
 };
 return items.map(x=>{
  const c=snapshot.sheets[x.sheet]?.cells[x.cell];if(!c||c.formula)fail('missing_reference_baseline');const base=font(c.font);let runs=[];
  if(c.rich){for(const node of c.rich[3]){const tag=node[0].split('}').at(-1);if(tag==='t')runs.push({text:node[2],font:{...base}});else if(tag==='r'){const prop=node[3].find(n=>n[0].endsWith('}rPr'));const text=node[3].filter(n=>n[0].endsWith('}t')).map(n=>n[2]).join('');runs.push({text,font:font(prop,base)});}}}else runs=[{text:c.value,font:base}];
  if(runs.map(r=>r.text).join('')!==x.before)fail('saved_reference_text_mismatch');
  for(const change of x.replacements){const full=runs.map(r=>r.text).join(''),start=full.indexOf(change.before),end=start+change.before.length;let offset=0,inserted=false;const next=[];if(start<0||full.indexOf(change.before,start+1)>=0)fail('ambiguous_reference');for(const r of runs){const a=offset,b=offset+r.text.length;offset=b;if(b<=start||a>=end){next.push(r);continue;}if(a<start)next.push({...r,text:r.text.slice(0,start-a)});if(!inserted){next.push({...r,text:change.after});inserted=true;}if(b>end)next.push({...r,text:r.text.slice(end-a)});}runs=next;}
  return {base,runs};
 });
}
