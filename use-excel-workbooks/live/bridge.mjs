import fs from 'node:fs';
import https from 'node:https';
import path from 'node:path';
import {randomBytes, randomUUID, timingSafeEqual} from 'node:crypto';
import {createRequire} from 'node:module';
const {zlibSync} = createRequire(new URL('../../use-word-documents/package.json', import.meta.url))('fflate');
import {ROOT, fail, sameDocument, sleep, MAX_TEXT} from './core.mjs';

const escapeXML = text => text.replace(/[&<>"']/g, c => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&apos;'}[c]));
export function manifest(account) {
  const url = `https://localhost:${account.port}/excel-live/${account.secret}`;
  const icon = size => `${url}/icon-${size}.png`;
  const pane = escapeXML(`${url}/index.html`);
  return `<?xml version="1.0" encoding="UTF-8"?>
<OfficeApp xmlns="http://schemas.microsoft.com/office/appforoffice/1.1" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xmlns:bt="http://schemas.microsoft.com/office/officeappbasictypes/1.0" xsi:type="TaskPaneApp">
  <Id>${account.addinId}</Id><Version>1.0.0.0</Version><ProviderName>Agent Hands</ProviderName><DefaultLocale>en-US</DefaultLocale>
  <DisplayName DefaultValue="Agent Hands Excel"/><Description DefaultValue="Bounded document edits from the private Agent Hands browser."/>
  <IconUrl DefaultValue="${icon(32)}"/><HighResolutionIconUrl DefaultValue="${icon(80)}"/>
  <AppDomains><AppDomain>https://localhost:${account.port}</AppDomain></AppDomains><Hosts><Host Name="Workbook"/></Hosts>
  <Requirements><Sets DefaultMinVersion="1.18"><Set Name="ExcelApi"/></Sets></Requirements>
  <DefaultSettings><SourceLocation DefaultValue="${pane}"/></DefaultSettings><Permissions>ReadWriteDocument</Permissions>
  <VersionOverrides xmlns="http://schemas.microsoft.com/office/taskpaneappversionoverrides" xsi:type="VersionOverridesV1_0">
    <Hosts><Host xsi:type="Workbook"><DesktopFormFactor><FunctionFile resid="Pane.Url"/>
      <ExtensionPoint xsi:type="PrimaryCommandSurface"><OfficeTab id="TabHome"><Group id="AgentHands.Excel.Group"><Label resid="Group.Label"/>
        <Icon><bt:Image size="16" resid="Icon.16"/><bt:Image size="32" resid="Icon.32"/><bt:Image size="80" resid="Icon.80"/></Icon>
        <Control xsi:type="Button" id="AgentHands.Excel.Open"><Label resid="Button.Label"/><Supertip><Title resid="Button.Label"/><Description resid="Button.Description"/></Supertip>
          <Icon><bt:Image size="16" resid="Icon.16"/><bt:Image size="32" resid="Icon.32"/><bt:Image size="80" resid="Icon.80"/></Icon>
          <Action xsi:type="ShowTaskpane"><TaskpaneId>Office.AutoShowTaskpaneWithDocument</TaskpaneId><SourceLocation resid="Pane.Url"/></Action>
        </Control>
      </Group></OfficeTab></ExtensionPoint>
    </DesktopFormFactor></Host></Hosts>
    <Resources><bt:Images>${[16, 32, 80].map(size => `<bt:Image id="Icon.${size}" DefaultValue="${icon(size)}"/>`).join('')}</bt:Images>
      <bt:Urls><bt:Url id="Pane.Url" DefaultValue="${pane}"/></bt:Urls>
      <bt:ShortStrings><bt:String id="Group.Label" DefaultValue="Agent Hands"/><bt:String id="Button.Label" DefaultValue="Open Excel tools"/></bt:ShortStrings>
      <bt:LongStrings><bt:String id="Button.Description" DefaultValue="Connect this document to the private Agent Hands browser."/></bt:LongStrings>
    </Resources>
  </VersionOverrides>
</OfficeApp>\n`;
}
// Small generated PNGs keep the manifest self-contained without additional asset tooling.
function png(size) {
  const crc = bytes => {
    let value = 0xffffffff;
    for (const byte of bytes) { value ^= byte; for (let bit = 0; bit < 8; bit++) value = (value >>> 1) ^ (0xedb88320 & -(value & 1)); }
    return (value ^ 0xffffffff) >>> 0;
  };
  const chunk = (type, bytes) => {
    const body = Buffer.concat([Buffer.from(type), bytes]), result = Buffer.alloc(body.length + 8);
    result.writeUInt32BE(bytes.length); body.copy(result, 4); result.writeUInt32BE(crc(body), result.length - 4); return result;
  };
  const header = Buffer.alloc(13); header.writeUInt32BE(size); header.writeUInt32BE(size, 4); header[8] = 8; header[9] = 2;
  const pixels = Buffer.alloc((size * 3 + 1) * size);
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) pixels.set([35, 75, 145], y * (size * 3 + 1) + 1 + x * 3);
  return Buffer.concat([Buffer.from('89504e470d0a1a0a', 'hex'), chunk('IHDR', header), chunk('IDAT', Buffer.from(zlibSync(pixels))), chunk('IEND', Buffer.alloc(0))]);
}
export async function startBridge(account, target) {
  const origin = `https://localhost:${account.port}`, prefix = `/excel-live/${account.secret}/`, token = randomBytes(32).toString('hex');
  let ready = null, pending = null, closed = false;
  const html = `<!doctype html><meta charset="utf-8"><meta name="referrer" content="no-referrer"><title>Agent Hands Excel</title><h1>Agent Hands Excel</h1><p>Only commands from the private Agent Hands browser can run here.</p><pre id="status">Connecting to Excel…</pre><script src="https://appsforoffice.microsoft.com/lib/1/hosted/office.js"></script><script type="module" src="./addin.js"></script>`;
  const script = fs.readFileSync(path.join(ROOT, 'use-excel-workbooks/officejs/app.js'), 'utf8');
  const icons = new Map([16, 32, 80].map(size => [`icon-${size}.png`, png(size)]));
  const authenticated = request => {
    const supplied = request.headers['x-agent-hands'];
    return typeof supplied === 'string' && supplied.length === token.length && timingSafeEqual(Buffer.from(supplied), Buffer.from(token));
  };
  const server = https.createServer({key: fs.readFileSync(path.join(account.dir, 'key.pem')), cert: fs.readFileSync(path.join(account.dir, 'cert.pem'))}, async (request, response) => {
    const reply = (status, data, type = 'application/json') => {
      response.writeHead(status, {'Content-Type': type, 'Cache-Control': 'no-store', 'X-Content-Type-Options': 'nosniff', 'Referrer-Policy': 'no-referrer'});
      response.end(Buffer.isBuffer(data) || typeof data === 'string' ? data : JSON.stringify(data));
    };
    try {
      const url = new URL(request.url, origin);
      if (request.headers.host !== `localhost:${account.port}` || url.origin !== origin || !url.pathname.startsWith(prefix)) return reply(404, {});
      // Office appends host parameters such as ?et= to the task-pane URL. Routing uses only the path; parameters never authorize bridge commands.
      const route = url.pathname.slice(prefix.length);
      if (request.method === 'GET' && route === 'index.html') return reply(200, html, 'text/html; charset=utf-8');
      if (request.method === 'GET' && icons.has(route)) return reply(200, icons.get(route), 'image/png');
      if (request.method === 'GET' && route === 'links.mjs') return reply(200, fs.readFileSync(path.join(ROOT, 'use-excel-workbooks/officejs/links.mjs')), 'text/javascript; charset=utf-8');
      if (request.method === 'GET' && route === 'layout.mjs') return reply(200, fs.readFileSync(path.join(ROOT, 'use-excel-workbooks/officejs/layout.mjs')), 'text/javascript; charset=utf-8');
      if (request.method === 'GET' && route === 'references.mjs') return reply(200, fs.readFileSync(path.join(ROOT, 'use-excel-workbooks/officejs/references.mjs')), 'text/javascript; charset=utf-8');
      if (request.method === 'GET' && route === 'comments.mjs') return reply(200, fs.readFileSync(path.join(ROOT, 'use-excel-workbooks/officejs/comments.mjs')), 'text/javascript; charset=utf-8');
      if (request.method === 'GET' && route === 'text-runs.mjs') return reply(200, fs.readFileSync(path.join(ROOT, 'use-excel-workbooks/officejs/text-runs.mjs')), 'text/javascript; charset=utf-8');
      if (request.method === 'GET' && route === 'addin.js') return reply(200, script, 'text/javascript; charset=utf-8');
      if (!authenticated(request) || (request.headers.origin && request.headers.origin !== origin)) return reply(403, {});
      if (request.method === 'GET' && route === 'config') return reply(200, {target, maxText: MAX_TEXT});
      if (request.method === 'GET' && route === 'next') {
        if (!ready || !pending || pending.sent) return reply(200, null);
        pending.beforeDispatch?.();
        pending.sent = true;
        return reply(200, pending.job);
      }
      if (request.method !== 'POST' || route !== 'report') return reply(404, {});
      let bytes = 0;
      const chunks = [];
      for await (const data of request) { bytes += data.length; if (bytes > 1_500_000) return reply(413, {}); chunks.push(data); }
      const report = JSON.parse(Buffer.concat(chunks).toString('utf8'));
      if (report.id === 'ready') {
        if (report.host !== 'Excel' || report.platform !== 'OfficeOnline' || !sameDocument(report.url, target)) return reply(409, {});
        ready = report;
      } else if (pending?.sent && report.id === pending.job.id) { pending.result = report; }
      else return reply(409, {});
      reply(200, {ok: true});
    } catch (error) { reply(500, {error: error.code || 'bridge_failed'}); }
  });
  server.requestTimeout = 10_000;
  server.headersTimeout = 10_000;
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(account.port, '127.0.0.1', resolve); });
  return {
    origin, prefix, token,
    async waitReady(timeout = 90_000) {
      const deadline = Date.now() + timeout;
      while (!ready && !closed && Date.now() < deadline) await sleep(200);
      if (!ready) fail('addin_setup_required', 'No verified Excel add-in session started. For an authorized edit, run excel-browser prepare --execute; otherwise report the setup requirement.');
      return ready;
    },
    async command(action, data = {}, beforeDispatch, timeout = 60_000) {
      if (pending) fail('bridge_busy', 'Only one command may be active.');
      pending = {job: {id: randomUUID(), action, ...data}, beforeDispatch, sent: false};
      try {
        const deadline = Date.now() + timeout;
        while (!pending.result && !closed && Date.now() < deadline) await sleep(200);
        if (!pending.result) fail(pending.sent ? 'uncertain_after_dispatch' : 'not_dispatched', 'The bridge did not return a result. Reconcile the saved operation before any new edit.');
        return pending.result;
      } finally { pending = null; }
    },
    async close() { closed = true; server.closeAllConnections(); await new Promise(resolve => server.close(resolve)); }
  };
}
