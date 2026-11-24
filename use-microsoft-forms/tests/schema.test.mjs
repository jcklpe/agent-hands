import test from 'node:test';
import assert from 'node:assert/strict';
import {validateSpec, reachableQuestions, digest} from '../scripts/schema.mjs';
const spec = () => ({version:1,title:'Service inventory',description:'Draft',acceptResponses:false,questions:[
  {id:'support',title:'Is support available?',type:'choice',required:true,options:['Yes','No'],branches:{No:'contact'}},
  {id:'details',title:'Describe support',type:'text',required:true,longAnswer:true},
  {id:'contact',title:'Contact',type:'text',required:true}
]});
test('accepts forward branches and preserves option order and original text',()=>{
 const s=spec(); assert.deepEqual(validateSpec(s),s);assert.deepEqual(reachableQuestions(s),['support','details','contact']);
});
test('rejects missing and backward branch targets before any authoring',()=>{
 for(const target of ['missing','support']){const s=spec();s.questions[0].branches.No=target;assert.throws(()=>validateSpec(s),{code:'invalid_branch'});}
});
test('refuses open response collection, unsupported settings and repeated IDs',()=>{
 const s=spec();s.acceptResponses=true;assert.throws(()=>validateSpec(s));
 const u=spec();u.shareWith='everyone';assert.throws(()=>validateSpec(u));
 const v=spec();v.questions[2].id='details';assert.throws(()=>validateSpec(v));
});
test('refuses multiple-choice branching and misspelled option labels',()=>{
 const s=spec();s.questions[0].multiple=true;assert.throws(()=>validateSpec(s));
 const u=spec();u.questions[0].branches.Maybe='contact';assert.throws(()=>validateSpec(u));
});
test('hash ignores object key order but detects wording and option ordering changes',()=>{
 assert.equal(digest({a:1,b:2}),digest({b:2,a:1}));
 const s=spec(),u=spec();u.questions[0].options.reverse();assert.notEqual(digest(s),digest(u));
});
