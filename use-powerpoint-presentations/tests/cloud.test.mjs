import test from 'node:test';
import assert from 'node:assert/strict';
import {createRequire} from 'node:module';
import {pptxShapes,pptxStartup,cloudResult} from '../scripts/cloud.mjs';
const {zipSync,strToU8}=createRequire(new URL('../../use-word-documents/package.json',import.meta.url))('fflate');
const rel='http://schemas.openxmlformats.org/officeDocument/2006/relationships/';
const pack=entries=>Buffer.from(zipSync(Object.fromEntries(Object.entries(entries).map(([k,v])=>[k,strToU8(v)]))));
const shape=(id,name,text)=>`<p:sp><p:nvSpPr><p:cNvPr id="${id}" name="${name}"/></p:nvSpPr><p:txBody><a:p><a:r><a:t>${text}</a:t></a:r></a:p></p:txBody></p:sp>`;
const slide=body=>`<p:sld><p:cSld><p:spTree>${body}</p:spTree></p:cSld></p:sld>`;
function fixture(){return {
 'ppt/presentation.xml':'<p:presentation xmlns:p="http://schemas.openxmlformats.org/presentationml/2006/main"><p:sldIdLst><p:sldId id="256" r:id="s1"/><p:sldId id="257" r:id="s2"/></p:sldIdLst></p:presentation>',
 'ppt/_rels/presentation.xml.rels':`<Relationships><Relationship Id="s1" Type="${rel}slide" Target="slides/slide7.xml"/><Relationship Id="s2" Type="${rel}slide" Target="slides/slide3.xml"/></Relationships>`,
 'ppt/slides/slide7.xml':slide(shape('4','Selected','Target old text.')+shape('5','Other','Other editor changed text.')),
 'ppt/slides/slide3.xml':slide(shape('4','Selected','Target old text.'))
};}
const edit={slideId:'256#100',shapeId:'4',name:'Selected',before:'Target old text.',after:'Target new text.'};
test('cloud mapping follows slide relationships and exact shape, preserving other edits',()=>{
 const f=fixture();assert.equal(cloudResult(pptxShapes(pack(f)),edit),'original_text_observed');
 f['ppt/slides/slide7.xml']=slide(shape('4','Selected','Target new text.')+shape('5','Other','Another independent change.'));
 assert.equal(cloudResult(pptxShapes(pack(f)),edit),'cloud_text_verified');
 f['ppt/slides/slide7.xml']=slide(shape('4','Selected','Target mixed new old text.'));
 assert.equal(cloudResult(pptxShapes(pack(f)),edit),'cloud_conflict_or_unverified');
});
test('fields, hyperlinks and grouped text cannot become edit baselines',()=>{
 for(const inserted of ['<a:fld id="field"/>','<a:hlinkClick r:id="link"/>']){
  const f=fixture();f['ppt/slides/slide7.xml']=f['ppt/slides/slide7.xml'].replace('<a:p>','<a:p>'+inserted);
  assert.equal(cloudResult(pptxShapes(pack(f)),edit),'cloud_conflict_or_unverified');
 }
 const f=fixture();f['ppt/slides/slide7.xml']=slide('<p:grpSp>'+shape('4','Selected','Target old text.')+'</p:grpSp>');
 assert.equal(cloudResult(pptxShapes(pack(f)),edit),'cloud_conflict_or_unverified');
});
test('ambiguous slide IDs and external relationships refuse verification',()=>{
 for(const key of ['ids','external','entity']){
  const f=fixture();
  if(key==='ids')f['ppt/presentation.xml']=f['ppt/presentation.xml'].replace('id="257"','id="256"');
  if(key==='external')f['ppt/_rels/presentation.xml.rels']=f['ppt/_rels/presentation.xml.rels'].replace('Id="s1"','Id="s1" TargetMode="External"');
  if(key==='entity')f['ppt/slides/slide7.xml']='<!DOCTYPE x [<!ENTITY nope "bad">]>'+f['ppt/slides/slide7.xml'];
  assert.throws(()=>pptxShapes(pack(f)),{code:'invalid_pptx'});
 }
});
test('startup requires the exact add-in, enabled property and linked task pane',()=>{
 const type='http://schemas.microsoft.com/office/2011/relationships/';
 const f={'_rels/.rels':`<Relationships><Relationship Id="r1" Type="${type}webextensiontaskpanes" Target="ppt/webextensions/taskpanes.xml"/></Relationships>`,
 'ppt/webextensions/taskpanes.xml':'<wetp:taskpanes><wetp:taskpane><wetp:webextensionref r:id="w1"/></wetp:taskpane></wetp:taskpanes>',
 'ppt/webextensions/_rels/taskpanes.xml.rels':`<Relationships><Relationship Id="w1" Type="${type}webextension" Target="webextension1.xml"/></Relationships>`,
 'ppt/webextensions/webextension1.xml':'<we:webextension><we:reference id="synthetic-addin"/><we:properties><we:property name="Office.AutoShowTaskpaneWithDocument" value="true"/></we:properties></we:webextension>'};
 assert.equal(pptxStartup(pack(f),'synthetic-addin'),true);assert.equal(pptxStartup(pack(f),'other'),false);
 f['ppt/webextensions/taskpanes.xml']=f['ppt/webextensions/taskpanes.xml'].replace('w1','wrong');assert.equal(pptxStartup(pack(f),'synthetic-addin'),false);
});
