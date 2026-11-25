// Bounded worksheet presentation changes. The caller owns identity, preview, dispatch and saved-file verification.
const fail = code => { throw Object.assign(new Error(code), {code}); };
const keys = (x, allowed) => x && typeof x === 'object' && !Array.isArray(x) && Object.keys(x).every(k => allowed.includes(k));
const color = x => /^#[0-9A-Fa-f]{6}$/.test(x);
export function validateLayout(spec) {
  if (!keys(spec, ['sheets','ranges','tables','cells']) || !Array.isArray(spec.sheets) || spec.sheets.length > 40 || !Array.isArray(spec.ranges) || spec.ranges.length > 200 || !Array.isArray(spec.tables) || spec.tables.length > 40 || !Array.isArray(spec.cells) || spec.cells.length > 200) fail('invalid_layout');
  const name = x => typeof x === 'string' && x.length > 0 && x.length <= 31;
  const address = x => typeof x === 'string' && /^[A-Z]{1,3}[1-9][0-9]{0,6}(?::[A-Z]{1,3}[1-9][0-9]{0,6})?$/.test(x);
  const seen = new Set();
  for (const x of spec.sheets) {
    if (!keys(x,['sheet','position','tabColor','freeze']) || !name(x.sheet) || seen.has(x.sheet) || (x.position !== undefined && (!Number.isInteger(x.position) || x.position < 0 || x.position >= 40)) || (x.tabColor !== undefined && !color(x.tabColor)) || (x.freeze !== undefined && (x.freeze !== null && (!address(x.freeze) || x.freeze.includes(':'))))) fail('invalid_sheet_layout');
    seen.add(x.sheet);
  }
  for (const x of spec.ranges) {
    if (!keys(x,['sheet','range','fill','font','wrapText','rowHeight','columnWidth','verticalAlignment','horizontalAlignment','unmerge','autofitRows']) || !name(x.sheet) || !address(x.range)) fail('invalid_range_layout');
    for(const k of ['unmerge','autofitRows'])if(x[k]!==undefined&&typeof x[k]!=='boolean')fail('invalid_range_layout');
    if (x.fill !== undefined && x.fill !== null && !color(x.fill)) fail('invalid_fill');
    if (x.font !== undefined && (!keys(x.font,['name','size','bold','italic','color','strikethrough']) || (x.font.color !== undefined && !color(x.font.color)) || (x.font.name !== undefined && !['Arial','Aptos','Calibri'].includes(x.font.name)) || (x.font.size !== undefined && (!Number.isFinite(x.font.size) || x.font.size < 8 || x.font.size > 36)) || ['bold','italic','strikethrough'].some(k => x.font[k] !== undefined && typeof x.font[k] !== 'boolean'))) fail('invalid_font');
    if (x.wrapText !== undefined && typeof x.wrapText !== 'boolean') fail('invalid_wrap');
    for (const k of ['rowHeight','columnWidth']) if (x[k] !== undefined && (!Number.isFinite(x[k]) || x[k] < 8 || x[k] > 600)) fail('invalid_dimension');
    if (x.verticalAlignment !== undefined && !['Top','Center','Bottom'].includes(x.verticalAlignment)) fail('invalid_alignment');
    if (x.horizontalAlignment !== undefined && !['Left','Center','Right'].includes(x.horizontalAlignment)) fail('invalid_alignment');
  }
  for (const x of spec.tables) {
    if (!keys(x,['name','style','bandedRows','removeColumns','removeRows','renameColumns']) || !/^[A-Za-z_][A-Za-z0-9_]{0,254}$/.test(x.name) || !/^TableStyle(Light|Medium)[1-9][0-9]?$/.test(x.style) || typeof x.bandedRows !== 'boolean') fail('invalid_table_layout');
    if(x.renameColumns!==undefined&&(!Array.isArray(x.renameColumns)||x.renameColumns.length>10||x.renameColumns.some(c=>!c||Object.keys(c).some(k=>!['before','after'].includes(k))||['before','after'].some(k=>typeof c[k]!=='string'||!c[k]||c[k].length>255))||new Set(x.renameColumns.map(c=>c.before)).size!==x.renameColumns.length||new Set(x.renameColumns.map(c=>c.after)).size!==x.renameColumns.length))fail('invalid_column_rename');
    if(x.removeColumns!==undefined && (!Array.isArray(x.removeColumns)||x.removeColumns.length>10||new Set(x.removeColumns).size!==x.removeColumns.length||x.removeColumns.some(c=>typeof c!=='string'||!c||c.length>255)))fail('invalid_column_removal');
    if(x.removeRows!==undefined && (!Array.isArray(x.removeRows)||x.removeRows.length>100||new Set(x.removeRows).size!==x.removeRows.length||x.removeRows.some(i=>!Number.isInteger(i)||i<0||i>10000)))fail('invalid_row_removal');
    if(x.removeColumns?.length&&x.removeRows?.length)fail('mixed_table_removal');
  }
  for (const x of spec.cells) if (!keys(x,['sheet','cell','before','after']) || !name(x.sheet) || !address(x.cell) || x.cell.includes(':') || typeof x.before !== 'string' || typeof x.after !== 'string' || x.after.length > 32767 || /^[=+@]/.test(x.after)) fail('invalid_text_cell');
  return spec;
}
export function createLayoutAdapter(Excel,Office,guard) {
  return async(action,request) => {
    let dispatched = false;
    try {
      const spec = validateLayout(request.spec);
      await guard();
      if (!Office.context.requirements.isSetSupported('ExcelApi','1.9')) fail('excel_api_1_9_required');
      if(spec.tables.some(t=>t.removeRows?.length)&&!Office.context.requirements.isSetSupported('ExcelApiOnline','1.1'))fail('excel_online_row_api_required');
      if (!['layout-read','layout-apply'].includes(action)) fail('unsupported_operation');
      if (action === 'layout-apply' && Office.context.document.mode !== 'readWrite') fail('read_only');
      return await Excel.run(async context => {
        const all = context.workbook.worksheets; all.load('items/name,items/position,items/tabColor');
        const ranges = spec.ranges.map(x => { const r = all.getItem(x.sheet).getRange(x.range); r.load('values,formulas,cellCount'); return r; });
        const cells = spec.cells.map(x => { const r = all.getItem(x.sheet).getRange(x.cell); r.load('values,formulas'); return r; });
        const tables = spec.tables.map(x => { const t = context.workbook.tables.getItem(x.name); t.load('name,style,showBandedRows'); return t; });
        const tableRanges=spec.tables.map((x,i)=>{if(!x.removeColumns?.length&&!x.removeRows?.length&&!x.renameColumns?.length)return null;const r=tables[i].getRange();r.load('values,formulas,cellCount,rowIndex,columnIndex,rowCount,columnCount');return r;});
        const usedRanges=tableRanges.map((r,i)=>{if(!r)return null;const u=tables[i].worksheet.getUsedRange();u.load('values,formulas,rowIndex,columnIndex,cellCount');return u;});
        await context.sync();
        for(let i=0;i<tableRanges.length;i++)if(tableRanges[i]){const r=tableRanges[i],x=spec.tables[i];if(r.cellCount>20000)fail('table_too_large');if(x.renameColumns?.some(c=>!r.values[0].includes(c.before)||r.values[0].includes(c.after)))fail('invalid_column_rename');if(x.removeColumns?.some(c=>!r.values[0].includes(c))||x.removeColumns?.length>=r.values[0].length||(x.removeRows?.length>=r.values.length-1)||x.removeRows?.some(n=>n>=r.values.length-1))fail('missing_table_member');}
        for(let i=0;i<tableRanges.length;i++)if(tableRanges[i]){
          const r=tableRanges[i],u=usedRanges[i],x=spec.tables[i];if(u.cellCount>100000)fail('sheet_too_large');
          for(let row=0;row<u.values.length;row++)for(let col=0;col<u.values[row].length;col++){
            const ri=u.rowIndex+row,ci=u.columnIndex+col,occupied=u.values[row][col]!==''||String(u.formulas[row][col]).startsWith('=');
            if(occupied&&((x.removeColumns?.length&&ri>=r.rowIndex&&ri<r.rowIndex+r.rowCount&&ci>=r.columnIndex+r.columnCount)||(x.removeRows?.length&&ci>=r.columnIndex&&ci<r.columnIndex+r.columnCount&&ri>=r.rowIndex+r.rowCount)))fail('adjacent_cells_would_shift');
          }
        }
        if (ranges.reduce((n,r) => n+r.cellCount,0) > 100000) fail('layout_too_large');
        for (const x of spec.sheets) if (!all.items.some(s => s.name === x.sheet) || (x.position !== undefined && x.position >= all.items.length)) fail('missing_sheet');
        for (let i=0;i<cells.length;i++) if (cells[i].values[0][0] !== spec.cells[i].before || String(cells[i].formulas[0][0]).startsWith('=')) fail('stale_or_formula_cell');
        const digests=await Promise.all(ranges.map(async r=>{const bytes=new TextEncoder().encode(JSON.stringify({values:r.values,formulas:r.formulas}));const digest=await crypto.subtle.digest('SHA-256',bytes);return [...new Uint8Array(digest)].map(b=>b.toString(16).padStart(2,'0')).join('');}));
        const snapshot = {sheets:all.items.map(s => ({name:s.name,position:s.position,tabColor:s.tabColor})),ranges:digests,cells:cells.map(r=>r.values),tables:tables.map(t=>({name:t.name,style:t.style,bandedRows:t.showBandedRows}))};
        snapshot.tableContents=tableRanges.map(r=>r?{values:r.values,formulas:r.formulas}:null);
        if (action === 'layout-read') return {status:'layout_ready',snapshot};
        if (JSON.stringify(snapshot) !== JSON.stringify(request.expected)) fail('stale_preview');
        await guard(); dispatched=true;
        for (const x of [...spec.sheets].sort((a,b)=>(a.position??100)-(b.position??100))) {
          const s = all.getItem(x.sheet);
          if (x.position !== undefined) s.position=x.position;
          if (x.tabColor !== undefined) s.tabColor=x.tabColor;
          if (x.freeze !== undefined) { s.freezePanes.unfreeze(); if (x.freeze) s.freezePanes.freezeAt(s.getRange(x.freeze)); }
        }
        for (let i=0;i<spec.ranges.length;i++) {
          const x=spec.ranges[i],f=ranges[i].format;
          if(x.unmerge)ranges[i].unmerge();
          if (x.fill === null) f.fill.clear(); else if (x.fill !== undefined) f.fill.color=x.fill;
          if (x.font) f.font.set(x.font);
          for (const k of ['wrapText','rowHeight','columnWidth','verticalAlignment','horizontalAlignment']) if (x[k] !== undefined) f[k]=x[k];
          if(x.autofitRows)f.autofitRows();
        }
        for (let i=0;i<tables.length;i++) { tables[i].style=spec.tables[i].style; tables[i].showBandedRows=spec.tables[i].bandedRows; }
        for (let i=0;i<cells.length;i++) cells[i].values=[[spec.cells[i].after]];
        for(let i=0;i<tables.length;i++){
          const x=spec.tables[i];
          for(const c of x.renameColumns||[])tables[i].columns.getItem(c.before).name=c.after;
          for(const col of x.removeColumns||[])tables[i].columns.getItem(col).delete();
          for(const index of [...(x.removeRows||[])].sort((a,b)=>b-a))tables[i].rows.deleteRowsAt(index,1);
        }
        await context.sync(); context.workbook.save(Excel.SaveBehavior.save); await context.sync();
        return {status:'layout_save_returned',savedFileVerified:false};
      });
    } catch(e) { return {status:dispatched?'uncertain_after_dispatch':'refused_before_mutation',code:e.code||'office_error'}; }
  };
}
