import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {initialize, launchOwnedBrowser} from '../../use-word-documents/scripts/browser.mjs';
import {openAddinAutomatically} from '../scripts/bootstrap.mjs';
import {manifest} from '../scripts/bridge.mjs';

test('headless preparation installs only the generated add-in, handles overflow and refuses a different document', async () => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'powerpoint-setup-')));
  const account = await initialize('demo', 43439, root);
  const target = {origin: 'https://example.sharepoint.com', pathname: '/sites/demo/Test.pptx', guid: ''};
  let context;
  try {
    context = await launchOwnedBrowser(account);
    await context.route('https://example.sharepoint.com/**', route => route.fulfill({contentType: 'text/html', body: '<iframe name="WacFrame_PowerPoint_1" src="https://powerpoint.officeapps.live.com/editor"></iframe>'}));
    await context.route('https://powerpoint.officeapps.live.com/editor', route => route.fulfill({contentType: 'text/html', body: `
      <button role="tab">Home</button><button role="tab">Insert</button>
      <button aria-label="Add-ins" onclick="document.querySelector('#advanced').hidden=false"></button>
      <button id="advanced" hidden onclick="document.querySelector('#catalog').hidden=false">Advanced...</button>
      <iframe name="_xdm_catalog" id="catalog" hidden src="https://powerpoint.officeapps.live.com/catalog"></iframe>
      <button aria-label="More Options" onclick="document.querySelector('#overflow').hidden=false"></button>
      <div role="menu" id="overflow" hidden></div>
      <script>
      window.opens=0;window.uploads=0;
      addEventListener('message',e=>{if(e.origin==='https://powerpoint.officeapps.live.com'&&e.data.xml){window.uploadedXML=e.data.xml;window.uploads++;document.querySelector('#catalog').hidden=true;document.querySelector('#overflow').innerHTML='<button role="menuitem" aria-label="Open PowerPoint tools" onclick="window.opens++">Open PowerPoint tools</button>';}});
      </script>`}));
    await context.route('https://powerpoint.officeapps.live.com/catalog', route => route.fulfill({contentType: 'text/html', body: `<button onclick="document.querySelector('#form').hidden=false">Upload My Add-in</button><div id="form" hidden><input type="file"><input type="button" value="Upload" onclick="document.querySelector('input[type=file]').files[0].text().then(xml=>parent.postMessage({xml},'https://powerpoint.officeapps.live.com'))"></div>`}));
    const page = await context.newPage();
    await page.goto(target.origin + target.pathname);
    const frame = page.frame({name: 'WacFrame_PowerPoint_1'});
    await frame.getByRole('tab', {name: 'Home', exact: true}).waitFor();
    const bridge = {waitReady: async () => { if (!await frame.evaluate(() => window.opens)) throw Object.assign(new Error('not ready'), {code: 'addin_setup_required'}); }};
    assert.equal(await openAddinAutomatically({page}, bridge, account, target), 'installed');
    assert.equal(await frame.evaluate(() => window.uploadedXML), manifest(account));
    assert.equal(await frame.evaluate(() => window.uploads), 1);
    assert.equal(await openAddinAutomatically({page}, bridge, account, target), 'already_running');
    assert.equal(await frame.evaluate(() => window.uploads), 1);
    await frame.evaluate(() => { window.opens = 0; });
    assert.equal(await openAddinAutomatically({page}, bridge, account, target), 'opened');
    assert.equal(await frame.evaluate(() => window.uploads), 1);
    await page.goto(target.origin + '/sites/demo/Other.pptx');
    await assert.rejects(openAddinAutomatically({page}, bridge, account, target), {code: 'target_mismatch'});
  } finally { if (context) await context.close(); fs.rmSync(root, {recursive: true, force: true}); }
});

test('prepare without execution authorization stops before account or network access', () => {
  try {
    execFileSync(process.execPath, [fileURLToPath(new URL('../../setup-microsoft-services/scripts/powerpoint-browser.mjs', import.meta.url)), 'prepare', 'demo', '--drive', 'drive1', '--item', 'item1'], {encoding: 'utf8'});
    assert.fail('prepare unexpectedly succeeded');
  } catch (error) {
    assert.equal(JSON.parse(error.stdout).status, 'execute_required');
  }
});
