import test from 'node:test';
import assert from 'node:assert/strict';
import {tailEdit,sameParagraphs} from '../scripts/tail-core.mjs';
test('normalizes Word nonbreaking spaces and soft breaks for cloud text comparison',()=>{
 assert.ok(sameParagraphs(['1\u00a0 Question','A\vB'],['1  Question','A\nB']));
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
