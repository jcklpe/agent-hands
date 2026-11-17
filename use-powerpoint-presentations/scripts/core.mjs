import fs from 'node:fs';
import path from 'node:path';
import {randomBytes, randomUUID} from 'node:crypto';
import {loadAccount, privateDir, readJSON, writeJSON, fail, hash, identifier} from '../../use-word-documents/scripts/core.mjs';
export * from '../../use-word-documents/scripts/core.mjs';
export const MAX_SLIDES = 100, MAX_SHAPES = 5000;
export function requireMacOS() { if (process.platform !== 'darwin') fail('unsupported_platform', 'PowerPoint live editing is currently supported on macOS only. Windows/Linux validation is deferred.'); }
export function powerpointAccount(alias) {
  const base = loadAccount(alias), pptDir = path.join(base.dir, 'powerpoint');
  privateDir(pptDir); privateDir(path.join(pptDir, 'plans'));
  const file = path.join(pptDir, 'account.json');
  if (!fs.existsSync(file)) writeJSON(file, {kind:'agent-hands-powerpoint-v1', owner:base.owner, addinId:randomUUID(), secret:randomBytes(24).toString('hex')}, true);
  const settings = readJSON(file);
  if (settings.kind !== 'agent-hands-powerpoint-v1' || settings.owner !== base.owner || !/^[0-9a-f-]{36}$/.test(settings.addinId) || !/^[0-9a-f]{48}$/.test(settings.secret)) fail('unsafe_state', 'Invalid PowerPoint bridge ownership marker.');
  return {...base, ...settings, pptDir};
}
export function shapeIdentity(slideId, shapeId) {
  if (!/^[0-9]{1,10}(#[0-9]{1,20})?$/.test(slideId || '') || !/^[0-9]{1,10}$/.test(shapeId || '')) fail('invalid_shape', 'Use the exact slideId and shapeId returned by read.');
}
export function validateEdit(find, replacement) {
  if (typeof find !== 'string' || !find.trim() || find.length > 255 || /[\x00-\x1f\x7f]/.test(find)) fail('unsupported_edit', 'Find must contain 1–255 literal characters within one text paragraph.');
  if (typeof replacement !== 'string' || replacement.length > 1000 || /[\x00-\x1f\x7f]/.test(replacement) || replacement === find) fail('unsupported_edit', 'Use different replacement text of at most 1000 characters, without control characters.');
}
export function previewShapes(shapes, slideId, shapeId, find, replacement) {
  shapeIdentity(slideId, shapeId); validateEdit(find, replacement);
  if (!Array.isArray(shapes) || shapes.length > MAX_SHAPES) fail('presentation_too_large', 'The presentation exceeds the bounded shape limit.');
  const matches = shapes.filter(s => s.slideId === slideId && s.shapeId === shapeId);
  if (matches.length !== 1 || !matches[0].supported || typeof matches[0].text !== 'string') fail('unsupported_shape', 'Select one ordinary top-level text box or geometric shape from read.');
  const s = matches[0];
  if (/[\uD800-\uDFFF]/.test(s.text + replacement)) fail('unsupported_edit', 'Selected shape text and replacement must use BMP characters; supplementary-character offsets are not validated.');
  if (s.text.split(find).length !== 2) fail('ambiguous_anchor', 'Find must occur exactly once in the selected shape.');
  return {slideId, shapeId, name:s.name, type:s.type, before:s.text, find, replacement, after:s.text.replace(find, () => replacement)};
}
export function makePlan(target, edit) {
  const plan = {version:1, kind:'agent-hands-powerpoint-v1', id:randomUUID(), created:new Date().toISOString(), target, edit};
  return {...plan, hash:hash(plan)};
}
export function verifyPlan(plan, expectedHash) {
  const {hash:digest, ...content} = plan;
  if (plan.kind !== 'agent-hands-powerpoint-v1' || plan.version !== 1 || digest !== hash(content) || digest !== expectedHash) fail('preview_mismatch', 'The supplied hash does not match this PowerPoint preview.');
  shapeIdentity(plan.edit.slideId, plan.edit.shapeId); validateEdit(plan.edit.find, plan.edit.replacement);
  if (typeof plan.edit.before !== 'string' || /[\uD800-\uDFFF]/.test(plan.edit.before + plan.edit.replacement) || plan.edit.before.length > 200000 || plan.edit.before.split(plan.edit.find).length !== 2 || plan.edit.after !== plan.edit.before.replace(plan.edit.find, () => plan.edit.replacement)) fail('preview_mismatch', 'Inconsistent shape preview.');
}
export function operationFiles(account, id) {
  if (!/^[0-9a-f]{8}(-[0-9a-f]{4}){3}-[0-9a-f]{12}$/.test(id || '')) fail('invalid_plan', 'Use the operation ID returned by preview.');
  return {plan:path.join(account.pptDir,'plans',`${id}.json`), journal:path.join(account.pptDir,'plans',`${id}.journal.json`)};
}
export function targetFromMetadata(alias, drive, item, meta, parent) {
  identifier(drive); identifier(item);
  if (meta.id !== item || meta.parentReference?.driveId !== drive || !meta.name?.toLowerCase().endsWith('.pptx') || !meta.file) fail('target_mismatch', 'Graph metadata does not identify the requested PPTX.');
  const url = new URL(meta.webUrl);
  if (url.protocol !== 'https:' || url.username || url.password || url.port || !/(^|\.)sharepoint\.com$/.test(url.hostname)) fail('unsupported_target', 'Only HTTPS commercial SharePoint/OneDrive for Business PPTX URLs are supported.');
  const guid = (url.searchParams.get('sourcedoc') || '').replace(/[{}]/g, '').toLowerCase();
  if (url.pathname.endsWith('/Doc.aspx') && !/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}$/.test(guid)) fail('unsupported_target', 'Missing document identity in Graph webUrl.');
  if (!guid && !url.pathname.toLowerCase().endsWith('.pptx')) fail('unsupported_target', 'Graph webUrl does not provide a verifiable document identity.');
  let canonicalPath = guid ? null : decodeURIComponent(url.pathname);
  if (parent) {
    const folder = new URL(parent.webUrl);
    if (parent.id !== meta.parentReference.id || folder.origin !== url.origin || folder.search || folder.hash || folder.username || folder.password || /[\\/]/.test(meta.name)) fail('target_mismatch', 'Parent metadata does not establish the canonical document path.');
    canonicalPath = decodeURIComponent(folder.pathname).replace(/\/$/, '') + '/' + meta.name;
  }
  const site = url.pathname.match(/^\/(personal|sites|teams)\/[^/]+(?=\/)/)?.[0] || '';
  return {alias, drive, item, name: meta.name, webUrl: url.href, origin: url.origin, pathname: decodeURIComponent(url.pathname), canonicalPath, guid, identityUrl: `${url.origin}${site}/_api/web/currentuser?$select=Email,LoginName`};
}
