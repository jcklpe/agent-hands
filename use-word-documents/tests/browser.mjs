import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import {initialize, launchOwnedBrowser, renewCertificate} from '../scripts/browser.mjs';
import {startBridge} from '../scripts/bridge.mjs';
import {previewParagraphs} from '../scripts/core.mjs';

test('real headless owned browser runs the add-in bridge with an offline Office fixture', async () => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'word-browser-')));
  const listener = net.createServer();
  await new Promise(resolve => listener.listen(0, '127.0.0.1', resolve));
  const port = listener.address().port;
  await new Promise(resolve => listener.close(resolve));
  const account = await initialize('demo', port, root);
  const sentinelAccount = await initialize('sentinel', port, root);
  const target = {origin: 'https://example.sharepoint.com', pathname: '/sites/demo/Test.docx', guid: ''};
  assert.equal((await renewCertificate(account, true)).status, 'certificate_renewed');
  const bridge = await startBridge(account, target);
  let context, sentinel;
  try {
    sentinel = await launchOwnedBrowser(sentinelAccount);
    const untouched = await sentinel.newPage();
    await untouched.goto('data:text/html,<title>Unrelated tabs stay open</title>');
    context = await launchOwnedBrowser(account, true, bridge);
    await context.route('https://appsforoffice.microsoft.com/**', route => route.fulfill({contentType: 'text/javascript', body: ''}));
    await context.addInitScript(target => {
      window.fixture = {paragraphs: ['ALPHA: old', 'BETA: original'], mutations: 0, failSave: false, table: false};
      const fixture = window.fixture;
      const proxy = index => ({get text() { return fixture.paragraphs[index]; }});
      const paragraphs = {load() {}, get items() { return fixture.paragraphs.map((_, index) => proxy(index)); }};
      const body = {paragraphs, search(find) {
        const items = fixture.paragraphs.flatMap((p, index) => p.includes(find) ? [{text: find, paragraphs: {load() {}, get items() { return [proxy(index)]; }}, parentTableOrNullObject: {load() {}, get isNullObject() { return !fixture.table; }}, insertText(replacement) { fixture.paragraphs[index] = fixture.paragraphs[index].replace(find, () => replacement); fixture.mutations++; }}] : []);
        return {items, load() {}};
      }};
      const settings = {};
      fixture.settings = settings;
      window.Office = {
        onReady: async () => {}, AsyncResultStatus: {Succeeded: 'ok'}, DocumentMode: {ReadWrite: 'readWrite'},
        context: {
          host: 'Word', platform: 'OfficeOnline', requirements: {isSetSupported: () => true},
          document: {
            mode: 'readWrite', getFilePropertiesAsync: callback => callback({status: 'ok', value: {url: target.origin + target.pathname}}),
            settings: {get: key => settings[key], set: (key, value) => settings[key] = value, saveAsync: callback => callback({status: 'ok'}), refreshAsync: callback => callback({status: 'ok'})}
          }
        }
      };
      window.Word = {InsertLocation: {replace: 'replace'}, run: async callback => callback({document: {body, save() { if (fixture.failSave) throw new Error('Interrupted save'); }}, sync: async () => {}})};
    }, target);
    const page = await context.newPage();
    await page.goto(bridge.origin + bridge.prefix + 'index.html?et=');
    await bridge.waitReady(5000);
    assert.equal((await bridge.command('enable-startup')).status, 'startup_saved');
    assert.deepEqual(await page.evaluate(() => fixture.settings), {'Office.AutoShowTaskpaneWithDocument': true});
    const read = await bridge.command('read');
    assert.deepEqual(read.paragraphs, ['ALPHA: old', 'BETA: original']);
    const edit = previewParagraphs(read.paragraphs, 'old', 'new');
    await page.evaluate(() => { fixture.paragraphs[1] = 'BETA: concurrent edit'; });
    assert.equal((await bridge.command('replace', {edit})).status, 'save_returned');
    assert.deepEqual(await page.evaluate(() => fixture.paragraphs), ['ALPHA: new', 'BETA: concurrent edit']);
    assert.equal((await bridge.command('replace', {edit})).code, 'stale_preview');
    assert.equal(await page.evaluate(() => fixture.mutations), 1);
    const next = previewParagraphs(['ALPHA: new'], 'new', 'later');
    await page.evaluate(() => { fixture.failSave = true; });
    assert.equal((await bridge.command('replace', {edit: next})).status, 'uncertain_after_dispatch');
    assert.equal(await page.evaluate(() => fixture.mutations), 2);
    await context.close(); context = null;
    assert.equal(await untouched.title(), 'Unrelated tabs stay open');
    assert.equal(sentinel.pages().length, 2);
  } finally { if (context) await context.close(); if (sentinel) await sentinel.close(); await bridge.close(); fs.rmSync(root, {recursive: true, force: true}); }
});
