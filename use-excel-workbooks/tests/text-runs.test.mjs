import test from 'node:test';
import assert from 'node:assert/strict';
import {createTextRunAdapter,validateRuns,validateRequest,sameColoredText} from '../officejs/text-runs.mjs';
const proposed=[{text:'Old ',font:{color:'#C00000'}},{text:'New',font:{color:'#008000'}}];
function host(options={}) {
 let state={text:'Old',runs:[{text:'Old',font:{color:'#000000'}}]},writes=0,syncs=0;
 const range={load(){},get values(){return [[state.text]];},get formulas(){return [[options.formula || state.text]];},get valueTypes(){return [[options.type||'String']];},getCellProperties(){return {value:[[{textRuns:structuredClone(state.runs)}]]};},getMergedAreasOrNullObject(){return {load(){},isNullObject:!options.merged};},setCellProperties(data){writes++;state.runs=structuredClone(data[0][0].textRuns);state.text=state.runs.map(r=>r.text).join('');if(options.mismatch)state.runs[0].font.color='#000000';}};
 const context={sync:async()=>{syncs++;if(options.failAfterWrite&&writes)throw Error('transport');},workbook:{worksheets:{getItem(name){return {id:'sheet-id',name,load(){},getRange(){return range;}};}}}};
 const Office={context:{requirements:{isSetSupported:()=>!options.unsupported},document:{mode:options.readOnly?'ReadOnly':'ReadWrite'}},DocumentMode:{ReadWrite:'ReadWrite'}};
 const adapter=createTextRunAdapter({run:fn=>fn(context)},Office,async()=>{if(options.wrongTarget)throw Object.assign(Error(),{code:'target_mismatch'});});
 return {adapter,writes:()=>writes,change:()=>{state.text='Concurrent edit';state.runs=[{text:state.text,font:{color:'#000000'}}];}};
}
const request={sheet:'Review',cell:'B2'};
async function plan(h) {const {status,...rest}=await h.adapter.read(request);return {...request,expected:rest,runs:proposed};}
test('writes only textRuns and reads back colors without claiming cloud persistence',async()=>{const h=host(),p=await plan(h),r=await h.adapter.write(p);assert.equal(r.status,'session_runs_verified');assert.equal(r.savedFileVerified,false);assert.equal(h.writes(),1);});
test('stale text refuses before mutation',async()=>{const h=host(),p=await plan(h);h.change();assert.equal((await h.adapter.write(p)).code,'stale_preview');assert.equal(h.writes(),0);});
for(const [options,code] of [[{formula:'=SUM(A1:A2)'},'formula_cell_refused'],[{type:'Double'},'non_text_cell_refused'],[{merged:true},'merged_cell_unsupported'],[{unsupported:true},'excel_api_1_18_required'],[{wrongTarget:true},'target_mismatch']])test(code,async()=>{const h=host(options);assert.equal((await h.adapter.read(request)).code,code);assert.equal(h.writes(),0);});
test('read-only refuses writes',async()=>{const h=host({readOnly:true});assert.equal((await h.adapter.write(await plan(h))).code,'read_only');assert.equal(h.writes(),0);});
for(const options of [{mismatch:true},{failAfterWrite:true}])test('post-dispatch failures are uncertain and never retried '+JSON.stringify(options),async()=>{const h=host(options);assert.equal((await h.adapter.write(await plan(h))).status,'uncertain_after_dispatch');assert.equal(h.writes(),1);});
test('bound ranges, text and font requests',()=>{for(const cell of ['A0','XFE1','A1048577','A1:B2'])assert.throws(()=>validateRequest({...request,cell}));assert.throws(()=>validateRuns([{text:'Old',font:{color:'#C00000',strikethrough:true}}]));assert.throws(()=>validateRuns([{text:'x'.repeat(32768),font:{color:'#000000'}}]));});
test('equivalent segmentation is accepted; lost color is rejected',()=>{assert.ok(sameColoredText([{text:'O',font:{color:'#C00000'}},{text:'ld ',font:{color:'#c00000'}},proposed[1]],proposed));assert.ok(!sameColoredText([{text:'Old New',font:{color:'#000000'}}],proposed));});
