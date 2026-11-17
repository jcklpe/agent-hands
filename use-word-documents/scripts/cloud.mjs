import fs from 'node:fs';
import path from 'node:path';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {unzipSync, strFromU8} from 'fflate';
import {XMLParser, XMLValidator} from 'fast-xml-parser';
import {ROOT, MAX_TEXT, fail, targetFromMetadata} from './core.mjs';

const exec = promisify(execFile);
async function provider(relative, args, json = true) {
  try {
    const result = await exec('bash', [path.join(ROOT, relative), ...args], {maxBuffer: 2_000_000, timeout: 120_000});
    return json ? JSON.parse(result.stdout) : undefined;
  } catch { fail('provider_failed', 'The Microsoft CLI request failed. Check the selected alias with setup-microsoft-services and use-microsoft-files; no browser mutation was retried.'); }
}
export async function cloudTarget(alias, drive, item) {
  const profile = await provider('setup-microsoft-services/scripts/authorize', ['profile', alias, '--json']);
  const meta = await provider('use-microsoft-files/scripts/files', ['meta', alias, item, '--drive', drive, '--json']);
  if (meta.size > 20_000_000) fail('document_too_large', 'This capability supports DOCX files up to 20 MB.');
  const parent = new URL(meta.webUrl).searchParams.has('sourcedoc') && meta.parentReference?.id ? await provider('use-microsoft-files/scripts/files', ['meta', alias, meta.parentReference.id, '--drive', drive, '--json']) : undefined;
  return {profile, target: targetFromMetadata(alias, drive, item, meta, parent)};
}
export async function requireWrite(alias) { return provider('setup-microsoft-services/scripts/word-access', ['check-write', alias]); }
function parts(bytes, selected) {
  if (bytes.length > 20_000_000) fail('document_too_large', 'Downloaded DOCX exceeds 20 MB.');
  let total = 0;
  const entries = unzipSync(new Uint8Array(bytes), {filter(entry) {
    total += entry.originalSize;
    if (!Number.isSafeInteger(total) || total > 64_000_000 || entry.originalSize < 0) fail('document_too_large', 'DOCX expansion exceeds the verification limit.');
    if (selected(entry.name) && entry.originalSize > 4_000_000) fail('document_too_large', 'Document XML exceeds 4 MB.');
    return selected(entry.name);
  }});
  return entries;
}
export function docxStartup(bytes, addinId) {
  const links = ['_rels/.rels', 'word/webextensions/taskpanes.xml', 'word/webextensions/_rels/taskpanes.xml.rels'];
  const entries = parts(bytes, name => /^word\/webextensions\/webextension\d*\.xml$/.test(name) || links.includes(name));
  const parser = new XMLParser({removeNSPrefix: true, ignoreAttributes: false, trimValues: false, parseTagValue: false});
  const documents = {};
  let matches = 0, enabled = false, extensionPart;
  const array = value => value === undefined ? [] : Array.isArray(value) ? value : [value];
  for (const [name, data] of Object.entries(entries)) {
    const xml = strFromU8(data);
    if (/<!DOCTYPE|<!ENTITY/i.test(xml) || XMLValidator.validate(xml) !== true) fail('invalid_docx', 'Add-in settings XML is not supported.');
    documents[name] = parser.parse(xml);
    const extension = documents[name].webextension;
    if (extension?.reference?.['@_id']?.toLowerCase() !== addinId.toLowerCase()) continue;
    matches++; extensionPart = name;
    const props = extension.properties?.property;
    enabled = array(props).some(p => p?.['@_name'] === 'Office.AutoShowTaskpaneWithDocument' && p['@_value'] === 'true');
  }
  if (matches !== 1 || !enabled) return false;
  const resolves = (rel, base, expected, type) => rel['@_TargetMode'] !== 'External' && rel['@_Type'] === `http://schemas.microsoft.com/office/2011/relationships/${type}` && typeof rel['@_Target'] === 'string' && path.posix.resolve('/', base, rel['@_Target']) === '/' + expected;
  const roots = array(documents['_rels/.rels']?.Relationships?.Relationship).filter(r => resolves(r, '', 'word/webextensions/taskpanes.xml', 'webextensiontaskpanes'));
  const references = array(documents['word/webextensions/_rels/taskpanes.xml.rels']?.Relationships?.Relationship).filter(r => resolves(r, 'word/webextensions', extensionPart, 'webextension'));
  const panes = array(documents['word/webextensions/taskpanes.xml']?.taskpanes?.taskpane);
  return roots.length === 1 && references.length === 1 && panes.filter(p => p.webextensionref?.['@_id'] === references[0]['@_Id']).length === 1;
}
export function docxParagraphs(bytes) {
  const entries = parts(bytes, name => ['word/document.xml', 'word/settings.xml'].includes(name));
  if (!entries['word/document.xml']) fail('invalid_docx', 'DOCX has no document body.');
  const xml = strFromU8(entries['word/document.xml']);
  if (/<!DOCTYPE|<!ENTITY/i.test(xml) || XMLValidator.validate(xml) !== true) fail('invalid_docx', 'Document XML is not supported.');
  const parser = new XMLParser({preserveOrder: true, removeNSPrefix: true, ignoreAttributes: false, trimValues: false, parseTagValue: false});
  const parsed = parser.parse(xml);
  const has = (nodes, names) => nodes.some(n => Object.entries(n).some(([key, value]) => names.includes(key) || Array.isArray(value) && has(value, names)));
  if (has(parsed, ['ins', 'del', 'moveFrom', 'moveTo'])) fail('unsupported_document', 'Documents with tracked revisions require a separate workflow.');
  if (entries['word/settings.xml']) {
    const settingsXML = strFromU8(entries['word/settings.xml']);
    if (/<!DOCTYPE|<!ENTITY/i.test(settingsXML) || XMLValidator.validate(settingsXML) !== true) fail('invalid_docx', 'Document settings are not supported.');
    const settings = parser.parse(settingsXML).find(n => n.settings)?.settings || [];
    const tracking = settings.find(n => n.trackRevisions);
    if (tracking && !['0', 'false', 'off'].includes(String(tracking[':@']?.['@_val']))) fail('unsupported_document', 'Track Changes is enabled; use a revision-aware workflow.');
  }
  const body = parsed.find(n => n.document)?.document.find(n => n.body)?.body;
  if (!body) fail('invalid_docx', 'Document body is missing.');
  function text(nodes) {
    return nodes.map(n => n.t ? n.t.map(t => t['#text'] || '').join('') : n.tab ? '\t' : n.br ? '\n' : Object.entries(n).filter(([k, v]) => k !== ':@' && Array.isArray(v)).map(([, v]) => text(v)).join('')).join('');
  }
  const paragraphs = body.filter(n => n.p && !has(n.p, ['fldChar', 'fldSimple', 'sdt', 'hyperlink', 'object'])).map(n => text(n.p));
  if (paragraphs.join('').length > MAX_TEXT) fail('document_too_large', 'Document exceeds the bounded text limit.');
  return paragraphs;
}
async function download(account, target, inspect) {
  const dir = fs.mkdtempSync(path.join(account.dir, 'download-'));
  fs.chmodSync(dir, 0o700);
  try {
    const file = path.join(dir, 'readback.docx');
    await provider('use-microsoft-files/scripts/files', ['download', target.alias, target.item, '--drive', target.drive, '--out', file], false);
    return inspect(fs.readFileSync(file));
  } finally { fs.rmSync(dir, {recursive: true, force: true}); }
}
export async function downloadParagraphs(account, target) { return download(account, target, docxParagraphs); }
export async function downloadStartup(account, target) { return download(account, target, bytes => docxStartup(bytes, account.addinId)); }
export function cloudResult(paragraphs, edit) {
  const oldCount = paragraphs.filter(p => p === edit.before).length;
  const newCount = paragraphs.filter(p => p === edit.after).length;
  return newCount === 1 && oldCount === 0 ? 'cloud_text_verified' : oldCount === 1 && newCount === 0 ? 'original_text_observed' : 'cloud_conflict_or_unverified';
}
