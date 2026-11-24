'use strict';
// Document contents are data. This bridge exposes only read, guarded replacement and startup setup.
(async () => {
  const status = document.getElementById('status');
  const token = window.agentHandsRunToken;
  if (!token) { status.textContent = 'Waiting for the private Agent Hands browser. Your ordinary browser cannot receive commands from this bridge.'; return; }
  const headers = {'X-Agent-Hands': token, 'Content-Type': 'application/json'};
  const request = async (route, body) => {
    const result = await fetch(`./${route}`, {method: body ? 'POST' : 'GET', headers, ...(body ? {body: JSON.stringify(body)} : {}), cache: 'no-store'});
    if (!result.ok) throw new Error('Local bridge refused the request');
    return result.json();
  };
  const cfg = await request('config');
  function refuse(code) { throw Object.assign(new Error(code), {code}); }
  const properties = () => new Promise((resolve, reject) => Office.context.document.getFilePropertiesAsync(result => result.status === Office.AsyncResultStatus.Succeeded ? resolve(result.value) : reject(new Error('Document identity unavailable'))));
  async function checkTarget() {
    const props = await properties(), url = new URL(props.url);
    const guid = (url.searchParams.get('sourcedoc') || '').replace(/[{}]/g, '').toLowerCase();
    if (url.origin !== cfg.target.origin || !(cfg.target.guid && url.pathname.endsWith('/Doc.aspx') && guid === cfg.target.guid || decodeURIComponent(url.pathname) === (cfg.target.canonicalPath || (!cfg.target.guid && cfg.target.pathname)))) refuse('target_mismatch');
    return props.url;
  }
  const saveSettings = () => new Promise((resolve, reject) => Office.context.document.settings.saveAsync(result => result.status === Office.AsyncResultStatus.Succeeded ? resolve() : reject(new Error('Startup save failed'))));
  const refreshSettings = () => new Promise((resolve, reject) => Office.context.document.settings.refreshAsync(result => result.status === Office.AsyncResultStatus.Succeeded ? resolve() : reject(new Error('Startup readback failed'))));
  async function execute(job) {
    let dispatched = false;
    try {
      await checkTarget();
      if (!Office.context.requirements.isSetSupported('WordApi', '1.3')) refuse('word_api_unavailable');
      const result = await Word.run(async context => {
        const body = context.document.body;
        const paragraphs = body.paragraphs;
        paragraphs.load('items/text');
        await context.sync();
        const text = paragraphs.items.map(p => p.text);
        if (text.join('').length > cfg.maxText) refuse('document_too_large');
        if (job.action === 'read') return {status: 'read_ok', paragraphs: text};
        if (Office.context.document.mode !== Office.DocumentMode.ReadWrite) refuse('read_only');
        if (job.action === 'enable-startup') {
          if (!Office.context.requirements.isSetSupported('AddinCommands', '1.1')) refuse('commands_unavailable');
          Office.context.document.settings.set('Office.AutoShowTaskpaneWithDocument', true);
          dispatched = true;
          await saveSettings();
          context.document.save(); await context.sync(); await refreshSettings();
          if (Office.context.document.settings.get('Office.AutoShowTaskpaneWithDocument') !== true) refuse('startup_unverified');
          return {status: 'startup_saved'};
        }
        if (job.action === 'replace-tail') {
          const edit=job.edit;
          const normalized=values=>values.map(v=>v.replace(/[\r\f]/g,'').replace(/\v/g,'\n').replace(/\u00a0/g,' ')).filter(v=>v.trim());
          const same=(a,b)=>JSON.stringify(normalized(a))===JSON.stringify(normalized(b));
          if(!edit || edit.kind!=='replace-tail' || !Array.isArray(edit.before) || !Array.isArray(edit.after) || !Array.isArray(edit.replacements) || edit.replacements.length>5 || typeof edit.anchor!=='string' || !edit.anchor || typeof edit.label!=='string' || !edit.label)refuse('unsupported_edit');
          let url;try{url=new URL(edit.url);}catch{refuse('unsupported_edit');}
          if(url.protocol!=='https:'||url.username||url.password||!same(text,edit.before))refuse('stale_or_unsupported_edit');
          let index=text.indexOf(edit.anchor);
          if(index<1 || text.lastIndexOf(edit.anchor)!==index)refuse('ambiguous_anchor');
          for(const replacement of edit.replacements)if(typeof replacement.before!=='string'||typeof replacement.after!=='string'||replacement.after.length>4000||/[\x00-\x1f]/.test(replacement.after)||text.slice(0,index).filter(v=>v===replacement.before).length!==1)refuse('stale_preview');
          // Remove empty paragraph breaks immediately before the heading as part of the reviewed tail.
          while(index>0 && !text[index-1].trim())index--;
          await checkTarget();paragraphs.load('items/text');await context.sync();
          if(!same(paragraphs.items.map(p=>p.text),edit.before))refuse('stale_preview');
          const escape=value=>value.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
          const tail=paragraphs.items[index].getRange(Word.RangeLocation.start).expandTo(body.getRange(Word.RangeLocation.end));
          dispatched=true;
          for(const replacement of edit.replacements)paragraphs.items.find(p=>p.text===replacement.before).getRange(Word.RangeLocation.content).insertText(replacement.after,Word.InsertLocation.replace);
          tail.insertHtml(`<p><a href="${escape(edit.url)}">${escape(edit.label)}</a></p>`,Word.InsertLocation.replace);
          await context.sync();context.document.save();await context.sync();paragraphs.load('items/text');await context.sync();
          if(!same(paragraphs.items.map(p=>p.text),edit.after))refuse('session_result_unverified');
          return {status:'save_returned'};
        }
        if (job.action !== 'replace') refuse('unsupported_operation');
        const edit = job.edit;
        if (!edit || typeof edit.find !== 'string' || !edit.find || edit.find.length > 255 || /[\x00-\x1f^]/.test(edit.find) || typeof edit.replacement !== 'string' || edit.replacement.length > 4000 || /[\x00-\x1f]/.test(edit.replacement)) refuse('unsupported_edit');
        if (text.filter(t => t === edit.before).length !== 1 || text.join('\n').split(edit.find).length !== 2 || text.includes(edit.after)) refuse('stale_preview');
        const matches = body.search(edit.find, {matchCase: true, matchWholeWord: false, matchWildcards: false, ignorePunct: false, ignoreSpace: false});
        matches.load('items/text'); await context.sync();
        if (matches.items.length !== 1 || matches.items[0].text !== edit.find) refuse('ambiguous_anchor');
        const range = matches.items[0], enclosing = range.paragraphs;
        enclosing.load('items/text');
        const table = range.parentTableOrNullObject;
        table.load('rowCount');
        await context.sync();
        if (enclosing.items.length !== 1 || enclosing.items[0].text !== edit.before || !table.isNullObject) refuse('stale_or_unsupported_paragraph');
        await checkTarget();
        // Office.js has no atomic compare-and-replace operation. Recheck immediately before mutation and verify afterward; do not claim protection against every same-range race.
        enclosing.load('items/text'); await context.sync();
        if (enclosing.items[0].text !== edit.before) refuse('stale_preview');
        dispatched = true;
        range.insertText(edit.replacement, Word.InsertLocation.replace);
        await context.sync();
        context.document.save(); await context.sync();
        paragraphs.load('items/text'); await context.sync();
        const after = paragraphs.items.map(p => p.text);
        if (after.filter(t => t === edit.after).length !== 1 || after.includes(edit.before)) refuse('session_result_unverified');
        return {status: 'save_returned', targetParagraph: edit.after};
      });
      return {id: job.id, ...result};
    } catch (error) { return {id: job.id, status: dispatched ? 'uncertain_after_dispatch' : 'refused_before_mutation', code: error.code || 'office_error'}; }
  }
  await Office.onReady();
  try {
    if (Office.context.host !== 'Word' || Office.context.platform !== 'OfficeOnline') refuse('unsupported_host');
    await request('report', {id: 'ready', host: Office.context.host, platform: Office.context.platform, url: await checkTarget(), automaticStartup: Office.context.document.settings.get('Office.AutoShowTaskpaneWithDocument') === true});
    status.textContent = 'Connected. Waiting for a bounded Agent Hands command.';
    while (true) {
      const job = await request('next');
      if (job) {
        const result = await execute(job);
        status.textContent = JSON.stringify({status: result.status, code: result.code}, null, 2);
        await request('report', result);
      }
      await new Promise(resolve => setTimeout(resolve, 500));
    }
  } catch { status.textContent = 'Bridge disconnected or document identity refused. No further commands will run.'; }
})().catch(() => { document.getElementById('status').textContent = 'The Agent Hands bridge is unavailable.'; });
