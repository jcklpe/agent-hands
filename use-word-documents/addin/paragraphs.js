// Shared by the bounded CLI and add-in. No document-provided code is executed.
globalThis.AgentHandsParagraphs = (() => {
  const fail = code => { throw Object.assign(new Error(code), {code}); };
  function validate(spec) {
    if (!spec || Object.keys(spec).some(k=>!['paragraphs','links','append','resolveComments','acceptInsertions','replaceBody'].includes(k)) || !Array.isArray(spec.paragraphs) || spec.paragraphs.length>500 || !Array.isArray(spec.links) || spec.links.length>100 || !Array.isArray(spec.append) || spec.append.length>80) fail('invalid_paragraph_spec');
    if(spec.resolveComments!==undefined && (!Array.isArray(spec.resolveComments)||spec.resolveComments.length>30||new Set(spec.resolveComments.map(c=>c.id)).size!==spec.resolveComments.length||spec.resolveComments.some(c=>!c||Object.keys(c).some(k=>!['id','content','authorName'].includes(k))||['id','content','authorName'].some(k=>typeof c[k]!=='string'||!c[k]||c[k].length>12000))))fail('invalid_comment_resolution');
    if(spec.acceptInsertions!==undefined && (!Array.isArray(spec.acceptInsertions)||!spec.acceptInsertions.length||spec.acceptInsertions.length>20||spec.acceptInsertions.some(x=>!x||Object.keys(x).some(k=>!['id','author','date','text'].includes(k))||['id','author','date','text'].some(k=>typeof x[k]!=='string')||!x.id||!x.author||!Number.isFinite(Date.parse(x.date))||x.text.length>12000)||new Set(spec.acceptInsertions.map(x=>x.id)).size!==spec.acceptInsertions.length))fail('invalid_insertion_acceptance');
    if(spec.replaceBody!==undefined && (!Array.isArray(spec.replaceBody)||!spec.replaceBody.length||spec.replaceBody.length>80||spec.replaceBody.some(x=>!x||Object.keys(x).some(k=>!['text','format'].includes(k))||typeof x.text!=='string'||!x.text||x.text.length>12000||/[\x00-\x1f]/.test(x.text))))fail('invalid_body_replacement');
    if((spec.acceptInsertions||spec.replaceBody)&&(spec.paragraphs.length||spec.links.length||spec.append.length||spec.resolveComments?.length||(spec.acceptInsertions&&spec.replaceBody)))fail('mixed_structural_edit');
    const seen=new Set();
    const style=x=>{
      if (!x || Object.keys(x).some(k=>!['style','size','bold','spaceBefore','spaceAfter','keepWithNext','pageBreakBefore'].includes(k)) || !['Normal','Title','Subtitle','Heading1','Heading2','Heading3','Caption'].includes(x.style)) fail('invalid_paragraph_style');
      for(const k of ['size','spaceBefore','spaceAfter']) if(x[k]!==undefined&&(!Number.isFinite(x[k])||x[k]<0||x[k]>36))fail('invalid_paragraph_style');
      for(const k of ['bold','keepWithNext','pageBreakBefore'])if(x[k]!==undefined&&typeof x[k]!=='boolean')fail('invalid_paragraph_style');
    };
    for(const x of spec.replaceBody||[])style(x.format);
    for(const p of spec.paragraphs) {
      if(!p || Object.keys(p).some(k=>!['index','before','after','format'].includes(k)) || !Number.isInteger(p.index)||p.index<0||p.index>10000||seen.has(p.index)||typeof p.before!=='string'||(p.after!==undefined&&(typeof p.after!=='string'||p.after.length>12000||/[\x00-\x08\x0b-\x1f]/.test(p.after))))fail('invalid_paragraph_edit');
      seen.add(p.index);if(p.format)style(p.format);
    }
    for(const x of spec.append) {if(!x||Object.keys(x).some(k=>!['text','format'].includes(k))||typeof x.text!=='string'||!x.text||x.text.length>12000||/[\x00-\x1f]/.test(x.text))fail('invalid_append');style(x.format);}
    for(const l of spec.links) {if(!l||Object.keys(l).some(k=>!['before','after'].includes(k)))fail('invalid_link');const a=new URL(l.before),b=new URL(l.after);if(a.protocol!=='https:'||b.protocol!=='https:'||a.origin!==b.origin||a.username||a.password||b.username||b.password||l.before===l.after)fail('invalid_link');}
    return spec;
  }
  const normalize = x=>x.replace(/[\r\f\u0005]/g,'').replace(/\v/g,'\n').replace(/\u00a0/g,' ');
  async function run(context,job,Word,guard) {
    let dispatched=false;
    try {
      const spec=validate(job.spec), paragraphs=context.document.body.paragraphs;
      paragraphs.load('items/text');context.document.load('changeTrackingMode');await context.sync();
      const before=paragraphs.items.map(p=>p.text);
      if(context.document.changeTrackingMode!=='Off')fail('tracking_enabled');
      if(JSON.stringify(before.map(normalize))!==JSON.stringify(job.before.map(normalize)))fail('stale_preview');
      const accepted=[];
      if(spec.acceptInsertions?.length){
        const changes=context.document.body.getTrackedChanges();changes.load('items/author,items/date,items/text,items/type');await context.sync();
        for(const wanted of spec.acceptInsertions){const matches=changes.items.filter(c=>c.type==='Added'&&c.author===wanted.author&&new Date(c.date).getTime()===Date.parse(wanted.date)&&normalize(c.text)===normalize(wanted.text));if(matches.length!==1)fail('stale_insertion');accepted.push(matches[0]);}
      }
      if(spec.replaceBody){const comments=context.document.body.getComments(),changes=context.document.body.getTrackedChanges();comments.load('items/id');changes.load('items/type');await context.sync();if(comments.items.length||changes.items.length)fail('reviewed_body_replacement_refused');}
      const resolved=[];
      if(spec.resolveComments?.length){
        const comments=context.document.body.getComments();comments.load('items/id,items/content,items/authorName,items/resolved');await context.sync();
        for(const requested of spec.resolveComments){const matches=comments.items.filter(c=>normalize(c.content).replace(/\s/g,'')===normalize(requested.content).replace(/\s/g,'')&&c.authorName===requested.authorName);if(matches.length!==1||matches[0].resolved)fail('stale_comment');resolved.push(matches[0]);}
      }
      const targets=[], replacements=[];
      for(const edit of spec.paragraphs) {
        const p=paragraphs.items[edit.index];if(!p||normalize(p.text)!==normalize(edit.before))fail('stale_paragraph');
        if(edit.after!==undefined && edit.after!==edit.before) {
          const oldText=edit.before.replace(/[\r\f\u0005]/g,'').replace(/\v/g,'\n'),newText=edit.after.replace(/[\r\f\u0005]/g,'').replace(/\v/g,'\n');let left=0,right=0;
          while(left<oldText.length&&left<newText.length&&oldText[left]===newText[left])left++;
          while(right<oldText.length-left&&right<newText.length-left&&oldText.at(-1-right)===newText.at(-1-right))right++;
          // Anchor a pure insertion to an adjacent literal character so Word search stays bounded and nonempty.
          if(left+right===oldText.length&&oldText.length){if(left>0)left-= /[\uDC00-\uDFFF]/.test(oldText[left-1])?2:1;else right-= /[\uD800-\uDBFF]/.test(oldText[0])?2:1;}
          // Retain enough surrounding literal text to identify a small insertion/deletion uniquely within its paragraph.
          while(oldText.split(oldText.slice(left,oldText.length-right)).length!==2 && (left||right)) {if(left)left=Math.max(0,left-16);else right=Math.max(0,right-16);}
          const find=oldText.slice(left,oldText.length-right),replacement=newText.slice(left,newText.length-right);
          const comments=p.getComments();comments.load('items/id');
          const changes=p.getRange('Content').getTrackedChanges();changes.load('items/type');
          await context.sync();if(changes.items.length)fail('revision_in_changed_paragraph');
          if(comments.items.length && left+right<2)fail('comment_boundary_replacement_refused_'+edit.index);
          if(!find)fail('empty_search_unsupported');
          const searchText=find.replace(/\^/g,'^^').replace(/\n/g,'^l').replace(/\t/g,'^t');
          if(find.includes('\n') && !comments.items.length) {
            replacements.push({range:p.getRange('Content'),text:edit.after});
          } else if(find.includes('\n')) {
            // Word Online search does not consistently match manual line breaks. Search literal endpoints, then verify the complete expanded span before any dispatch.
            const lines=find.split('\n'),head=lines[0],tail=lines.at(-1);
            if(!head||!tail||head.length>255||tail.length>255)fail('unsupported_line_break_span_'+edit.index);
            const opts={matchCase:true,matchWildcards:false,matchWholeWord:false,ignorePunct:false,ignoreSpace:false};
            const a=p.getRange('Content').search(head.replace(/\^/g,'^^'),opts),b=p.getRange('Content').search(tail.replace(/\^/g,'^^'),opts);
            a.load('items/text');b.load('items/text');await context.sync();
            if(a.items.length!==1||b.items.length!==1)fail('ambiguous_edit_'+edit.index);
            const span=a.items[0].expandTo(b.items[0]);span.load('text');await context.sync();
            if(normalize(span.text)!==normalize(find))fail('line_break_span_mismatch');
            replacements.push({range:span,text:replacement});
          } else if(searchText.length<=255) {
            const matches=p.getRange('Content').search(searchText,{matchCase:true,matchWildcards:false,matchWholeWord:false,ignorePunct:false,ignoreSpace:false});matches.load('items/text');await context.sync();
            if(matches.items.length!==1||normalize(matches.items[0].text)!==normalize(find))fail('ambiguous_edit_'+edit.index+'_'+matches.items.length);
            replacements.push({range:matches.items[0],text:replacement});
          } else {
            if(comments.items.length)fail('comment_boundary_replacement_refused_'+edit.index);
            replacements.push({range:p.getRange('Content'),text:edit.after});
          }
        }
        targets.push({p,format:edit.format});
      }
      const links=[];
      if(spec.links.length) {
        const ranges=context.document.body.getRange('Content').getHyperlinkRanges();ranges.load('items/hyperlink');await context.sync();
        for(const l of spec.links) {const matches=ranges.items.filter(r=>r.hyperlink===l.before);if(!matches.length)fail('link_not_found');for(const r of matches)links.push({range:r,address:l.after});}
      }
      await guard();paragraphs.load('items/text');await context.sync();if(JSON.stringify(paragraphs.items.map(p=>normalize(p.text)))!==JSON.stringify(before.map(normalize)))fail('stale_preview');
      if(job.action==='paragraphs-inspect')return {status:'paragraphs_ready',before};
      if(job.action!=='paragraphs-apply')fail('unsupported_operation');
      const format=(p,f)=>{if(!f)return;p.styleBuiltIn=f.style;p.font.name='Aptos';p.font.size=f.size??11;p.font.color='#000000';p.font.bold=f.bold??false;p.font.italic=false;for(const k of ['spaceBefore','spaceAfter','keepWithNext','pageBreakBefore'])if(f[k]!==undefined)p[k]=f[k];};
      dispatched=true;
      if(spec.replaceBody){
        const esc=t=>t.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
        const html=spec.replaceBody.map(x=>{const f=x.format,tag={Title:'h1',Heading1:'h2',Heading2:'h3'}[f.style]||'p';return `<${tag} style="font-family:Aptos;font-size:${f.size??11}pt;color:#000000;font-weight:${f.bold?'bold':'normal'};margin-top:${f.spaceBefore??0}pt;margin-bottom:${f.spaceAfter??6}pt">${esc(x.text)}</${tag}>`;}).join('');
        context.document.body.insertHtml(html,'Replace');
      }
      for(const c of accepted)c.accept();
      for(const r of replacements)r.range.insertText(r.text,'Replace');
      for(const x of targets)format(x.p,x.format);
      for(const l of links)l.range.hyperlink=l.address;
      for(const x of spec.append)format(context.document.body.insertParagraph(x.text,'End'),x.format);
      for(const c of resolved)c.resolved=true;
      await context.sync();context.document.save();await context.sync();
      return {status:'paragraphs_save_returned'};
    }catch(e){return {status:dispatched?'uncertain_after_dispatch':'refused_before_mutation',code:e.code||'office_error'};}
  }
  return {validate,run};
})();
