import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {initialize} from '../scripts/browser.mjs';
import {writeJSON, loadAccount, lockAccount} from '../scripts/core.mjs';
import {defaultStateRoot, platformStateRoot, validateStateRoot, fingerprintTree} from '../scripts/storage.mjs';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {migrateState} from '../scripts/migrate-state.mjs';

test('state locations are explicit, outside checkouts and do not traverse symlinks', () => {
  assert.equal(defaultStateRoot({}, 'darwin', '/demo'), '/demo/.agent-hands/office');
  assert.equal(defaultStateRoot({}, 'linux', '/demo'), '/demo/.agent-hands/office');
  assert.equal(defaultStateRoot({}, 'win32', '/demo'), '/demo/.agent-hands/office');
  assert.equal(platformStateRoot({}, 'darwin', '/demo'), '/demo/Library/Application Support/agent-hands/office');
  assert.equal(platformStateRoot({XDG_STATE_HOME:'/state'}, 'linux', '/demo'), '/state/agent-hands/office');
  assert.equal(platformStateRoot({LOCALAPPDATA:'/local'}, 'win32', '/demo'), '/local/agent-hands/office');
  assert.equal(defaultStateRoot({AGENT_HANDS_STATE_DIR:'/chosen'}, 'darwin', '/demo'), '/chosen/office');
  assert.throws(() => defaultStateRoot({AGENT_HANDS_STATE_DIR:'relative'}), {code:'unsafe_state'});
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'word-storage-')));
  try {
    fs.mkdirSync(path.join(root,'repo')); fs.writeFileSync(path.join(root,'repo','.git'),'gitdir: demo');
    assert.throws(() => validateStateRoot(path.join(root,'repo','state')), {code:'unsafe_state'});
    fs.symlinkSync(root, path.join(root,'link'));
    assert.throws(() => validateStateRoot(path.join(root,'link','state')), {code:'unsafe_state'});
  } finally { fs.rmSync(root,{recursive:true,force:true}); }
});

test('whole-account migration preserves browser bytes, both journals and identity; old location refuses reuse', async () => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'word-migrate-')));
  try {
    const source = path.join(root,'legacy'), dest = path.join(root,'private','office');
    const account = await initialize('demo',43189,source);
    fs.mkdirSync(path.join(account.dir,'powerpoint'),{mode:0o700});
    writeJSON(path.join(account.dir,'powerpoint','receipt.json'),{status:'uncertain_after_dispatch'});
    writeJSON(path.join(account.dir,'plans','receipt.json'),{status:'uncertain_after_dispatch'});
    fs.writeFileSync(path.join(account.browserDir,'synthetic-cookie'),'synthetic browser state');
    const before = fingerprintTree(account.dir);
    assert.equal(migrateState('demo',false,source,dest).treeHash,before);
    assert.equal(fs.existsSync(dest),false);
    const release = lockAccount(account);
    assert.throws(() => migrateState('demo',true,source,dest),{code:'profile_busy'}); release();
    const marker = path.join(account.browserDir,'SingletonLock'); fs.symlinkSync('demo-123',marker);
    assert.throws(() => migrateState('demo',true,source,dest),{code:'profile_busy'}); fs.unlinkSync(marker);
    assert.equal(migrateState('demo',true,source,dest).treeHash,before);
    assert.equal(fingerprintTree(path.join(dest,'demo')),before);
    assert.equal(loadAccount('demo',dest).owner,account.owner);
    assert.throws(() => loadAccount('demo',source),{code:'unsafe_state'});
    await assert.rejects(initialize('demo',43189,source),{code:'already_initialized'});
    assert.deepEqual(fs.readdirSync(path.join(source,'demo')),['account.json']);
    assert.throws(() => migrateState('demo',true,source,dest),{code:'state_collision'});
  } finally { fs.rmSync(root,{recursive:true,force:true}); }
});

test('interrupted rename leaves a blocking migration record and no silent copy fallback', async t => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'word-migrate-fail-')));
  try {
    const source = path.join(root,'legacy'), dest = path.join(root,'private');
    const account = await initialize('demo',43189,source);
    const before = fingerprintTree(account.dir);
    const rename = t.mock.method(fs,'renameSync',() => { throw new Error('synthetic rename failure'); });
    try { assert.throws(() => migrateState('demo',true,source,dest),/synthetic rename failure/); } finally { rename.mock.restore(); }
    assert.equal(fingerprintTree(account.dir),before);
    assert.ok(fs.existsSync(path.join(dest,'.migration-demo.json')));
    assert.throws(() => migrateState('demo',true,source,dest),{code:'migration_incomplete'});
    assert.ok(!fs.existsSync(path.join(dest,'demo')));
  } finally { fs.rmSync(root,{recursive:true,force:true}); }
});

test('interruption after moving retains private recovery record and complete destination', async t => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'word-migrate-post-')));
  try {
    const source = path.join(root,'legacy'), dest = path.join(root,'private');
    const account = await initialize('demo',43189,source);
    const mkdir = fs.mkdirSync;
    const inject = t.mock.method(fs,'mkdirSync',function(file, ...args) {
      if (String(file) === account.dir && fs.existsSync(path.join(dest,'demo'))) throw new Error('synthetic tombstone failure');
      return mkdir.call(fs,file,...args);
    });
    try { assert.throws(() => migrateState('demo',true,source,dest),/synthetic tombstone failure/); } finally { inject.mock.restore(); }
    assert.ok(fs.existsSync(path.join(dest,'demo','account.json')));
    assert.ok(fs.existsSync(path.join(dest,'demo','lock.json')));
    assert.ok(fs.existsSync(path.join(dest,'.migration-demo.json')));
    assert.throws(() => migrateState('demo',true,source,dest),{code:'migration_incomplete'});
  } finally { fs.rmSync(root,{recursive:true,force:true}); }
});

test('CLI refuses a checkout state root before creating private files', () => {
  const root = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'word-state-cli-')));
  try {
    const repo = path.join(root, 'repo'); fs.mkdirSync(repo); fs.writeFileSync(path.join(repo, '.git'), 'gitdir: demo');
    const chosen = path.join(repo, 'state');
    const cli = fileURLToPath(new URL('../../setup-microsoft-services/scripts/word-browser.mjs', import.meta.url));
    const result = spawnSync(process.execPath, [cli, 'init', 'demo', '--port', '43189'], {encoding:'utf8', env:{...process.env, AGENT_HANDS_STATE_DIR:chosen}});
    assert.equal(result.status, 1);
    assert.equal(JSON.parse(result.stdout).status, 'unsafe_state');
    assert.equal(fs.existsSync(chosen), false);
  } finally { fs.rmSync(root, {recursive:true, force:true}); }
});
