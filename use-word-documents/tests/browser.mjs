import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import net from 'node:net';
import {initialize, launchOwnedBrowser, renewCertificate} from '../scripts/browser.mjs';
import {startBridge} from '../scripts/bridge.mjs';
import {previewParagraphs, makePlan, markDispatch} from '../scripts/core.mjs';

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
      window.fixture = {paragraphs: ['ALPHA: old', 'BETA: original'], mutations: 0, failSave: false, table: false, syncs: 0, failSync: 0, readOnly: false, wrongTarget: false};
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
            get mode() { return fixture.readOnly ? 'readOnly' : 'readWrite'; }, getFilePropertiesAsync: callback => callback({status: 'ok', value: {url: target.origin + (fixture.wrongTarget ? '/Other.docx' : target.pathname)}}),
            settings: {get: key => settings[key], set: (key, value) => settings[key] = value, saveAsync: callback => callback({status: 'ok'}), refreshAsync: callback => callback({status: 'ok'})}
          }
        }
      };
      window.Word = {InsertLocation: {replace: 'replace'}, run: async callback => callback({document: {body, save() { if (fixture.failSave) throw new Error('Interrupted save'); }}, sync: async () => { fixture.syncs++; if (fixture.failSync === fixture.syncs) throw new Error('Synthetic transport interruption'); }})};
    }, target);
    const page = await context.newPage();
    await page.goto(bridge.origin + bridge.prefix + 'index.html?et=');
    await bridge.waitReady(5000);
    assert.equal((await bridge.command('enable-startup')).status, 'startup_saved');
    assert.deepEqual(await page.evaluate(() => fixture.settings), {'Office.AutoShowTaskpaneWithDocument': true});
    const read = await bridge.command('read');
    assert.deepEqual(read.paragraphs, ['ALPHA: old', 'BETA: original']);
    const edit = previewParagraphs(read.paragraphs, 'old', 'new');
    for (const [flag, code] of [['readOnly', 'read_only'], ['wrongTarget', 'target_mismatch'], ['table', 'stale_or_unsupported_paragraph']]) {
      await page.evaluate(flag => { fixture[flag] = true; }, flag);
      const refused = await bridge.command('replace', {edit});
      assert.equal(refused.status, 'refused_before_mutation');
      assert.equal(refused.code, code);
      assert.equal(await page.evaluate(() => fixture.mutations), 0);
      await page.evaluate(flag => { fixture[flag] = false; }, flag);
    }
    await page.evaluate(() => { fixture.syncs = 0; fixture.failSync = 1; });
    assert.equal((await bridge.command('replace', {edit})).status, 'refused_before_mutation');
    assert.equal(await page.evaluate(() => fixture.mutations), 0);
    await page.evaluate(() => { fixture.failSync = 0; fixture.paragraphs[1] = 'BETA: concurrent edit'; });
    assert.equal((await bridge.command('replace', {edit})).status, 'save_returned');
    assert.deepEqual(await page.evaluate(() => fixture.paragraphs), ['ALPHA: new', 'BETA: concurrent edit']);
    assert.equal((await bridge.command('replace', {edit})).code, 'stale_preview');
    assert.equal(await page.evaluate(() => fixture.mutations), 1);
    const next = previewParagraphs(['ALPHA: new'], 'new', 'later');
    await page.evaluate(() => { fixture.failSave = true; });
    assert.equal((await bridge.command('replace', {edit: next})).status, 'uncertain_after_dispatch');
    assert.equal(await page.evaluate(() => fixture.mutations), 2);
    // Interrupt synchronization after insertion, before save, and after save before readback.
    for (const failSync of [5, 6, 7]) {
      await page.evaluate(failSync => { fixture.paragraphs[0] = 'ALPHA: new'; fixture.failSave = false; fixture.syncs = 0; fixture.failSync = failSync; }, failSync);
      const before = await page.evaluate(() => fixture.mutations);
      const result = await bridge.command('replace', {edit: next});
      assert.equal(result.status, 'uncertain_after_dispatch');
      assert.equal(await page.evaluate(() => fixture.mutations), before + 1);
      assert.equal(await page.evaluate(() => fixture.paragraphs[1]), 'BETA: concurrent edit');
    }
    // Drop the result report after the actual add-in executes; retain durable dispatch and prohibit replay.
    await page.evaluate(() => { fixture.paragraphs[0] = 'ALPHA: new'; fixture.failSync = 0; fixture.syncs = 0; });
    let dropped = false;
    await context.route(bridge.origin + bridge.prefix + 'report', async route => {
      const report = route.request().postDataJSON();
      if (report.status === 'save_returned') { dropped = true; await route.abort(); } else await route.continue();
    });
    const plan = makePlan(target, next), journal = path.join(account.dir, 'plans', plan.id + '.journal.json');
    const before = await page.evaluate(() => fixture.mutations);
    await assert.rejects(bridge.command('replace', {edit: next}, () => markDispatch(journal, plan), 2000), {code: 'uncertain_after_dispatch'});
    assert.equal(dropped, true);
    assert.equal(await page.evaluate(() => fixture.mutations), before + 1);
    assert.deepEqual(await page.evaluate(() => fixture.paragraphs), ['ALPHA: later', 'BETA: concurrent edit']);
    assert.equal(JSON.parse(fs.readFileSync(journal)).status, 'uncertain_after_dispatch');
    assert.throws(() => markDispatch(journal, plan), {code: 'already_dispatched'});
    await context.close(); context = null;
    assert.equal(await untouched.title(), 'Unrelated tabs stay open');
    assert.equal(sentinel.pages().length, 2);
  } finally { if (context) await context.close(); if (sentinel) await sentinel.close(); await bridge.close(); fs.rmSync(root, {recursive: true, force: true}); }
});
