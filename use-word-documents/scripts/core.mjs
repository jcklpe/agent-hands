import fs from 'node:fs';
import path from 'node:path';
import {createHash, randomUUID} from 'node:crypto';
import {fileURLToPath} from 'node:url';

export const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
export const STATE = path.join(ROOT, 'setup-microsoft-services/.word-state');
export const MAX_TEXT = 200_000;
export function fail(code, message) { throw Object.assign(new Error(message), {code}); }
export const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');
export const readJSON = file => { noSymlinks(file); return JSON.parse(fs.readFileSync(file, 'utf8')); };
export const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
export function aliasName(alias) {
  if (!/^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$/.test(alias || '')) fail('invalid_alias', 'Use a configured account alias with letters, digits, underscores or hyphens.');
  return alias;
}
export function identifier(id) {
  if (typeof id !== 'string' || !id || id.length > 512 || /[\s\x00-\x1f]/.test(id) || id.startsWith('-')) fail('invalid_target', 'An explicit drive and item ID are required.');
  return id;
}
export function noSymlinks(file) {
  const absolute = path.resolve(file);
  let part = path.parse(absolute).root;
  for (const name of absolute.slice(part.length).split(path.sep)) {
    part = path.join(part, name);
    try { if (fs.lstatSync(part).isSymbolicLink()) fail('unsafe_state', 'State paths must not contain symlinks.'); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
}
export function privateDir(dir) {
  noSymlinks(dir);
  fs.mkdirSync(dir, {recursive: true, mode: 0o700});
  if (process.platform !== 'win32') {
    const stat = fs.statSync(dir);
    if (stat.uid !== process.getuid()) fail('unsafe_state', 'State directory has a different owner.');
    fs.chmodSync(dir, 0o700);
  }
}
export function writeJSON(file, value, exclusive = false) {
  noSymlinks(file);
  const temp = exclusive ? file : `${file}.${randomUUID()}.tmp`;
  const fd = fs.openSync(temp, 'wx', 0o600);
  try { fs.writeFileSync(fd, JSON.stringify(value, null, 2) + '\n'); fs.fsyncSync(fd); } finally { fs.closeSync(fd); }
  if (!exclusive) fs.renameSync(temp, file);
  if (process.platform !== 'win32') { const directory = fs.openSync(path.dirname(file), 'r'); try { fs.fsyncSync(directory); } finally { fs.closeSync(directory); } }
}
export function accountDir(alias, root = STATE) { return path.join(root, aliasName(alias)); }
export function loadAccount(alias, root = STATE) {
  const dir = accountDir(alias, root);
  noSymlinks(dir);
  const marker = path.join(dir, 'account.json');
  if (!fs.existsSync(marker)) fail('setup_required', 'Initialize this Word browser account with the Microsoft setup entrypoint.');
  noSymlinks(marker);
  const account = readJSON(marker);
  if (account.kind !== 'agent-hands-word-v1' || account.alias !== alias || !/^[0-9a-f-]{36}$/.test(account.owner)) fail('unsafe_state', 'Invalid Word browser ownership marker.');
  const browserDir = path.join(dir, 'browser');
  noSymlinks(browserDir);
  const browserOwner = path.join(browserDir, 'agent-hands-owner.json');
  noSymlinks(browserOwner);
  if (!fs.existsSync(browserOwner) || readJSON(browserOwner).owner !== account.owner) fail('unsafe_state', 'Browser directory is not owned by this tool.');
  if (!Number.isInteger(account.port) || account.port < 1024 || account.port > 65535 || !/^[a-f0-9]{48}$/.test(account.secret) || !/^[0-9a-f-]{36}$/.test(account.addinId)) fail('unsafe_state', 'Invalid local bridge configuration.');
  return {...account, dir, browserDir};
}
export function lockAccount(account) {
  const file = path.join(account.dir, 'lock.json');
  try { writeJSON(file, {pid: process.pid, owner: account.owner, created: new Date().toISOString()}, true); }
  catch (error) { if (error.code === 'EEXIST') fail('profile_busy', 'This tool profile is locked. Do not delete the lock until its recorded process and owned browser have stopped.'); throw error; }
  return () => fs.unlinkSync(file);
}
export function recoveryStatus(account, probe = pid => process.kill(pid, 0)) {
  const file = path.join(account.dir, 'lock.json');
  let controller = 'not_recorded', lockPresent = false;
  try {
    const lock = readJSON(file); lockPresent = true;
    if (lock.owner !== account.owner || !Number.isSafeInteger(lock.pid) || lock.pid <= 0) fail('unsafe_state', 'Invalid profile lock. Inspect private recovery state manually.');
    try { probe(lock.pid); controller = 'running'; }
    catch (error) { controller = error.code === 'ESRCH' ? 'not_running' : 'unknown'; }
  } catch (error) { if (error.code !== 'ENOENT') throw error; }
  const singletonMarkers = [];
  for (const name of ['SingletonLock', 'SingletonSocket', 'SingletonCookie']) {
    try { fs.lstatSync(path.join(account.browserDir, name)); singletonMarkers.push(name); }
    catch (error) { if (error.code !== 'ENOENT') throw error; }
  }
  return {status: 'recovery_inspection', lockPresent, controller, singletonMarkers, browserStopped: 'not_established', automaticRecoveryAllowed: false, next: 'Establish that the exact owned browser and controller stopped before manual lock recovery. Preserve profiles and dispatch journals; use word verify after an interrupted edit.'};
}
export function targetFromMetadata(alias, drive, item, meta, parent) {
  identifier(drive); identifier(item);
  if (meta.id !== item || meta.parentReference?.driveId !== drive || !meta.name?.toLowerCase().endsWith('.docx') || !meta.file) fail('target_mismatch', 'Graph metadata does not identify the requested DOCX.');
  const url = new URL(meta.webUrl);
  if (url.protocol !== 'https:' || url.username || url.password || url.port || !/(^|\.)sharepoint\.com$/.test(url.hostname)) fail('unsupported_target', 'Only HTTPS commercial SharePoint/OneDrive for Business DOCX URLs are supported.');
  const guid = (url.searchParams.get('sourcedoc') || '').replace(/[{}]/g, '').toLowerCase();
  if (url.pathname.endsWith('/Doc.aspx') && !/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(guid)) fail('unsupported_target', 'Missing document identity in Graph webUrl.');
  if (!guid && !url.pathname.toLowerCase().endsWith('.docx')) fail('unsupported_target', 'Graph webUrl does not provide a verifiable document identity.');
  let canonicalPath = guid ? null : decodeURIComponent(url.pathname);
  if (parent) {
    const folder = new URL(parent.webUrl);
    if (parent.id !== meta.parentReference.id || folder.origin !== url.origin || folder.search || folder.hash || folder.username || folder.password || /[\\/]/.test(meta.name)) fail('target_mismatch', 'Parent metadata does not establish the canonical document path.');
    canonicalPath = decodeURIComponent(folder.pathname).replace(/\/$/, '') + '/' + meta.name;
  }
  const site = url.pathname.match(/^\/(personal|sites|teams)\/[^/]+(?=\/)/)?.[0] || '';
  return {alias, drive, item, name: meta.name, webUrl: url.href, origin: url.origin, pathname: decodeURIComponent(url.pathname), canonicalPath, guid, identityUrl: `${url.origin}${site}/_api/web/currentuser?$select=Email,LoginName`};
}
export function sameDocument(actual, target) {
  try {
    const url = new URL(actual);
    if (url.origin !== target.origin) return false;
    const guid = (url.searchParams.get('sourcedoc') || '').replace(/[{}]/g, '').toLowerCase();
    return !!(target.guid && url.pathname.endsWith('/Doc.aspx') && guid === target.guid) || decodeURIComponent(url.pathname) === (target.canonicalPath || (!target.guid && target.pathname));
  } catch { return false; }
}
export function checkAccount(profile, current) {
  const expected = [profile.userPrincipalName, profile.mail].filter(Boolean).map(v => v.toLowerCase());
  const actual = [current.Email, current.LoginName?.split('|').at(-1)].filter(Boolean).map(v => v.toLowerCase());
  if (!expected.length || !actual.some(v => expected.includes(v))) fail('account_mismatch', 'The owned browser identity does not match the selected Graph account.');
}
export function validateEdit(find, replacement) {
  if (typeof find !== 'string' || !find.trim() || find.length > 255 || /[\r\n\t\x00-\x1f^]/.test(find)) fail('unsupported_edit', 'Find must be 1–255 literal characters in one paragraph, without Word search control characters.');
  if (typeof replacement !== 'string' || replacement.length > 4000 || /[\r\n\t\x00-\x1f]/.test(replacement) || replacement === find) fail('unsupported_edit', 'Replacement must be different, at most 4000 characters, and contain no paragraph or control characters.');
}
export function previewParagraphs(paragraphs, find, replacement) {
  validateEdit(find, replacement);
  if (!Array.isArray(paragraphs) || paragraphs.some(p => typeof p !== 'string') || paragraphs.join('').length > MAX_TEXT) fail('document_too_large', 'Document exceeds the bounded read limit.');
  const matches = paragraphs.filter(p => p.includes(find));
  if (matches.length !== 1 || matches[0].split(find).length !== 2) fail('ambiguous_anchor', 'Find must occur exactly once in the document body.');
  const before = matches[0], after = before.replace(find, () => replacement);
  if (paragraphs.includes(after)) fail('ambiguous_result', 'The resulting paragraph already exists; choose a more specific edit.');
  return {find, replacement, before, after};
}
export function makePlan(target, edit) {
  const plan = {version: 1, id: randomUUID(), created: new Date().toISOString(), target, edit};
  return {...plan, hash: hash(plan)};
}
export function verifyPlan(plan, expectedHash) {
  const {hash: digest, ...content} = plan;
  if (digest !== hash(content) || digest !== expectedHash) fail('preview_mismatch', 'The supplied hash does not match this stored preview.');
  validateEdit(plan.edit.find, plan.edit.replacement);
  if (plan.edit.after !== plan.edit.before.replace(plan.edit.find, () => plan.edit.replacement)) fail('preview_mismatch', 'Inconsistent preview.');
}
export function operationFiles(account, id) {
  if (!/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(id || '')) fail('invalid_plan', 'Use the operation ID returned by preview.');
  return {plan: path.join(account.dir, 'plans', `${id}.json`), journal: path.join(account.dir, 'plans', `${id}.journal.json`)};
}
export function markDispatch(journal, plan) {
  if (fs.existsSync(journal)) fail('already_dispatched', 'This operation has a dispatch record. Use verify; never replay it automatically.');
  writeJSON(journal, {operation: plan.id, hash: plan.hash, status: 'uncertain_after_dispatch', time: new Date().toISOString()}, true);
}
