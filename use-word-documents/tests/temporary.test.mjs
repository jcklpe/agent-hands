import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {ROOT} from '../scripts/core.mjs';
import {spawnSync} from 'node:child_process';
import {privateTempDir, cleanupTempRuns} from '../scripts/temporary.mjs';

test('temporary readbacks are private and cannot enter source or Git checkouts', () => {
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'office-temp-test-'));
  try {
    const run = privateTempDir('readback-', fixture);
    if (process.platform !== 'win32') assert.equal(fs.statSync(run).mode & 0o777, 0o700);
    fs.rmSync(run, {recursive:true});
    for (const candidate of [ROOT, path.join(fixture, 'missing'), 'relative']) assert.throws(() => privateTempDir('readback-', candidate), {code: 'unsafe_temporary_directory'});
    fs.mkdirSync(path.join(fixture, '.git'));
    fs.mkdirSync(path.join(fixture, 'nested'));
    assert.throws(() => privateTempDir('readback-', path.join(fixture, 'nested')), {code: 'unsafe_temporary_directory'});
    fs.symlinkSync(ROOT, path.join(fixture, 'source-link'), 'dir');
    assert.throws(() => privateTempDir('readback-', path.join(fixture, 'source-link')), {code: 'unsafe_temporary_directory'});
    assert.throws(() => cleanupTempRuns(false, path.join(fixture, 'nested')), {code:'unsafe_temporary_directory'});
    assert.deepEqual(fs.readdirSync(fixture).sort(), ['.git', 'nested', 'source-link']);
  } finally { fs.rmSync(fixture, {recursive: true, force: true}); }
});

test('crash-left readbacks require registration, age and a stopped controller before cleanup', () => {
  const fixture = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'office-cleanup-test-')));
  try {
    const run = privateTempDir('agent-hands-word-readback-', fixture);
    const marker = path.join(run,'.agent-hands-run.json'), record = JSON.parse(fs.readFileSync(marker));
    const later = record.created + 25*60*60*1000;
    fs.writeFileSync(path.join(run,'readback.docx'),'synthetic private bytes');
    const dead = () => { throw Object.assign(new Error('missing'),{code:'ESRCH'}); };
    assert.equal(cleanupTempRuns(true,fixture,Date.now(),dead).eligible,0);
    assert.equal(cleanupTempRuns(false,fixture,later,()=>{}).removed,0);
    assert.equal(cleanupTempRuns(false,fixture,later,()=>{throw Object.assign(new Error('denied'),{code:'EPERM'});}).removed,0);
    const unknown = path.join(fixture,'agent-hands-word-readback-unknown');fs.mkdirSync(unknown);
    assert.equal(cleanupTempRuns(true,fixture,later,dead).eligible,1);
    assert.ok(fs.existsSync(run));
    assert.equal(cleanupTempRuns(false,fixture,later,dead).removed,1);
    assert.ok(!fs.existsSync(run));assert.ok(fs.existsSync(unknown));
    const link = path.join(fixture,'agent-hands-powerpoint-readback-link');fs.symlinkSync(unknown,link);
    assert.equal(cleanupTempRuns(false,fixture,later,dead).removed,0);
    assert.ok(fs.existsSync(link));
  } finally {fs.rmSync(fixture,{recursive:true,force:true});}
});

test('a killed writer leaves a registered synthetic readback that can be reconciled and cleaned', () => {
  const fixture = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), 'office-killed-temp-')));
  try {
    const module = new URL('../scripts/temporary.mjs', import.meta.url).href;
    const script = `import fs from 'node:fs'; import path from 'node:path'; import {privateTempDir} from ${JSON.stringify(module)}; const dir=privateTempDir('agent-hands-word-readback-',process.argv[1]);fs.writeFileSync(path.join(dir,'readback.docx'),'synthetic content');process.stdout.write(dir);process.kill(process.pid,'SIGKILL');`;
    const child = spawnSync(process.execPath,['--input-type=module','-e',script,fixture],{encoding:'utf8'});
    assert.equal(child.signal,'SIGKILL');
    const dir = child.stdout;
    assert.ok(fs.existsSync(path.join(dir,'readback.docx')));
    assert.equal(cleanupTempRuns(true,fixture,Date.now()+25*60*60*1000).eligible,1);
    assert.equal(cleanupTempRuns(false,fixture,Date.now()+25*60*60*1000).removed,1);
    assert.ok(!fs.existsSync(dir));
  } finally {fs.rmSync(fixture,{recursive:true,force:true});}
});
