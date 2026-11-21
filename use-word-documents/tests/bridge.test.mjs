import test from 'node:test';
import assert from 'node:assert/strict';
import https from 'node:https';
import net from 'node:net';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {initialize} from '../scripts/browser.mjs';
import {startBridge} from '../scripts/bridge.mjs';
import {markDispatch, makePlan} from '../scripts/core.mjs';

async function port() {
  const server = net.createServer();
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const value = server.address().port;
  await new Promise(resolve => server.close(resolve));
  return value;
}
test('bridge enforces local host, origin, run token, target and single delivery', async () => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'word-bridge-')));
  const account = await initialize('demo', await port(), root);
  const target = {origin: 'https://example.sharepoint.com', pathname: '/sites/demo/Test.docx', guid: ''};
  const bridge = await startBridge(account, target);
  const call = (route, body, overrides = {}) => new Promise((resolve, reject) => {
    const request = https.request({hostname: '127.0.0.1', port: account.port, servername: 'localhost', ca: fs.readFileSync(path.join(account.dir, 'cert.pem')), path: bridge.prefix + route, method: body ? 'POST' : 'GET', headers: {Host: `localhost:${account.port}`, Origin: bridge.origin, 'X-Agent-Hands': bridge.token, ...overrides}}, response => {
      let text = ''; response.on('data', chunk => text += chunk); response.on('end', () => resolve({status: response.statusCode, body: response.headers['content-type']?.startsWith('application/json') ? JSON.parse(text) : text}));
    });
    request.on('error', reject); request.end(body ? JSON.stringify(body) : undefined);
  });
  try {
    const pane = await call('index.html?et=', null, {'X-Agent-Hands': ''});
    assert.equal(pane.status, 200);
    assert.match(pane.body, /<title>Agent Hands Word<\/title>/);
    assert.ok(!pane.body.includes(bridge.token));
    const script = await call('addin.js', null, {'X-Agent-Hands': ''});
    assert.equal(script.status, 200);
    assert.ok(!script.body.includes(bridge.token));
    assert.equal((await call('config?et=', null, {'X-Agent-Hands': ''})).status, 403);
    assert.equal((await call('config', null, {'X-Agent-Hands': 'wrong'})).status, 403);
    assert.equal((await call('config', null, {Origin: 'https://evil.test'})).status, 403);
    assert.equal((await call('config', null, {Host: `evil.test:${account.port}`})).status, 404);
    assert.equal((await call('report', {id: 'ready', host: 'Word', platform: 'OfficeOnline', url: 'https://example.sharepoint.com/sites/demo/Other.docx'})).status, 409);
    await assert.rejects(bridge.waitReady(20), {code: 'addin_setup_required'});
    assert.equal((await call('report', {id: 'ready', host: 'Word', platform: 'OfficeOnline', url: target.origin + target.pathname})).status, 200);
    await bridge.waitReady(20);
    const plan = makePlan(target, {find: 'old', replacement: 'new', before: 'old', after: 'new'});
    const journal = path.join(account.dir, 'plans', plan.id + '.journal.json');
    await assert.rejects(bridge.command('replace', {}, () => markDispatch(journal, plan), 50), {code: 'not_dispatched'});
    assert.ok(!fs.existsSync(journal));
    let dispatches = 0;
    const result = bridge.command('replace', {edit: {}}, () => dispatches++, 2000);
    const first = await call('next');
    assert.equal(first.body.action, 'replace');
    assert.equal((await call('next')).body, null);
    assert.equal(dispatches, 1);
    assert.equal((await call('report', {id: 'wrong', status: 'save_returned'})).status, 409);
    await call('report', {id: first.body.id, status: 'save_returned'});
    assert.equal((await result).status, 'save_returned');
    const timeout = bridge.command('replace', {}, () => markDispatch(journal, plan), 100);
    await call('next');
    await assert.rejects(timeout, {code: 'uncertain_after_dispatch'});
    assert.equal((await call('next')).body, null);
    assert.equal(JSON.parse(fs.readFileSync(journal)).status, 'uncertain_after_dispatch');
    assert.throws(() => markDispatch(journal, plan), {code: 'already_dispatched'});
    assert.equal((await call('report', {id: first.body.id, status: 'save_returned'})).status, 409);
  } finally { await bridge.close(); fs.rmSync(root, {recursive: true, force: true}); }
});
