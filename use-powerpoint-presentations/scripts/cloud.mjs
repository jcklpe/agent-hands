import fs from 'node:fs';
import {privateTempDir} from '../../use-word-documents/scripts/temporary.mjs';
import path from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {createRequire} from 'node:module';
import {ROOT, MAX_TEXT, MAX_SLIDES, MAX_SHAPES, fail, targetFromMetadata} from './core.mjs';
const require = createRequire(new URL('../../use-word-documents/package.json', import.meta.url));
const {unzipSync, strFromU8} = require('fflate'), {XMLParser, XMLValidator} = require('fast-xml-parser');
export {requireWrite} from '../../use-word-documents/scripts/cloud.mjs';
const exec = promisify(execFile);
async function provider(relative, args, json = true) {
  try { const r = await exec('bash', [path.join(ROOT, relative), ...args], {maxBuffer:2_000_000, timeout:120_000}); return json ? JSON.parse(r.stdout) : undefined; }
  catch { fail('provider_failed', 'The Microsoft CLI request failed. Check the selected account and Microsoft Files access; no browser mutation was retried.'); }
}
export async function cloudTarget(alias, drive, item) {
  const profile = await provider('setup-microsoft-services/scripts/authorize', ['profile',alias,'--json']);
  const meta = await provider('use-microsoft-files/scripts/files', ['meta',alias,item,'--drive',drive,'--json']);
  if (!Number.isSafeInteger(meta.size) || meta.size < 0 || meta.size > 20_000_000) fail('presentation_too_large', 'This capability supports PPTX files up to 20 MB.');
  const parent = meta.parentReference?.id ? await provider('use-microsoft-files/scripts/files', ['meta',alias,meta.parentReference.id,'--drive',drive,'--json']) : undefined;
  return {profile, target:targetFromMetadata(alias,drive,item,meta,parent)};
}
function parts(bytes, selected) {
  if (bytes.length > 20_000_000) fail('presentation_too_large', 'Downloaded PPTX exceeds 20 MB.');
  let total=0, count=0; const seen=new Set();
  return unzipSync(new Uint8Array(bytes), {filter(entry) {
    total+=entry.originalSize; count++;
    if (seen.has(entry.name) || count>5000 || !Number.isSafeInteger(total) || total>64_000_000 || entry.originalSize<0) fail('invalid_pptx','PPTX contains duplicate parts or exceeds the expansion limit.');
    seen.add(entry.name);
    if (selected(entry.name) && entry.originalSize>4_000_000) fail('presentation_too_large','Selected XML exceeds 4 MB.');
    return selected(entry.name);
  }});
}
const parser = new XMLParser({preserveOrder:true, ignoreAttributes:false, trimValues:false, parseTagValue:false, processEntities:true});
function xml(bytes) {
  if (!bytes) fail('invalid_pptx','A required presentation part is missing.');
  const text=strFromU8(bytes);
  if (/<!DOCTYPE|<!ENTITY/i.test(text) || XMLValidator.validate(text)!==true) fail('invalid_pptx','Unsupported presentation XML.');
  return parser.parse(text);
}
const nodes=(list,key)=>list.filter(n=>Object.hasOwn(n,key));
const one=(list,key)=>{const found=nodes(list,key);if(found.length!==1)fail('invalid_pptx','Missing or ambiguous presentation structure.');return found[0];};
const attrs=node=>node[':@']||{};
const has=(list,names)=>list.some(n=>Object.entries(n).some(([k,v])=>names.includes(k)||Array.isArray(v)&&has(v,names)));
function resolvePart(base, target) {
  if (typeof target!=='string' || target.includes('\\') || target.includes('?') || target.includes('#')) fail('invalid_pptx','Unsupported package relationship.');
  return path.posix.resolve('/',base,target).slice(1);
}
function rels(data) { return nodes(one(xml(data),'Relationships').Relationships,'Relationship').map(attrs); }
const REL='http://schemas.openxmlformats.org/officeDocument/2006/relationships/';
export function pptxShapes(bytes) {
  const entries=parts(bytes,name=>name==='ppt/presentation.xml'||name==='ppt/_rels/presentation.xml.rels'||/^ppt\/slides\/slide[^/]*\.xml$/.test(name));
  const presentation=one(xml(entries['ppt/presentation.xml']),'p:presentation');
  if (attrs(presentation)['@_xmlns:p']!=='http://schemas.openxmlformats.org/presentationml/2006/main') fail('unsupported_pptx','Unsupported presentation namespace.');
  const slides=nodes(one(presentation['p:presentation'],'p:sldIdLst')['p:sldIdLst'],'p:sldId');
  if (!slides.length||slides.length>MAX_SLIDES) fail('presentation_too_large','Read supports 1–100 slides.');
  const relationships=rels(entries['ppt/_rels/presentation.xml.rels']), ids=new Set(), shapes=[]; let chars=0;
  for (const slide of slides) {
    const id=attrs(slide)['@_id'], rid=attrs(slide)['@_r:id'];
    if (!/^[0-9]{1,10}$/.test(id)||ids.has(id)) fail('invalid_pptx','Ambiguous slide identity.');
    ids.add(id);
    const matches=relationships.filter(r=>r['@_Id']===rid && r['@_Type']===REL+'slide' && r['@_TargetMode']!=='External');
    if(matches.length!==1)fail('invalid_pptx','Slide relationship is unavailable.');
    const part=resolvePart('ppt',matches[0]['@_Target']);
    if(!/^ppt\/slides\/slide[^/]*\.xml$/.test(part))fail('unsupported_pptx','Unsupported slide part path.');
    const slideXML=one(xml(entries[part]),'p:sld')['p:sld'];
    const tree=one(one(slideXML,'p:cSld')['p:cSld'],'p:spTree')['p:spTree'], shapeIds=new Set();
    for(const node of nodes(tree,'p:sp')) {
      const sp=node['p:sp'], identity=attrs(one(one(sp,'p:nvSpPr')['p:nvSpPr'],'p:cNvPr'));
      const shapeId=identity['@_id'], name=identity['@_name'];
      if(!/^[0-9]{1,10}$/.test(shapeId)||shapeIds.has(shapeId)||typeof name!=='string')fail('invalid_pptx','Ambiguous shape identity.');
      shapeIds.add(shapeId);
      const bodies=nodes(sp,'p:txBody');
      const supported=bodies.length===1&&!has(sp,['a:fld','a:hlinkClick','a:hlinkMouseOver','p:oleObj','p:contentPart']);
      let text;
      if(supported)text=nodes(bodies[0]['p:txBody'],'a:p').map(p=>p['a:p'].map(n=>{
        if(n['a:br'])return '\n';
        if(n['a:r'])return nodes(n['a:r'],'a:t').map(t=>t['a:t'].map(v=>v['#text']||'').join('')).join('');
        return '';
      }).join('')).join('\n');
      chars+=text?.length||0;
      shapes.push({slideId:id,shapeId,name,supported,...(supported?{text}: {})});
      if(shapes.length>MAX_SHAPES||chars>MAX_TEXT)fail('presentation_too_large','Presentation exceeds the bounded shape/text limit.');
    }
  }
  return shapes;
}
export function pptxStartup(bytes, addinId) {
  const entries=parts(bytes,name=>name==='_rels/.rels'||/^ppt\/webextensions\//.test(name));
  let extensionPart;
  for(const [name,data] of Object.entries(entries)) {
    if(!/^ppt\/webextensions\/webextension\d*\.xml$/.test(name))continue;
    const document=xml(data), root=nodes(document,'we:webextension');
    if(root.length!==1)continue;
    const body=root[0]['we:webextension'], reference=nodes(body,'we:reference');
    if(reference.length!==1 || attrs(reference[0])['@_id']?.toLowerCase()!==addinId.toLowerCase())continue;
    if(extensionPart) return false;
    const properties=nodes(body,'we:properties');
    if(properties.length!==1 || !nodes(properties[0]['we:properties'],'we:property').some(n=>attrs(n)['@_name']==='Office.AutoShowTaskpaneWithDocument'&&attrs(n)['@_value']==='true'))return false;
    extensionPart=name;
  }
  if(!extensionPart||!entries['_rels/.rels']||!entries['ppt/webextensions/taskpanes.xml']||!entries['ppt/webextensions/_rels/taskpanes.xml.rels'])return false;
  const type='http://schemas.microsoft.com/office/2011/relationships/';
  const roots=rels(entries['_rels/.rels']).filter(r=>r['@_TargetMode']!=='External'&&r['@_Type']===type+'webextensiontaskpanes'&&resolvePart('',r['@_Target'])==='ppt/webextensions/taskpanes.xml');
  const references=rels(entries['ppt/webextensions/_rels/taskpanes.xml.rels']).filter(r=>r['@_TargetMode']!=='External'&&r['@_Type']===type+'webextension'&&resolvePart('ppt/webextensions',r['@_Target'])===extensionPart);
  const panes=nodes(one(xml(entries['ppt/webextensions/taskpanes.xml']),'wetp:taskpanes')['wetp:taskpanes'],'wetp:taskpane');
  return roots.length===1&&references.length===1&&panes.filter(p=>nodes(p['wetp:taskpane'],'wetp:webextensionref').some(n=>attrs(n)['@_r:id']===references[0]['@_Id'])).length===1;
}
async function download(account,target,inspect) {
  const dir=privateTempDir('agent-hands-powerpoint-readback-');
  try {const file=path.join(dir,'readback.pptx');await provider('use-microsoft-files/scripts/files',['download',target.alias,target.item,'--drive',target.drive,'--out',file],false);return inspect(fs.readFileSync(file));}
  finally {fs.rmSync(dir,{recursive:true,force:true});}
}
export const downloadShapes=(account,target)=>download(account,target,pptxShapes);
export const downloadStartup=(account,target)=>download(account,target,bytes=>pptxStartup(bytes,account.addinId));
export function cloudResult(shapes,edit) {
  const matches=shapes.filter(s=>s.slideId===edit.slideId.split('#')[0]&&s.shapeId===edit.shapeId);
  if(matches.length!==1||!matches[0].supported||matches[0].name!==edit.name)return 'cloud_conflict_or_unverified';
  const normalized=s=>s.replace(/\r\n|[\r\v]/g,'\n');
  const actual=normalized(matches[0].text);
  return actual===normalized(edit.after)?'cloud_text_verified':actual===normalized(edit.before)?'original_text_observed':'cloud_conflict_or_unverified';
}
