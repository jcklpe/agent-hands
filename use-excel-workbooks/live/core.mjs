import fs from 'node:fs';
import path from 'node:path';
import {randomBytes, randomUUID} from 'node:crypto';
import {loadAccount, privateDir, readJSON, writeJSON, fail, identifier} from '../../use-word-documents/scripts/core.mjs';
export * from '../../use-word-documents/scripts/core.mjs';
export function requireMacOS() { if (process.platform !== 'darwin') fail('unsupported_platform', 'Excel live editing is currently supported on macOS only. Windows/Linux validation is deferred.'); }
export function excelAccount(alias) {
  const base = loadAccount(alias), excelDir = path.join(base.dir, 'excel');
  privateDir(excelDir); privateDir(path.join(excelDir, 'plans'));
  const file = path.join(excelDir, 'account.json');
  if (!fs.existsSync(file)) writeJSON(file, {kind:'agent-hands-excel-v1', owner:base.owner, addinId:randomUUID(), secret:randomBytes(24).toString('hex')}, true);
  const settings = readJSON(file);
  if (settings.kind !== 'agent-hands-excel-v1' || settings.owner !== base.owner || !/^[0-9a-f-]{36}$/.test(settings.addinId) || !/^[0-9a-f]{48}$/.test(settings.secret)) fail('unsafe_state', 'Invalid Excel bridge ownership marker.');
  return {...base, ...settings, excelDir};
}
export function targetFromMetadata(alias, drive, item, meta, parent) {
  identifier(drive); identifier(item);
  if (meta.id !== item || meta.parentReference?.driveId !== drive || !meta.name?.toLowerCase().endsWith('.xlsx') || !meta.file) fail('target_mismatch', 'Graph metadata does not identify the requested XLSX.');
  const url = new URL(meta.webUrl);
  if (url.protocol !== 'https:' || url.username || url.password || url.port || !/(^|\.)sharepoint\.com$/.test(url.hostname)) fail('unsupported_target', 'Only HTTPS commercial SharePoint/OneDrive for Business XLSX URLs are supported.');
  const guid = (url.searchParams.get('sourcedoc') || '').replace(/[{}]/g, '').toLowerCase();
  if (url.pathname.endsWith('/Doc.aspx') && !/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(guid)) fail('unsupported_target', 'Missing document identity in Graph webUrl.');
  if (!guid && !url.pathname.toLowerCase().endsWith('.xlsx')) fail('unsupported_target', 'Graph webUrl does not provide a verifiable document identity.');
  let canonicalPath = guid ? null : decodeURIComponent(url.pathname);
  if (parent) {
    const folder = new URL(parent.webUrl);
    if (parent.id !== meta.parentReference.id || folder.origin !== url.origin || folder.search || folder.hash || folder.username || folder.password || /[\\/]/.test(meta.name)) fail('target_mismatch', 'Parent metadata does not establish the canonical document path.');
    canonicalPath = decodeURIComponent(folder.pathname).replace(/\/$/, '') + '/' + meta.name;
  }
  const site = url.pathname.match(/^\/(personal|sites|teams)\/[^/]+(?=\/)/)?.[0] || '';
  return {alias, drive, item, name: meta.name, webUrl: url.href, origin: url.origin, pathname: decodeURIComponent(url.pathname), canonicalPath, guid, identityUrl: `${url.origin}${site}/_api/web/currentuser?$select=Email,LoginName`};
}
