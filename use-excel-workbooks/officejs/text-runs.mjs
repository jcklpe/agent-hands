// Bounded Office.js adapter. Host transport owns account identity, target identity, dispatch journaling and independent saved-file verification.
export const MAX_RUNS = 128;
const fail = code => { throw Object.assign(new Error(code), {code}); };
export function validateRequest(request) {
  if (!request || typeof request.sheet !== 'string' || !request.sheet || request.sheet.length > 31 || !/^[A-Z]{1,3}[1-9][0-9]{0,6}$/.test(request.cell || '')) fail('invalid_target');
  const [,letters,row]=/^([A-Z]+)([0-9]+)$/.exec(request.cell);
  if ([...letters].reduce((n,c)=>n*26+c.charCodeAt(0)-64,0)>16384 || Number(row)>1048576) fail('invalid_target');
  return request;
}
export function validateRuns(runs) {
  if (!Array.isArray(runs) || !runs.length || runs.length > MAX_RUNS) fail('invalid_runs');
  let length=0;
  for(const run of runs) {
    if (!run || Object.keys(run).some(k=>!['text','font'].includes(k)) || typeof run.text !== 'string' || !run.text.length || /[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(run.text)) fail('invalid_runs');
    length+=run.text.length;
    if (!run.font || Object.keys(run.font).some(k=>k!=='color') || !/^#[a-fA-F0-9]{6}$/.test(run.font.color || '')) fail('unsupported_font');
  }
  if(length>32767)fail('text_too_long');
  return runs.map(r=>({text:r.text,font:{color:r.font.color.toUpperCase()}}));
}
function color(value) {return typeof value==='string'?value.toUpperCase():value;}
export function sameColoredText(actual, expected) {
  // Excel may merge adjacent equivalent runs; compare UTF-16 text and color, not segmentation.
  const flatten=runs=>runs.flatMap(r=>Array.from({length:r.text.length},(_,i)=>[r.text[i],color(r.font?.color)]));
  return JSON.stringify(flatten(actual))===JSON.stringify(flatten(expected));
}
export function createTextRunAdapter(Excel, Office, guardTarget) {
  async function inspect(context, request) {
    validateRequest(request);
    const sheet=context.workbook.worksheets.getItem(request.sheet);
    sheet.load('id,name');
    const range=sheet.getRange(request.cell);
    range.load('values,formulas,valueTypes,address');
    const properties=range.getCellProperties({textRuns:true});
    const merged=range.getMergedAreasOrNullObject();merged.load('isNullObject');
    await context.sync();
    if (!merged.isNullObject) fail('merged_cell_unsupported');
    const value=range.values[0][0], formula=range.formulas[0][0],type=range.valueTypes[0][0];
    // Excel returns constant values in formulas too. Reject actual formulas, numbers, errors and rich data types.
    if (typeof formula==='string' && formula.startsWith('=')) fail('formula_cell_refused');
    if (!['String','Empty'].includes(type)) fail('non_text_cell_refused');
    const runs=properties.value[0][0].textRuns || [];
    const text=value===''?'':value;
    if(typeof text!=='string' || text.length>32767 || runs.map(r=>r.text).join('')!==text) fail('inconsistent_read');
    return {range, snapshot:{sheetId:sheet.id,sheet:sheet.name,cell:request.cell,text,runs:JSON.parse(JSON.stringify(runs))}};
  }
  async function run(action, request) {
    let dispatched=false;
    try {
      validateRequest(request);
      if (!Office.context.requirements.isSetSupported('ExcelApi','1.18')) fail('excel_api_1_18_required');
      await guardTarget();
      return await Excel.run(async context=>{
        const current=await inspect(context,request);
        if(action==='read')return {status:'read_ok',...current.snapshot};
        if(action!=='write')fail('unsupported_operation');
        if(Office.context.document.mode!==Office.DocumentMode.ReadWrite)fail('read_only');
        const runs=validateRuns(request.runs);
        if(JSON.stringify(current.snapshot)!==JSON.stringify(request.expected))fail('stale_preview');
        await guardTarget();
        const rechecked=await inspect(context,request);
        if(JSON.stringify(rechecked.snapshot)!==JSON.stringify(request.expected))fail('stale_preview');
        // This is not an atomic compare-and-set; concurrent same-cell edits remain a race.
        dispatched=true;
        rechecked.range.setCellProperties([[{textRuns:runs}]]);
        await context.sync();
        const after=await inspect(context,request);
        if(!sameColoredText(after.snapshot.runs,runs))fail('session_readback_mismatch');
        return {status:'session_runs_verified',...after.snapshot,savedFileVerified:false};
      });
    } catch(error) {
      return {status:dispatched?'uncertain_after_dispatch':'refused_before_mutation',code:error.code||'office_error',savedFileVerified:false};
    }
  }
  return {read:request=>run('read',request),write:request=>run('write',request)};
}
