import test from 'node:test';
import assert from 'node:assert/strict';
import {extremePath} from '../scripts/preview-paths.mjs';
const spec={version:1,title:'Example',description:'',acceptResponses:false,questions:[{id:'gate',title:'Details?',type:'choice',required:true,options:['Yes','No'],branches:{Yes:'details',No:'contact'}},{id:'details',title:'Describe',type:'text',required:true},{id:'contact',title:'Contact',type:'text',required:true}]};
test('preview paths derive followups from supplied data without domain-specific rules',()=>{
 assert.deepEqual(extremePath(spec,'more').visited,[0,1,2]);assert.deepEqual(extremePath(spec,'fewer').visited,[0,2]);assert.equal(extremePath(spec,'fewer').choices[0].option,'No');
});
test('end destinations stop the simulated path without a response submission',()=>{
 const s=structuredClone(spec);s.questions[0].branches.No='end';assert.deepEqual(extremePath(s,'fewer').visited,[0]);
});
