import {unzipSync,strFromU8} from 'fflate';
import {XMLParser,XMLValidator} from 'fast-xml-parser';
import {docxParagraphs} from './cloud.mjs';
import {fail,MAX_TEXT} from './core.mjs';

export const normalizeParagraphs = paragraphs => paragraphs.map(v=>v.replace(/[\r\f\u0005]/g,'').replace(/\v/g,'\n').replace(/\u00a0/g,' ')).filter(v=>v.trim());
export function bodySnapshot(bytes, allowedCommentParagraphs = []) {
  allowedCommentParagraphs = normalizeParagraphs(allowedCommentParagraphs);
  docxParagraphs(bytes, {allowPreservedInsertions: allowedCommentParagraphs.length > 0});
  let size=0;
  const entries=unzipSync(new Uint8Array(bytes),{filter:e=>{
    size+=e.originalSize;
    if(size>64_000_000 || e.originalSize<0)fail('document_too_large','DOCX expansion exceeds the readback bound.');
    return e.name==='word/document.xml' || /^word\/comments[^/]*\.xml$/.test(e.name);
  }});
  for(const [name,value] of Object.entries(entries)) if(!allowedCommentParagraphs.length && name!=='word/document.xml' && /<(?:\w+:)?comment\b/.test(strFromU8(value)))fail('unsupported_document','Tail replacement refuses documents containing comments. Preserve and handle those comments separately.');
  const xml=strFromU8(entries['word/document.xml']);
  if(XMLValidator.validate(xml)!==true || /<!DOCTYPE|<!ENTITY/.test(xml))fail('invalid_docx','Invalid body XML.');
  const parsed=new XMLParser({preserveOrder:true,removeNSPrefix:true,ignoreAttributes:false,trimValues:false,parseTagValue:false}).parse(xml);
  const body=parsed.find(n=>n.document)?.document.find(n=>n.body)?.body;
  if(!body || body.some(n=>!n.p && !n.sectPr))fail('unsupported_document','Tail replacement supports paragraph-only document bodies.');
  const has=(nodes,names)=>nodes.some(n=>Object.entries(n).some(([key,value])=>names.includes(key) || Array.isArray(value)&&has(value,names)));
  if(has(body,['sdt','object','drawing','fldChar','fldSimple',...(!allowedCommentParagraphs.length?['commentRangeStart','commentRangeEnd','commentReference']:[])]))fail('unsupported_document','Body controls, objects, fields and comments require a separate workflow.');
  const content=nodes=>nodes.map(n=>n.t?n.t.map(t=>t['#text']??'').join(''):n.tab?'\t':n.br?'\n':Object.entries(n).filter(([k,v])=>k!==':@'&&Array.isArray(v)).map(([,v])=>content(v)).join('')).join('');
  for(const node of body.filter(n=>n.p)) if(has(node.p,['commentRangeStart','commentRangeEnd','commentReference','ins']) && !allowedCommentParagraphs.includes(normalizeParagraphs([content(node.p)])[0]))fail('comment_in_changed_range','A comment or insertion touches a paragraph outside the preserved prefix: '+normalizeParagraphs([content(node.p)])[0]);
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

export function commentEvidence(bytes) {
 const entries=unzipSync(new Uint8Array(bytes));
 const parser=new XMLParser({ignoreAttributes:false,removeNSPrefix:true,trimValues:false,parseTagValue:false});
 const xml=entries['word/comments.xml'];
 const body = parser.parse(strFromU8(entries['word/document.xml']));
 const insertions=[];
 function collect(node){if(!node||typeof node!=='object')return;for(const [key,value] of Object.entries(node)){if(key==='ins')insertions.push(value);else if(typeof value==='object')collect(value);}}
 collect(body);
 return {comments:xml?parser.parse(strFromU8(xml)):null,insertions};
}

export function sameReviewEvidence(a,b){
 const normalize=value=>{if(Array.isArray(value))return value.map(normalize);if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).filter(([k])=>k!=='@_id'&&!k.startsWith('@_rsid')).map(([k,v])=>[k,normalize(v)]));return value;};
 return JSON.stringify(a?.comments)===JSON.stringify(b?.comments) && JSON.stringify(normalize(a?.insertions))===JSON.stringify(normalize(b?.insertions));
}
