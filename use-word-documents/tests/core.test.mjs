import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {zipSync, strToU8} from 'fflate';
import {previewParagraphs, makePlan, verifyPlan, targetFromMetadata, sameDocument, checkAccount, writeJSON, markDispatch, lockAccount, loadAccount, noSymlinks} from '../scripts/core.mjs';
import {docxParagraphs, docxStartup, cloudResult} from '../scripts/cloud.mjs';
import {initialize, launchOptions, browserIdentity} from '../scripts/browser.mjs';
import {manifest} from '../scripts/bridge.mjs';

export const target = {alias: 'demo', drive: 'drive1', item: 'item1', name: 'Test.docx', origin: 'https://example.sharepoint.com', pathname: '/sites/demo/_layouts/15/Doc.aspx', guid: '12345678-1234-1234-1234-123456789abc', webUrl: 'https://example.sharepoint.com/sites/demo/_layouts/15/Doc.aspx?sourcedoc=%7B12345678-1234-1234-1234-123456789abc%7D'};
const edit = previewParagraphs(['ALPHA: old', 'BETA: other'], 'old', '$new');
test('previews bind only the unique target paragraph and preserve replacement literals', () => {
  assert.equal(edit.after, 'ALPHA: $new');
  assert.deepEqual(previewParagraphs(['ALPHA: old', 'BETA: concurrent change'], 'old', '$new'), edit);
  assert.notDeepEqual(previewParagraphs(['ALPHA changed: old'], 'old', '$new'), edit);
  for (const paragraphs of [['old', 'old'], ['old old'], ['nothing']]) assert.throws(() => previewParagraphs(paragraphs, 'old', 'new'), {code: 'ambiguous_anchor'});
  assert.throws(() => previewParagraphs(['old', 'new'], 'old', 'new'), {code: 'ambiguous_result'});
  for (const find of ['', '^p', 'a\nb', 'x'.repeat(256)]) assert.throws(() => previewParagraphs([find], find, 'new'), {code: 'unsupported_edit'});
});
test('preview digest detects content, target and operation tampering', () => {
  const plan = makePlan(target, edit);
  verifyPlan(plan, plan.hash);
  assert.throws(() => verifyPlan({...plan, target: {...target, item: 'other'}}, plan.hash), {code: 'preview_mismatch'});
  assert.throws(() => verifyPlan(plan, 'wrong'), {code: 'preview_mismatch'});
});
test('document and selected browser account identity are exact', () => {
  const meta = {id: target.item, parentReference: {driveId: target.drive}, name: target.name, file: {}, webUrl: target.webUrl};
  const checked = targetFromMetadata('demo', target.drive, target.item, meta);
  assert.equal(checked.identityUrl, 'https://example.sharepoint.com/sites/demo/_api/web/currentuser?$select=Email,LoginName');
  assert.ok(sameDocument(target.webUrl, checked));
  assert.ok(!sameDocument(target.webUrl.replace('example.', 'wrong.'), checked));
  assert.ok(!sameDocument(target.webUrl.replace('123456789abc', '123456789abd'), checked));
  const withPath = targetFromMetadata('demo', target.drive, target.item, {...meta, parentReference: {...meta.parentReference, id: 'folder1'}}, {id: 'folder1', webUrl: 'https://example.sharepoint.com/sites/demo/Documents'});
  assert.ok(sameDocument('https://example.sharepoint.com/sites/demo/Documents/Test.docx', withPath));
  assert.ok(!sameDocument('https://example.sharepoint.com/sites/demo/Documents/Other.docx', withPath));
  assert.throws(() => targetFromMetadata('demo', target.drive, target.item, {...meta, webUrl: 'https://example.sharepoint.com.evil.test/Test.docx'}), {code: 'unsupported_target'});
  assert.throws(() => targetFromMetadata('demo', 'wrong', target.item, meta), {code: 'target_mismatch'});
  checkAccount({userPrincipalName: 'editor@example.test'}, {LoginName: 'i:0#.f|membership|EDITOR@example.test'});
  assert.throws(() => checkAccount({mail: 'editor@example.test'}, {Email: 'other@example.test'}), {code: 'account_mismatch'});
});
test('browser identity allows silent sign-in to finish and refuses a different account', async () => {
  let attempts = 0;
  const context = {request: {get: async () => { attempts++; return {ok: () => attempts > 1, json: async () => ({Email: 'editor@example.test'})}; }}};
  await browserIdentity(context, {identityUrl: 'https://example.sharepoint.com/_api/web/currentuser'}, {mail: 'editor@example.test'});
  assert.equal(attempts, 2);
  await assert.rejects(browserIdentity(context, {identityUrl: 'https://example.sharepoint.com/_api/web/currentuser'}, {mail: 'other@example.test'}), {code: 'account_mismatch'});
});
test('expired identity requires authentication and a renewed identity is checked again', async t => {
  let now = 0, renewed = false, requests = 0;
  const clock = t.mock.method(Date, 'now', () => now);
  const context = {request: {get: async () => {
    requests++;
    if (!renewed) { now += 16_000; return {ok: () => false}; }
    return {ok: () => true, json: async () => ({Email: 'editor@example.test'})};
  }}};
  const selected = {identityUrl: 'https://example.sharepoint.com/_api/web/currentuser'}, profile = {mail: 'editor@example.test'};
  try {
    await assert.rejects(browserIdentity(context, selected, profile), {code: 'authentication_required'});
    renewed = true;
    await browserIdentity(context, selected, profile);
    assert.equal(requests, 2);
  } finally { clock.mock.restore(); }
});
test('private profile ownership, lock and dispatch journal never adopt or replay', async t => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'word-core-'));
  try {
    const account = await initialize('demo', 43439, fs.realpathSync(root));
    assert.equal(loadAccount('demo', fs.realpathSync(root)).browserDir, account.browserDir);
    assert.equal(launchOptions(account).headless, true);
    assert.equal(launchOptions(account).chromiumSandbox, true);
    assert.deepEqual(launchOptions(account).ignoreDefaultArgs, ['--use-mock-keychain', '--password-store=basic']);
    assert.equal(launchOptions(account).args.length, 1);
    assert.match(launchOptions(account).args[0], /^--ignore-certificate-errors-spki-list=/);
    assert.ok(!('ignoreHTTPSErrors' in launchOptions(account)));
    const clock = t.mock.method(Date, 'now', () => Date.parse('2100-01-01T00:00:00Z'));
    try { assert.throws(() => launchOptions(account), {code: 'certificate_expired'}); }
    finally { clock.mock.restore(); }
    const release = lockAccount(account);
    assert.throws(() => lockAccount(account), {code: 'profile_busy'});
    release();
    const plan = makePlan(target, edit), journal = path.join(account.dir, 'dispatch.json');
    markDispatch(journal, plan);
    assert.equal(JSON.parse(fs.readFileSync(journal)).status, 'uncertain_after_dispatch');
    assert.throws(() => markDispatch(journal, plan), {code: 'already_dispatched'});
    assert.match(manifest(account), /Office.AutoShowTaskpaneWithDocument/);
    await assert.rejects(initialize('demo', 43439, fs.realpathSync(root)), {code: 'already_initialized'});
    fs.symlinkSync(path.join(root, 'missing'), path.join(root, 'link'));
    assert.throws(() => noSymlinks(path.join(root, 'link')), {code: 'unsafe_state'});
    writeJSON(path.join(account.browserDir, 'agent-hands-owner.json'), {owner: 'wrong'});
    assert.throws(() => loadAccount('demo', fs.realpathSync(root)), {code: 'unsafe_state'});
  } finally { fs.rmSync(root, {recursive: true, force: true}); }
});
test('independent DOCX verification tolerates other-paragraph edits and refuses revisions', () => {
  const packageFor = body => Buffer.from(zipSync({'word/document.xml': strToU8(`<?xml version="1.0"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>${body}</w:body></w:document>`)}));
  const paragraphs = docxParagraphs(packageFor('<w:p><w:r><w:rPr><w:b/></w:rPr><w:t>ALPHA: $new</w:t></w:r></w:p><w:p><w:r><w:t>BETA: concurrent &amp; preserved</w:t></w:r></w:p>'));
  assert.deepEqual(paragraphs, ['ALPHA: $new', 'BETA: concurrent & preserved']);
  assert.equal(cloudResult(paragraphs, edit), 'cloud_text_verified');
  assert.equal(cloudResult(['ALPHA: old'], edit), 'original_text_observed');
  assert.equal(cloudResult(['ALPHA: conflicting'], edit), 'cloud_conflict_or_unverified');
  assert.throws(() => docxParagraphs(packageFor('<w:p><w:ins><w:r><w:t>revision</w:t></w:r></w:ins></w:p>')), {code: 'unsupported_document'});
  assert.deepEqual(docxParagraphs(packageFor('<w:p><w:fldSimple><w:r><w:t>Generated value</w:t></w:r></w:fldSimple></w:p>')), []);
  const tracking = Buffer.from(zipSync({'word/document.xml': strToU8('<w:document xmlns:w="urn:word"><w:body/></w:document>'), 'word/settings.xml': strToU8('<w:settings xmlns:w="urn:word"><w:trackRevisions/></w:settings>')}));
  assert.throws(() => docxParagraphs(tracking), {code: 'unsupported_document'});
  assert.throws(() => docxParagraphs(Buffer.from(zipSync({'other.xml': strToU8('missing')}))), {code: 'invalid_docx'});
});
test('cloud startup verification binds the exact add-in and refuses ambiguous or unsafe metadata', () => {
  const id = '12345678-1234-1234-1234-123456789abc';
  const xml = (identifier = id, value = 'true') => `<we:webextension xmlns:we="urn:extensions"><we:reference id="${identifier}"/><we:properties><we:property name="Office.AutoShowTaskpaneWithDocument" value="${value}"/></we:properties></we:webextension>`;
  const packed = (entries, connected = true) => Buffer.from(zipSync(Object.fromEntries(Object.entries({...connected && {
    '_rels/.rels': '<Relationships><Relationship Id="root1" Type="http://schemas.microsoft.com/office/2011/relationships/webextensiontaskpanes" Target="word/webextensions/taskpanes.xml"/></Relationships>',
    'word/webextensions/_rels/taskpanes.xml.rels': `<Relationships><Relationship Id="pane1" Type="http://schemas.microsoft.com/office/2011/relationships/webextension" Target="/${Object.keys(entries)[0]}"/></Relationships>`,
    'word/webextensions/taskpanes.xml': '<wetp:taskpanes xmlns:wetp="urn:taskpanes" xmlns:r="urn:relationships"><wetp:taskpane visibility="0"><wetp:webextensionref r:id="pane1"/></wetp:taskpane></wetp:taskpanes>'
  }, ...entries}).map(([name, value]) => [name, strToU8(value)]))));
  assert.equal(docxStartup(packed({'word/webextensions/webextension.xml': xml()}), id), true);
  assert.equal(docxStartup(packed({'word/webextensions/webextension2.xml': xml(id.toUpperCase())}), id), true);
  assert.equal(docxStartup(packed({'word/webextensions/webextension.xml': xml('other')}), id), false);
  assert.equal(docxStartup(packed({'word/webextensions/webextension.xml': xml(id, 'false')}), id), false);
  assert.equal(docxStartup(packed({'word/webextensions/webextension.xml': xml()}, false), id), false);
  assert.equal(docxStartup(packed({'word/webextensions/webextension.xml': xml(), 'word/webextensions/_rels/taskpanes.xml.rels': '<Relationships/>'}), id), false);
  assert.equal(docxStartup(packed({'word/webextensions/webextension.xml': xml(), 'word/webextensions/webextension2.xml': xml()}), id), false);
  assert.equal(docxStartup(packed({'word/document.xml': '<document/>'}), id), false);
  assert.throws(() => docxStartup(packed({'word/webextensions/webextension.xml': '<!DOCTYPE we [<!ENTITY x "test">]>' + xml()}), id), {code: 'invalid_docx'});
});
