import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
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
  const dir = fs.mkdtempSync(path.join(root, prefix));
  try { fs.chmodSync(dir, 0o700); } catch (error) { fs.rmdirSync(dir); throw error; }
  return dir;
}
