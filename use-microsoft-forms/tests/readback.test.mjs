import test from 'node:test';
import assert from 'node:assert/strict';
import {compareForm,branchLabel} from '../scripts/editor.mjs';
import {validateTarget} from '../scripts/plans.mjs';
const spec={title:'Example',description:'One paragraph.\n\nAnother paragraph.',questions:[{id:'name',title:'Service name',type:'text',required:true},{id:'support',title:'Is support available?',type:'choice',required:false,options:['Yes','No']},{id:'details',title:'Details',type:'text',longAnswer:true,required:false}]};
const actual=()=>({introduction:{title:'Example',description:'One paragraph.\nAnother paragraph.',acceptResponses:false},questions:[{label:'1. Question title Service name Single line text Required to answer',options:[]},{label:'2. Question title Is support available? Single choice',options:['Yes','No']},{label:'3. Question title Details Multi Line Text',options:[]}]});
test('readback accepts observed rich-text whitespace normalization while checking all wording',()=>{compareForm(spec,actual());const a=actual();a.questions[0].label=a.questions[0].label.replace('Service name','Service title');assert.throws(()=>compareForm(spec,a),{code:'question_unverified'});});
test('readback refuses open collection, changed required flags and reordered options',()=>{
 const open=actual();open.introduction.acceptResponses=true;assert.throws(()=>compareForm(spec,open),{code:'introduction_unverified'});
 const flags=actual();flags.questions[0].label=flags.questions[0].label.replace(' Required to answer','');assert.throws(()=>compareForm(spec,flags),{code:'question_unverified'});
 const order=actual();order.questions[1].options.reverse();assert.throws(()=>compareForm(spec,order),{code:'options_unverified'});
});
test('branch display mapping refuses backward targets even when the website offers them',()=>{
 assert.equal(branchLabel(spec.questions,0,'support'),'Next');assert.equal(branchLabel(spec.questions,0,'details'),'3. Details');
 assert.throws(()=>branchLabel(spec.questions,1,'name'),{code:'invalid_branch'});
});
test('target validation refuses external origins, respondent URLs and authentication parameters',()=>{
 validateTarget('https://forms.cloud.microsoft/Pages/DesignPageV2.aspx?subpage=design&id=synthetic');validateTarget(null);
 for(const url of ['https://example.test/Pages/DesignPageV2.aspx?id=x','https://forms.cloud.microsoft/Pages/ResponsePage.aspx?id=x','https://forms.cloud.microsoft/Pages/DesignPageV2.aspx?id=x&state=secret'])assert.throws(()=>validateTarget(url),{code:'invalid_target'});
});
