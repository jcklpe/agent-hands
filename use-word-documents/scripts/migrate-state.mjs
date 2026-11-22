import fs from 'node:fs';
import path from 'node:path';
import {STATE, LEGACY_STATE, aliasName, loadAccount, lockAccount, privateDir, writeJSON, fail, noSymlinks} from './core.mjs';
import {validateStateRoot, fingerprintTree} from './storage.mjs';

const syncDirectory = dir => {
  if (process.platform !== 'win32') { const fd = fs.openSync(dir, 'r'); try { fs.fsyncSync(fd); } finally { fs.closeSync(fd); } }
};

export function migrateState(alias, execute = false, sourceRoot = LEGACY_STATE, destinationRoot = STATE) {
  aliasName(alias); validateStateRoot(destinationRoot); noSymlinks(sourceRoot);
  const source = path.join(sourceRoot, alias), destination = path.join(destinationRoot, alias);
  if (path.resolve(source) === path.resolve(destination)) fail('unsafe_state', 'Migration source and destination must differ.');
  const marker = path.join(destinationRoot, `.migration-${alias}.json`);
  if (fs.existsSync(marker)) fail('migration_incomplete', 'A previous migration must be reconciled before another attempt.');
  if (fs.existsSync(destination)) fail('state_collision', 'Destination account already exists. Do not merge or overwrite recovery journals.');
  const account = loadAccount(alias, sourceRoot);
  if (fs.existsSync(path.join(source, 'lock.json'))) fail('profile_busy', 'Stop and inspect the owned controller before migration.');
  for (const name of ['SingletonLock', 'SingletonSocket', 'SingletonCookie']) {
    try { fs.lstatSync(path.join(account.browserDir, name)); fail('profile_busy', 'Stop and inspect the owned browser before migration.'); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  const before = fingerprintTree(source);
  if (!execute) return {status: 'state_migration_preview', alias, source, destination, treeHash: before, includes: ['Word', 'PowerPoint', 'browser sign-in', 'plans', 'dispatch journals'], requires: 'Stop all Office callers, including older versions, until migration finishes.', authenticationChanged: false};
  privateDir(destinationRoot);
  if (fs.statSync(source).dev !== fs.statSync(destinationRoot).dev) fail('cross_device_migration', 'Atomic migration requires the same filesystem. No copy fallback is performed.');
  const release = lockAccount(account);
  let moved = false;
  try {
    if (fingerprintTree(source, true) !== before) fail('state_changed', 'Source changed before migration. Stop all writers before retrying.');
    writeJSON(marker, {kind: 'agent-hands-office-migration-v1', alias, source, destination, treeHash: before, owner: account.owner, stage: 'prepared'}, true);
    // Freeze all callers for migration. The lock protects cooperative clients; old init commands must also stay stopped until tombstones exist.
    if (fs.existsSync(destination)) fail('state_collision', 'Destination appeared during migration; inspect both stores.');
    fs.renameSync(source, destination); moved = true;
    syncDirectory(sourceRoot); syncDirectory(destinationRoot);
    privateDir(source);
    writeJSON(path.join(source, 'account.json'), {kind: 'agent-hands-office-migrated-v1', alias, destination}, true);
    writeJSON(marker, {kind: 'agent-hands-office-migration-v1', alias, source, destination, treeHash: before, owner: account.owner, stage: 'moved'});
    fs.unlinkSync(path.join(destination, 'lock.json'));
    if (fingerprintTree(destination) !== before) fail('migration_verification_failed', 'Moved contents differ. Keep both locations and the migration record for investigation.');
    fs.unlinkSync(marker); syncDirectory(destinationRoot);
    return {status: 'state_migrated', alias, treeHash: before, authenticationChanged: false, legacyTombstone: true};
  } finally {
    if (!moved) release();
    // An unresolved record deliberately blocks the new route. Do not roll back, copy journals or erase uncertain state automatically.
  }
}
