import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {execFileSync} from 'node:child_process';
import {createRequire} from 'node:module';
const {zipSync,strToU8}=createRequire(new URL('../../use-word-documents/package.json',import.meta.url))('fflate');
const ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main';
function read(cell,extra={}){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'excel-runs-test-'));try{
 const entries={...extra,
 'xl/workbook.xml':`<workbook xmlns="${ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Review" r:id="r1"/></sheets></workbook>`,
 'xl/_rels/workbook.xml.rels':'<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>',
 'xl/worksheets/sheet1.xml':`<worksheet xmlns="${ns}"><sheetData><row r="2">${cell}</row></sheetData></worksheet>`};
 const file=path.join(dir,'test.xlsx');fs.writeFileSync(file,zipSync(Object.fromEntries(Object.entries(entries).map(([k,v])=>[k,strToU8(v)]))));
 return JSON.parse(execFileSync('python3',[new URL('../live/readback.py',import.meta.url).pathname,file,'Review','B2'],{encoding:'utf8'}));
}finally{fs.rmSync(dir,{recursive:true,force:true});}}
test('download verifier detects explicit saved run colors',()=>{const r=read('<c r="B2" t="inlineStr"><is><r><rPr><color rgb="FFC00000"/></rPr><t>Old</t></r><r><rPr><color rgb="FF008000"/></rPr><t>New</t></r></is></c>');assert.deepEqual(r,{text:'OldNew',runs:[{text:'Old',font:{color:'#C00000'}},{text:'New',font:{color:'#008000'}}],formula:false});});
test('download verifier exposes plain-text flattening and formulas',()=>{assert.deepEqual(read('<c r="B2" t="inlineStr"><is><t>OldNew</t></is></c>').runs,[]);assert.equal(read('<c r="B2"><f>1+1</f></c>').formula,true);});

test('download verifier resolves inherited cell font when Excel omits the first run color',()=>{const styles=`<styleSheet xmlns="${ns}"><fonts><font><color rgb="FFC00000"/></font></fonts><cellXfs><xf fontId="0"/></cellXfs></styleSheet>`;const r=read('<c r="B2" t="inlineStr"><is><r><t>Old</t></r><r><rPr><color rgb="FF008000"/></rPr><t>New</t></r></is></c>',{'xl/styles.xml':styles});assert.equal(r.runs[0].font.color,'#C00000');assert.equal(r.runs[1].font.color,'#008000');});
