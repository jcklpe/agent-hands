'use strict';
// Disposable-presentation probe: fixed commands, exact file identity, bounded text boxes and a guarded substring edit.
(async () => {
  const status = document.getElementById('status'), token = window.agentHandsRunToken;
  if (!token) { status.textContent = 'Waiting for the owned Agent Hands browser.'; return; }
  const headers = {'X-Agent-Hands': token, 'Content-Type': 'application/json'};
  const request = async (route, body) => {
    const response = await fetch(`./${route}`, {method: body ? 'POST' : 'GET', headers, ...(body ? {body: JSON.stringify(body)} : {}), cache: 'no-store'});
    if (!response.ok) throw new Error('Bridge refused');
    return response.json();
  };
  const cfg = await request('config');
  const refuse = code => { throw Object.assign(new Error(code), {code}); };
  const properties = () => new Promise((resolve, reject) => Office.context.document.getFilePropertiesAsync(r => r.status === Office.AsyncResultStatus.Succeeded ? resolve(r.value) : reject(new Error('Identity unavailable'))));
  async function checkTarget() {
    const props = await properties(), url = new URL(props.url);
    const guid = (url.searchParams.get('sourcedoc') || '').replace(/[{}]/g, '').toLowerCase();
    if (url.origin !== cfg.target.origin || !(cfg.target.guid && url.pathname.endsWith('/Doc.aspx') && guid === cfg.target.guid || decodeURIComponent(url.pathname) === cfg.target.canonicalPath)) refuse('target_mismatch');
    return props.url;
  }
  const settingsCall = method => new Promise((resolve, reject) => Office.context.document.settings[method](r => r.status === Office.AsyncResultStatus.Succeeded ? resolve() : reject(new Error('Settings operation failed'))));
  async function read(context) {
    const slides = context.presentation.slides; slides.load('items/id'); await context.sync();
    if (slides.items.length !== 1) refuse('not_disposable_fixture');
    const slide = slides.items[0], shapes = slide.shapes;
    shapes.load('items/id,items/name,items/type'); await context.sync();
    const supportedTypes=[PowerPoint.ShapeType.textBox,PowerPoint.ShapeType.geometricShape];
    if (shapes.items.length !== 5 || shapes.items.some(s => !supportedTypes.includes(s.type))) refuse('unsupported_fixture_shapes');
    for (const shape of shapes.items) shape.textFrame.textRange.load('text');
    await context.sync();
    const result = shapes.items.map(shape => ({slideId:slide.id, shapeId:shape.id, name:shape.name, text:shape.textFrame.textRange.text}));
    if (!result.some(s => s.text === 'Disposable PowerPoint coauthoring test') || !result.some(s => s.text === 'Preservation check: Keep this bold text.')) refuse('not_disposable_fixture');
    if (result.map(s=>s.text).join('').length > cfg.maxText) refuse('presentation_too_large');
    return {result, shapes};
  }
  async function execute(job) {
    let dispatched = false;
    try {
      await checkTarget();
      if (!Office.context.requirements.isSetSupported('PowerPointApi','1.4')) refuse('powerpoint_api_unavailable');
      const outcome = await PowerPoint.run(async context => {
        const {result, shapes} = await read(context);
        if (job.action === 'read') return {status:'read_ok',shapes:result};
        if (Office.context.document.mode !== Office.DocumentMode.ReadWrite) refuse('read_only');
        if (job.action === 'enable-startup') {
          if (!Office.context.requirements.isSetSupported('AddinCommands','1.1')) refuse('commands_unavailable');
          Office.context.document.settings.set('Office.AutoShowTaskpaneWithDocument',true);
          dispatched = true; await settingsCall('saveAsync'); await settingsCall('refreshAsync');
          if (Office.context.document.settings.get('Office.AutoShowTaskpaneWithDocument') !== true) refuse('startup_unverified');
          return {status:'startup_saved'};
        }
        if (job.action !== 'replace') refuse('unsupported_operation');
        const edit = job.edit;
        if (!edit || !['ALPHA','BETA'].includes(edit.name) || typeof edit.find !== 'string' || !edit.find || edit.find.length > 255 || /[\x00-\x1f]/.test(edit.find) || typeof edit.replacement !== 'string' || edit.replacement.length > 1000 || /[\x00-\x1f]/.test(edit.replacement) || edit.replacement === edit.find || edit.after !== edit.before.replace(edit.find,()=>edit.replacement)) refuse('unsupported_edit');
        const selected = result.filter(s => s.slideId === edit.slideId && s.shapeId === edit.shapeId && s.name === edit.name);
        if (selected.length !== 1 || selected[0].text !== edit.before || edit.before.split(edit.find).length !== 2 || result.some(s => s.text === edit.after)) refuse('stale_preview');
        const shape = shapes.items.find(s => s.id === edit.shapeId), range = shape.textFrame.textRange;
        await checkTarget(); range.load('text'); await context.sync();
        if (range.text !== edit.before) refuse('stale_preview');
        dispatched = true;
        range.getSubstring(edit.before.indexOf(edit.find),edit.find.length).text = edit.replacement;
        await context.sync(); range.load('text'); await context.sync();
        if (range.text !== edit.after) refuse('session_result_unverified');
        return {status:'session_text_verified',shapeId:edit.shapeId,text:range.text,cloudPersistence:'requires_independent_download'};
      });
      return {id:job.id,...outcome};
    } catch (error) { return {id:job.id,status:dispatched?'uncertain_after_dispatch':'refused_before_mutation',code:error.code||'office_error',message:String(error.message||'').slice(0,500),...(error.observedShapes?{observedShapes:error.observedShapes,expectedShapeType:error.expectedShapeType}:{})}; }
  }
  await Office.onReady();
  try {
    if (Office.context.host !== 'PowerPoint' || Office.context.platform !== 'OfficeOnline') refuse('unsupported_host');
    await request('report',{id:'ready',host:Office.context.host,platform:Office.context.platform,url:await checkTarget(),automaticStartup:Office.context.document.settings.get('Office.AutoShowTaskpaneWithDocument')===true});
    status.textContent='Connected to the disposable PowerPoint test.';
    while(true) {
      const job=await request('next');
      if(job) {const result=await execute(job);status.textContent=JSON.stringify({status:result.status,code:result.code});await request('report',result);}
      await new Promise(resolve=>setTimeout(resolve,500));
    }
  } catch {status.textContent='Disconnected or target refused.';}
})().catch(()=>{document.getElementById('status').textContent='PowerPoint probe unavailable.';});
