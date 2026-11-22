import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {createHash} from 'node:crypto';

export function defaultStateRoot(env = process.env, platform = process.platform, home = os.homedir()) {
  const base = env.AGENT_HANDS_STATE_DIR || (platform === 'darwin' ? path.join(home, 'Library/Application Support/agent-hands') : platform === 'win32' ? path.join(env.LOCALAPPDATA || path.join(home, 'AppData/Local'), 'agent-hands') : path.join(env.XDG_STATE_HOME || path.join(home, '.local/state'), 'agent-hands'));
  if (!path.isAbsolute(base)) throw Object.assign(new Error('The private state root must be absolute.'), {code: 'unsafe_state'});
  return path.join(base, 'office');
}
export function validateStateRoot(root) {
  if (!path.isAbsolute(root)) throw Object.assign(new Error('The private state root must be absolute.'), {code: 'unsafe_state'});
  let current = path.parse(root).root;
  for (const segment of root.slice(current.length).split(path.sep)) {
    current = path.join(current, segment);
    try {
      const stat = fs.lstatSync(current);
      if (stat.isSymbolicLink() || !stat.isDirectory()) throw Object.assign(new Error('Private state roots must traverse real directories.'), {code: 'unsafe_state'});
    } catch (error) { if (error.code !== 'ENOENT') throw error; }
    if (fs.existsSync(path.join(current, '.git'))) throw Object.assign(new Error('Private state cannot live in a Git checkout.'), {code: 'unsafe_state'});
  }
}
export function fingerprintTree(root, ignoreLock = false) {
  const parent = fs.lstatSync(root);
  if (!parent.isDirectory() || parent.isSymbolicLink() || (process.platform !== 'win32' && (parent.uid !== process.getuid() || (parent.mode & 0o077)))) throw Object.assign(new Error('Account root must be an owner-only directory.'), {code: 'unsafe_state'});
  const entries = [];
  const visit = (dir, relative = '') => {
    for (const name of fs.readdirSync(dir).sort()) {
      if (!relative && ignoreLock && name === 'lock.json') continue;
      const file = path.join(dir, name), key = path.join(relative, name), stat = fs.lstatSync(file);
      if (stat.isSymbolicLink() || (!stat.isDirectory() && !stat.isFile()) || (process.platform !== 'win32' && stat.uid !== process.getuid())) throw Object.assign(new Error('Migration requires owned regular files and directories, without symlinks.'), {code: 'unsafe_state'});
      if (stat.isDirectory()) { entries.push([key, 'directory', stat.mode & 0o777]); visit(file, key); }
      else entries.push([key, 'file', stat.mode & 0o777, createHash('sha256').update(fs.readFileSync(file)).digest('hex')]);
    }
  };
  visit(root);
  return createHash('sha256').update(JSON.stringify(entries)).digest('hex');
}
