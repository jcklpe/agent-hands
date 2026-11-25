import {unzipSync,strFromU8} from 'fflate';
import {XMLParser,XMLValidator} from 'fast-xml-parser';
import {createHash} from 'node:crypto';
import {fail} from './core.mjs';
import {commentEvidence,sameReviewEvidence} from './tail-core.mjs';
import '../addin/paragraphs.js';
export const validateParagraphs=globalThis.AgentHandsParagraphs.validate;
export const normalized=x=>x.replace(/[\r\f\u0005]/g,'').replace(/\v/g,'\n').replace(/\u00a0/g,' ');
export function paragraphSnapshot(bytes) {
  let size=0;
  const entries=unzipSync(new Uint8Array(bytes),{filter:e=>{size+=e.originalSize;if(size>64000000||e.originalSize<0)fail('oversized_document','DOCX exceeds the readback bound.');return true;}});
  const parse=file=>{const xml=strFromU8(entries[file]);if(/<!DOCTYPE|<!ENTITY/.test(xml)||XMLValidator.validate(xml)!==true)fail('invalid_document','Invalid XML.');return new XMLParser({preserveOrder:true,removeNSPrefix:true,ignoreAttributes:false,trimValues:false,parseTagValue:false}).parse(xml);};
  const body=parse('word/document.xml').find(x=>x.document)?.document.find(x=>x.body)?.body;
  if(!body)fail('invalid_document','Missing document body.');
  const text=nodes=>nodes.map(n=>n.t?n.t.map(x=>x['#text']??'').join(''):n.tab?'\t':n.br?(n[':@']?.['@_type']==='page'?'':'\n'):Object.entries(n).filter(([k,v])=>k!==':@'&&Array.isArray(v)).map(([,v])=>text(v)).join('')).join('');
  const all=[],direct=[],anchors=[],links=[];
  function walk(nodes,top=false){for(const n of nodes){if(n.p){const value=normalized(text(n.p));all.push(value);if(top)direct.push(value);}for(const [k,v] of Object.entries(n)){if(['commentRangeStart','commentRangeEnd','commentReference'].includes(k))anchors.push({kind:k,id:n[':@']?.['@_id']});if(k==='hyperlink')links.push({id:n[':@']?.['@_id'],text:text(v)});if(Array.isArray(v))walk(v);}}}
  walk(body,true);
  const rels={};if(entries['word/_rels/document.xml.rels'])for(const n of parse('word/_rels/document.xml.rels').find(x=>x.Relationships)?.Relationships||[])if(n.Relationship)rels[n[':@']['@_Id']]=n[':@'];
  const media={};for(const [p,data] of Object.entries(entries))if(p.startsWith('word/media/'))media[p]=createHash('sha256').update(data).digest('hex');
  return {all,direct,anchors,links:links.map(l=>({text:l.text,address:rels[l.id]?.['@_Target']})),media,review:commentEvidence(bytes)};
}
export function paragraphMode(snapshot,live) {
  for(const mode of ['direct','all'])if(JSON.stringify(snapshot[mode])===JSON.stringify(live.map(normalized)))return mode;
  fail('cloud_baseline_mismatch','Word and the downloaded document have different paragraph sequences.');
}
export function verifyParagraphs(before,after,spec,mode) {
  const expected=[...before[mode]];
  for(const x of spec.paragraphs)if(x.after!==undefined)expected[x.index]=normalized(x.after);
  expected.push(...spec.append.map(x=>normalized(x.text)));
  const issues=[];
  if(JSON.stringify(expected)!==JSON.stringify(after[mode]))issues.push('paragraph text differs');
  if(!sameReviewEvidence(before.review,after.review))issues.push('comment or tracked insertion changed');
  if(JSON.stringify(before.anchors)!==JSON.stringify(after.anchors))issues.push('comment anchors changed');
  if(JSON.stringify(before.media)!==JSON.stringify(after.media))issues.push('embedded media changed');
  const links=before.links.map(l=>({...l,address:spec.links.find(x=>x.before===l.address)?.after??l.address}));
  if(JSON.stringify(links)!==JSON.stringify(after.links))issues.push('hyperlink text or destination differs');
  return {status:issues.length?'saved_paragraphs_unverified':'saved_paragraphs_verified',issues,commentsPreserved:sameReviewEvidence(before.review,after.review),visualAcceptanceRequired:true,replayAllowed:false};
}
