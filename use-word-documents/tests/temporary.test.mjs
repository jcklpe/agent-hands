import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {ROOT} from '../scripts/core.mjs';
import {privateTempDir} from '../scripts/temporary.mjs';

test('temporary readbacks are private and cannot enter source or Git checkouts', () => {
  const fixture = fs.mkdtempSync(path.join(os.tmpdir(), 'office-temp-test-'));
  try {
    const run = privateTempDir('readback-', fixture);
    if (process.platform !== 'win32') assert.equal(fs.statSync(run).mode & 0o777, 0o700);
    fs.rmdirSync(run);
    for (const candidate of [ROOT, path.join(fixture, 'missing'), 'relative']) assert.throws(() => privateTempDir('readback-', candidate), {code: 'unsafe_temporary_directory'});
    fs.mkdirSync(path.join(fixture, '.git'));
    fs.mkdirSync(path.join(fixture, 'nested'));
    assert.throws(() => privateTempDir('readback-', path.join(fixture, 'nested')), {code: 'unsafe_temporary_directory'});
    fs.symlinkSync(ROOT, path.join(fixture, 'source-link'), 'dir');
    assert.throws(() => privateTempDir('readback-', path.join(fixture, 'source-link')), {code: 'unsafe_temporary_directory'});
    assert.deepEqual(fs.readdirSync(fixture).sort(), ['.git', 'nested', 'source-link']);
  } finally { fs.rmSync(fixture, {recursive: true, force: true}); }
});
