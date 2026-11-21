import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {X509Certificate} from 'node:crypto';
import {initialize, renewCertificate, launchOptions} from '../scripts/browser.mjs';
import {lockAccount, writeJSON} from '../scripts/core.mjs';

test('renewal preserves key, identity, browser state and uncertain journals; refuses unsafe state', async t => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'word-renew-')));
  try {
    const account = await initialize('demo', 43189, root);
    const sentinel = path.join(account.browserDir, 'synthetic-session');
    fs.writeFileSync(sentinel, 'synthetic session', {mode: 0o600});
    const journal = path.join(account.dir, 'plans', 'synthetic.journal.json');
    writeJSON(journal, {status: 'uncertain_after_dispatch'});
    const preserved = [path.join(account.dir, 'key.pem'), path.join(account.dir, 'account.json'), sentinel, journal];
    const before = preserved.map(p => fs.readFileSync(p));
    const cert = path.join(account.dir, 'cert.pem'), original = fs.readFileSync(cert);
    assert.equal((await renewCertificate(account)).status, 'certificate_renewal_preview');
    assert.deepEqual(fs.readFileSync(cert), original);
    const release = lockAccount(account);
    await assert.rejects(renewCertificate(account, true), {code: 'profile_busy'});
    release();
    const singleton = path.join(account.browserDir, 'SingletonLock');
    fs.symlinkSync('synthetic-host-123', singleton);
    await assert.rejects(renewCertificate(account, true), {code: 'profile_busy'});
    fs.unlinkSync(singleton);
    const rename = t.mock.method(fs, 'renameSync', () => { throw new Error('synthetic rename failure'); });
    try { await assert.rejects(renewCertificate(account, true), /synthetic rename failure/); } finally { rename.mock.restore(); }
    assert.deepEqual(fs.readFileSync(cert), original);
    assert.ok(!fs.existsSync(path.join(account.dir, 'lock.json')));
    assert.ok(!fs.readdirSync(account.dir).some(n => n.endsWith('.tmp')));
    const clock = t.mock.method(Date, 'now', () => Date.parse(new X509Certificate(original).validTo) + 86400_000);
    try { assert.equal((await renewCertificate(account)).expired, true); assert.throws(() => launchOptions(account), {code: 'certificate_expired'}); assert.equal((await renewCertificate(account, true)).status, 'certificate_renewed'); assert.equal(launchOptions(account).headless, true); }
    finally { clock.mock.restore(); }
    assert.notDeepEqual(fs.readFileSync(cert), original);
    assert.equal(new X509Certificate(fs.readFileSync(cert)).publicKey.export({type:'spki',format:'pem'}), new X509Certificate(original).publicKey.export({type:'spki',format:'pem'}));
    preserved.forEach((p,i) => assert.deepEqual(fs.readFileSync(p), before[i]));
    assert.equal(fs.statSync(cert).mode & 0o777, 0o600);
    assert.equal(launchOptions(account).chromiumSandbox, true);
    assert.ok(!fs.existsSync(path.join(account.dir, 'lock.json')));
    assert.ok(!fs.readdirSync(account.dir).some(n => n.endsWith('.tmp')));
    const second = await initialize('other', 43190, root);
    fs.copyFileSync(path.join(second.dir, 'key.pem'), path.join(account.dir, 'key.pem'));
    const good = fs.readFileSync(cert);
    await assert.rejects(renewCertificate(account, true), {code: 'certificate_key_mismatch'});
    assert.deepEqual(fs.readFileSync(cert), good);
    fs.unlinkSync(cert); fs.symlinkSync(path.join(second.dir, 'cert.pem'), cert);
    await assert.rejects(renewCertificate(account, true), {code: 'unsafe_state'});
  } finally { fs.rmSync(root, {recursive: true, force: true}); }
});
