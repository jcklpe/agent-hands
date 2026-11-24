import {unzipSync,strFromU8} from 'fflate';
import {XMLParser,XMLValidator} from 'fast-xml-parser';
import {docxParagraphs} from './cloud.mjs';
import {fail,MAX_TEXT} from './core.mjs';

export const normalizeParagraphs = paragraphs => paragraphs.map(v=>v.replace(/[\r\f]/g,'').replace(/\v/g,'\n').replace(/\u00a0/g,' ')).filter(v=>v.trim());
export function bodySnapshot(bytes) {
  docxParagraphs(bytes);
  let size=0;
  const entries=unzipSync(new Uint8Array(bytes),{filter:e=>{
    size+=e.originalSize;
    if(size>64_000_000 || e.originalSize<0)fail('document_too_large','DOCX expansion exceeds the readback bound.');
    return e.name==='word/document.xml' || /^word\/comments[^/]*\.xml$/.test(e.name);
  }});
  for(const [name,value] of Object.entries(entries)) if(name!=='word/document.xml' && /<(?:\w+:)?comment\b/.test(strFromU8(value)))fail('unsupported_document','Tail replacement refuses documents containing comments. Preserve and handle those comments separately.');
  const xml=strFromU8(entries['word/document.xml']);
  if(XMLValidator.validate(xml)!==true || /<!DOCTYPE|<!ENTITY/.test(xml))fail('invalid_docx','Invalid body XML.');
  const parsed=new XMLParser({preserveOrder:true,removeNSPrefix:true,ignoreAttributes:false,trimValues:false,parseTagValue:false}).parse(xml);
  const body=parsed.find(n=>n.document)?.document.find(n=>n.body)?.body;
  if(!body || body.some(n=>!n.p && !n.sectPr))fail('unsupported_document','Tail replacement supports paragraph-only document bodies.');
  const has=(nodes,names)=>nodes.some(n=>Object.entries(n).some(([key,value])=>names.includes(key) || Array.isArray(value)&&has(value,names)));
  if(has(body,['sdt','object','drawing','fldChar','fldSimple','commentRangeStart','commentRangeEnd','commentReference']))fail('unsupported_document','Body controls, objects, fields and comments require a separate workflow.');
  const content=nodes=>nodes.map(n=>n.t?n.t.map(t=>t['#text']??'').join(''):n.tab?'\t':n.br?'\n':Object.entries(n).filter(([k,v])=>k!==':@'&&Array.isArray(v)).map(([,v])=>content(v)).join('')).join('');
  const paragraphs=normalizeParagraphs(body.filter(n=>n.p).map(n=>content(n.p)));
  if(paragraphs.join('').length>MAX_TEXT)fail('document_too_large','Body exceeds the text bound.');
  return paragraphs;
}
export function tailEdit(paragraphs,spec) {
  if(!spec || Object.keys(spec).some(k=>!['anchor','label','url','replacements'].includes(k)))fail('unsupported_edit','Use only anchor, label, url and replacements.');
  const values=[spec.anchor,spec.label];
  if(values.some(v=>typeof v!=='string'||!v.trim()||v.length>255||/[\x00-\x1f]/.test(v)))fail('unsupported_edit','Anchor and link label must be short, nonempty paragraph text.');
  let url;try{url=new URL(spec.url);}catch{fail('unsupported_edit','Use an exact HTTPS link.');}
  if(url.protocol!=='https:'||url.username||url.password||spec.url.length>2048||/[\x00-\x20]/.test(spec.url))fail('unsupported_edit','Use an HTTPS link without credentials or whitespace.');
  const before=normalizeParagraphs(paragraphs),index=before.indexOf(spec.anchor);
  if(index<1 || before.lastIndexOf(spec.anchor)!==index)fail('ambiguous_anchor','The tail heading must occur exactly once after a preserved prefix.');
  if(!Array.isArray(spec.replacements)||spec.replacements.length>5)fail('unsupported_edit','Provide up to five exact prefix paragraph replacements.');
  const prefix=before.slice(0,index);
  const seen=new Set();
  for(const replacement of spec.replacements){
    if(!replacement||Object.keys(replacement).some(k=>!['before','after'].includes(k))||['before','after'].some(k=>typeof replacement[k]!=='string'||!replacement[k].trim()||replacement[k].length>4000||/[\x00-\x1f]/.test(replacement[k]))||seen.has(replacement.before))fail('unsupported_edit','Prefix replacements must contain distinct, nonempty before/after paragraphs.');
    seen.add(replacement.before);
    if(prefix.filter(p=>p===replacement.before).length!==1)fail('ambiguous_anchor','Each prefix replacement must match exactly one preserved paragraph.');
    prefix[prefix.indexOf(replacement.before)]=replacement.after;
  }
  return {kind:'replace-tail',...structuredClone(spec),before,after:[...prefix,spec.label]};
}
export function sameParagraphs(a,b){return JSON.stringify(normalizeParagraphs(a))===JSON.stringify(normalizeParagraphs(b));}
