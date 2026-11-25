import test from 'node:test';
import assert from 'node:assert/strict';
import {tailEdit,sameParagraphs} from '../scripts/tail-core.mjs';
test('normalizes Word nonbreaking spaces and soft breaks for cloud text comparison',()=>{
 assert.ok(sameParagraphs(['1\u00a0 Question\u0005','A\vB'],['1  Question','A\nB']));
 assert.ok(!sameParagraphs(['1 Question'],['2 Question']));
});
const spec=()=>({anchor:'Draft appendix',label:'Separate draft',url:'https://example.test/draft',replacements:[{before:'The draft follows.',after:'The draft is linked below.'}]});
test('removes the exact tail while preserving and explicitly updating the prefix',()=>{
 const before=['Title','The draft follows.','','Draft appendix','Question one','Question two'];
 const edit=tailEdit(before,spec());
 assert.deepEqual(edit.after,['Title','The draft is linked below.','Separate draft']);
 assert.deepEqual(edit.before,['Title','The draft follows.','Draft appendix','Question one','Question two']);
 assert.ok(!sameParagraphs(edit.before,['Title','Human notes','Draft appendix']));
});
test('rejects duplicate/missing anchors, unexpected prefix changes and unsafe links',()=>{
 assert.throws(()=>tailEdit(['Title','Draft appendix','Draft appendix'],spec()));
 assert.throws(()=>tailEdit(['Title','Different appendix'],spec()));
 assert.throws(()=>tailEdit(['Title','Human notes','Draft appendix'],spec()));
 for(const url of ['javascript:alert(1)','http://example.test','https://user:password@example.test'])assert.throws(()=>tailEdit(['Title','The draft follows.','Draft appendix'],{...spec(),url}));
});

test('commented prefix can be retained but commented tail is refused', async()=>{
 const {zipSync,strToU8}=await import('fflate');
 const {bodySnapshot,commentEvidence}=await import('../scripts/tail-core.mjs');
 const body='<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:commentRangeStart w:id="1"/><w:r><w:t>Keep this</w:t></w:r><w:commentRangeEnd w:id="1"/><w:r><w:commentReference w:id="1"/></w:r></w:p><w:p><w:r><w:t>Remove tail</w:t></w:r></w:p></w:body></w:document>';
 const bytes=zipSync({'word/document.xml':strToU8(body),'word/comments.xml':strToU8('<w:comments xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:comment w:id="1" w:author="Reviewer"><w:p><w:r><w:t>Keep the evidence</w:t></w:r></w:p></w:comment></w:comments>')});
 assert.throws(()=>bodySnapshot(bytes));
 assert.deepEqual(bodySnapshot(bytes,['Keep this']),['Keep this','Remove tail']);
 assert.throws(()=>bodySnapshot(bytes,['Remove tail']));
 assert.ok(JSON.stringify(commentEvidence(bytes)).includes('Keep the evidence'));
});

test('tracked insertions are allowed only in the untouched prefix and remain evidence',async()=>{
 const {zipSync,strToU8}=await import('fflate');const {bodySnapshot,commentEvidence}=await import('../scripts/tail-core.mjs');
 const bytes=zipSync({'word/document.xml':strToU8('<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:ins w:author="Reviewer" w:id="1"><w:r><w:t>Proposed prefix</w:t></w:r></w:ins></w:p><w:p><w:r><w:t>Tail</w:t></w:r></w:p></w:body></w:document>')});
 assert.throws(()=>bodySnapshot(bytes));assert.throws(()=>bodySnapshot(bytes,['Tail']));assert.deepEqual(bodySnapshot(bytes,['Proposed prefix']),['Proposed prefix','Tail']);assert.ok(JSON.stringify(commentEvidence(bytes)).includes('Reviewer'));
});

test('review evidence permits Word revision-ID rewrites but preserves attribution and content',async()=>{
 const {sameReviewEvidence}=await import('../scripts/tail-core.mjs');const a={comments:{text:'Comment'},insertions:[{'@_id':'1','@_author':'Reviewer',r:{'@_rsidR':'x',t:'Proposed'}}]};const b=structuredClone(a);b.insertions[0]['@_id']='2';b.insertions[0].r['@_rsidR']='y';assert.ok(sameReviewEvidence(a,b));b.insertions[0].r.t='Different';assert.ok(!sameReviewEvidence(a,b));
});
