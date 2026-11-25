import test from 'node:test';
import assert from 'node:assert/strict';
import {validateLayout,createLayoutAdapter} from '../officejs/layout.mjs';
const spec={sheets:[{sheet:'Data',position:0,tabColor:'#E6F1FA',freeze:'B2'}],ranges:[],tables:[],cells:[{sheet:'Data',cell:'A1',before:'Title',after:'Guide'}]};
test('reject unknown operations, unsafe values, duplicate worksheets and unbounded ranges',()=>{
  for(const x of [{...spec,script:'anything'},{...spec,cells:[{...spec.cells[0],after:'=2+2'}]},{...spec,sheets:[...spec.sheets,...spec.sheets]},{...spec,ranges:[{sheet:'Data',range:'A:A'}]}])assert.throws(()=>validateLayout(x));
});
for(const cause of ['formula','stale','readOnly'])test('refuse before writing '+cause,async()=>{
  let writes=0;
  const r={values:[['Title']],formulas:[[cause==='formula'?'=1+1':'Title']],load(){}};
  const s={name:'Data',position:0,tabColor:'#FFFFFF',getRange:()=>r};
  const context={workbook:{worksheets:{items:[s],load(){},getItem:()=>s},tables:{},save(){writes++;}},async sync(){}};
  const adapter=createLayoutAdapter({run:fn=>fn(context)},{context:{requirements:{isSetSupported:()=>true},document:{mode:cause==='readOnly'?'readOnly':'readWrite'}}},async()=>{});
  const result=await adapter('layout-apply',{spec,expected:{}});
  assert.equal(result.status,'refused_before_mutation');assert.equal(writes,0);assert.equal(r.values[0][0],'Title');
});

test('accepted wording can explicitly clear inherited strikethrough',()=>{
  const accepted={...spec,ranges:[{sheet:'Data',range:'A1',font:{color:'#191A22',strikethrough:false}}]};
  assert.equal(validateLayout(accepted).ranges[0].font.strikethrough,false);
  for(const value of ['false',null,0])assert.throws(()=>validateLayout({...accepted,ranges:[{...accepted.ranges[0],font:{strikethrough:value}}]}));
});
