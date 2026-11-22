import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {randomUUID} from 'node:crypto';
import {ROOT, fail} from './core.mjs';

export function privateTempDir(prefix, selected = os.tmpdir()) {
  if (!path.isAbsolute(selected) || !/^[a-z-]+-$/.test(prefix)) fail('unsafe_temporary_directory', 'Use an existing absolute system temporary directory outside source checkouts.');
  let root;
  try { root = fs.realpathSync(selected); } catch { fail('unsafe_temporary_directory', 'The selected temporary directory is unavailable.'); }
  const source = fs.realpathSync(ROOT);
  if (!fs.statSync(root).isDirectory() || root === source || root.startsWith(source + path.sep)) fail('unsafe_temporary_directory', 'Temporary downloads must stay outside source checkouts.');
  for (let current = root; ; current = path.dirname(current)) {
    if (fs.existsSync(path.join(current, '.git'))) fail('unsafe_temporary_directory', 'Temporary downloads must stay outside Git checkouts.');
    if (path.dirname(current) === current) break;
  }
  cleanupTempRuns(false, root);
  const dir = fs.mkdtempSync(path.join(root, prefix));
  try { fs.chmodSync(dir, 0o700); } catch (error) { fs.rmdirSync(dir); throw error; }
  try { fs.writeFileSync(path.join(dir, '.agent-hands-run.json'), JSON.stringify({kind:'office-readback-temp-v1', pid:process.pid, created:Date.now(), nonce:randomUUID()}), {flag:'wx', mode:0o600}); }
  catch (error) { fs.rmSync(dir, {recursive:true, force:true}); throw error; }
  return dir;
}

export function cleanupTempRuns(preview = true, selected = os.tmpdir(), now = Date.now(), probe = pid => process.kill(pid, 0)) {
  if (!path.isAbsolute(selected)) fail('unsafe_temporary_directory', 'Temporary cleanup requires an absolute system temporary directory outside checkouts.');
  const root = fs.realpathSync(selected);
  const source = fs.realpathSync(ROOT);
  if (root === source || root.startsWith(source + path.sep)) fail('unsafe_temporary_directory', 'Temporary cleanup must stay outside source checkouts.');
  for (let current = root; ; current = path.dirname(current)) {
    if (fs.existsSync(path.join(current, '.git'))) fail('unsafe_temporary_directory', 'Temporary cleanup must stay outside Git checkouts.');
    if (path.dirname(current) === current) break;
  }
  // Only registered Office readback folders are eligible. Do not sweep other tool output or unregistered historical experiments.
  const result = {status:'temporary_cleanup', eligible:0, removed:0, skipped:0};
  for (const name of fs.readdirSync(root)) {
    if (!/^agent-hands-(word|powerpoint)-readback-[A-Za-z0-9]+$/.test(name)) continue;
    const dir = path.join(root, name), marker = path.join(dir, '.agent-hands-run.json');
    try {
      const folder = fs.lstatSync(dir), file = fs.lstatSync(marker);
      if (!folder.isDirectory() || folder.isSymbolicLink() || !file.isFile() || file.isSymbolicLink() || (process.platform !== 'win32' && (folder.uid !== process.getuid() || file.uid !== process.getuid() || (folder.mode & 0o077) || (file.mode & 0o077)))) { result.skipped++; continue; }
      if (file.size > 4096 || fs.existsSync(path.join(dir, '.git'))) { result.skipped++; continue; }
      const data = JSON.parse(fs.readFileSync(marker, 'utf8'));
      if (data.kind !== 'office-readback-temp-v1' || !Number.isSafeInteger(data.pid) || data.pid < 1 || !Number.isFinite(data.created) || now - data.created < 24*60*60*1000 || !/^[a-f0-9-]{36}$/.test(data.nonce || '')) { result.skipped++; continue; }
      try { probe(data.pid); result.skipped++; continue; } catch (error) { if (error.code !== 'ESRCH') { result.skipped++; continue; } }
      result.eligible++;
      if (!preview) { fs.rmSync(dir, {recursive:true}); result.removed++; }
    } catch (error) {
      if (error.code === 'ENOENT' || error instanceof SyntaxError) { result.skipped++; continue; }
      fail('temporary_cleanup_failed', 'A registered Office temporary directory could not be inspected or cleaned. Inspect private temporary storage; no broader sweep was attempted.');
    }
  }
  return result;
}
