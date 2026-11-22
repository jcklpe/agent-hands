import fs from 'node:fs';
import path from 'node:path';
import {parseArgs} from 'node:util';
import {aliasName, identifier, loadAccount, lockAccount, writeJSON, readJSON, operationFiles, makePlan, verifyPlan, previewParagraphs, markDispatch, fail, sleep, recoveryStatus} from './core.mjs';
import {initialize, openBrowser, browserIdentity, renewCertificate} from './browser.mjs';
import {startBridge, manifest} from './bridge.mjs';
import {cloudTarget, requireWrite, downloadParagraphs, downloadStartup, cloudResult} from './cloud.mjs';
import {retentionPlan, retirePlanContent} from './retention.mjs';
import {cleanupTempRuns} from './temporary.mjs';
import {migrateState} from './migrate-state.mjs';
import {openAddinAutomatically} from './bootstrap.mjs';

const emit = value => process.stdout.write(JSON.stringify(value, null, 2) + '\n');
const help = setup => setup ? `word-browser init ALIAS --port PORT
word-browser retention ALIAS [--execute --hash SHA256]
word-browser cleanup-temp ALIAS [--execute]
word-browser migrate-state ALIAS [--execute]
word-browser recovery-status ALIAS
word-browser renew-certificate ALIAS [--execute]
word-browser login ALIAS --drive DRIVE --item ITEM
word-browser prepare ALIAS --drive DRIVE --item ITEM --execute
word-browser configure ALIAS --drive DRIVE --item ITEM --execute
The browser belongs only to Agent Hands. Login/configure are visible one-time setup.
Prepare installs/opens the add-in and saves startup headlessly for one authorized document.
Configure requires authorized add-in installation and saves automatic startup for the exact document.
` : `word read ALIAS --drive DRIVE --item ITEM
word preview ALIAS --drive DRIVE --item ITEM --find TEXT --replace TEXT
word apply ALIAS --plan ID --hash SHA256 --execute
word status ALIAS --plan ID
word verify ALIAS --plan ID
Read/preview/apply run headlessly in the tool-owned browser. Verify only downloads the cloud file.
Apply requires the exact preview hash and files.write_enabled. No whole-file upload or mutation retries.
`;
function parse(argv, setup) {
  const parsed = parseArgs({args: argv, allowPositionals: true, strict: true, options: {
    drive: {type: 'string'}, item: {type: 'string'}, find: {type: 'string'}, replace: {type: 'string'}, plan: {type: 'string'}, hash: {type: 'string'}, port: {type: 'string'}, execute: {type: 'boolean'}, help: {type: 'boolean'}
  }});
  if (!parsed.positionals.length || parsed.values.help || parsed.positionals[0] === 'help') return null;
  const [command, alias, ...extra] = parsed.positionals;
  const allowed = setup ? {init: ['port'], retention: ['execute', 'hash'], 'cleanup-temp': ['execute'], 'migrate-state': ['execute'], 'recovery-status': [], 'renew-certificate': ['execute'], login: ['drive', 'item'], prepare: ['drive', 'item', 'execute'], configure: ['drive', 'item', 'execute']} : {read: ['drive', 'item'], preview: ['drive', 'item', 'find', 'replace'], apply: ['plan', 'hash', 'execute'], status: ['plan'], verify: ['plan']};
  if (!allowed[command] || extra.length || Object.keys(parsed.values).some(key => !allowed[command].includes(key))) fail('invalid_arguments', 'Unsupported command or option; use --help.');
  return {command, alias: aliasName(alias), options: parsed.values};
}
export async function main(argv, setup = false) {
  let unlock, bridge, browser;
  let dispatchFile, activePlan, setupStarted = false;
  const cleanup = async () => {
    // Closing this context only stops the tool-owned browser. Never enumerate, signal or restore normal Chrome windows.
    if (browser) { const owned = browser; browser = null; await owned.context.close(); }
    if (bridge) { const ownBridge = bridge; bridge = null; await ownBridge.close(); }
    if (unlock) { const release = unlock; unlock = null; release(); }
  };
  let signalHandling = false;
  const signal = () => { if (!signalHandling) { signalHandling = true; void cleanup().finally(() => process.exit(130)); } };
  process.once('SIGINT', signal); process.once('SIGTERM', signal);
  try {
    const args = parse(argv, setup);
    if (!args) { process.stdout.write(help(setup)); return; }
    const {command, alias, options} = args;
    if (['apply', 'configure', 'prepare'].includes(command) && !options.execute) fail('execute_required', 'This write requires --execute and authorization for the selected document.');
    if (command === 'cleanup-temp') { emit(cleanupTempRuns(!options.execute)); return; }
    if (command === 'migrate-state') { emit(migrateState(alias, !!options.execute)); return; }
    if (command === 'init') {
      const account = await initialize(alias, Number(options.port));
      fs.writeFileSync(path.join(account.dir, 'manifest.xml'), manifest(account), {mode: 0o600, flag: 'wx'});
      emit({status: 'initialized', alias, manifest: path.join(account.dir, 'manifest.xml'), authentication: 'not_checked'});
      return;
    }
    const account = loadAccount(alias);
    if (command === 'retention') { emit(options.execute ? retirePlanContent(account, options.hash) : retentionPlan(account)); return; }
    if (command === 'recovery-status') { emit(recoveryStatus(account)); return; }
    if (command === 'renew-certificate') { emit(await renewCertificate(account, !!options.execute)); return; }
    unlock = lockAccount(account);
    let target, profile, plan, files;
    if (['status', 'apply', 'verify'].includes(command)) {
      files = operationFiles(account, options.plan);
      if (command === 'status' && !fs.existsSync(files.plan)) { emit({status: fs.existsSync(files.journal) ? 'plan_unavailable_with_receipt' : 'plan_unavailable', replayAllowed:false, ...(fs.existsSync(files.journal) ? {receipt:readJSON(files.journal)} : {})}); return; }
      plan = readJSON(files.plan);
      verifyPlan(plan, command === 'apply' ? options.hash : plan.hash);
      if (plan.target.alias !== alias) fail('account_mismatch', 'Preview belongs to a different account alias.');
      if (command === 'status') {
        emit(fs.existsSync(files.journal) ? readJSON(files.journal) : {status: 'not_dispatched', operation: plan.id}); return;
      }
      if (command === 'apply' && !options.execute) fail('execute_required', 'Apply requires --execute and the exact preview hash.');
      if (command === 'apply' && fs.existsSync(files.journal)) fail('already_dispatched', 'A dispatch record already exists. Use verify; this operation will not be sent again.');
      ({target, profile} = await cloudTarget(alias, identifier(plan.target.drive), identifier(plan.target.item)));
      if (target.origin !== plan.target.origin || target.guid !== plan.target.guid || target.pathname !== plan.target.pathname || target.canonicalPath !== plan.target.canonicalPath) fail('target_mismatch', 'The target identity changed after preview. Make a new preview.');
      if (command === 'verify') {
        const state = cloudResult(await downloadParagraphs(account, target), plan.edit);
        emit({status: state, operation: plan.id, dispatch: fs.existsSync(files.journal) ? readJSON(files.journal).status : 'not_dispatched', replayAllowed: false});
        if (state !== 'cloud_text_verified') process.exitCode = 1;
        return;
      }
    } else ({target, profile} = await cloudTarget(alias, identifier(options.drive), identifier(options.item)));
    if (['apply', 'configure', 'prepare'].includes(command)) {
      if (!options.execute) fail('execute_required', 'Startup configuration requires --execute after add-in installation is authorized.');
      await requireWrite(alias);
    }
    if (command !== 'login') bridge = await startBridge(account, target);
    if (command === 'configure') emit({status: 'setup_instructions', manifest: path.join(account.dir, 'manifest.xml'), instructions: 'In the separate Agent Hands window, sign in normally, then upload this manifest through Word Add-ins and open Agent Hands → Open Word bridge. The command will enable automatic startup for this document and close only its own browser.'});
    browser = await openBrowser(account, target, !['login', 'configure'].includes(command), bridge);
    await browserIdentity(browser.context, target, profile, ['login', 'configure'].includes(command));
    if (command === 'login') { emit({status: 'browser_account_verified', alias}); return; }
    let preparation;
    if (command === 'prepare') { setupStarted = true; preparation = await openAddinAutomatically(browser, bridge, account, target); }
    const readiness = await bridge.waitReady(command === 'configure' ? 600_000 : 90_000);
    await browserIdentity(browser.context, target, profile);
    if (command === 'prepare') {
      if (readiness.automaticStartup && await downloadStartup(account, target)) {
        emit({status: 'document_prepared', preparation, cloudStartupVerified: true, startupChanged: false, contentEditSent: false});
        return;
      }
      const result = await bridge.command('enable-startup');
      if (result.status !== 'startup_saved') { emit(result); process.exitCode = 1; return; }
      let persisted = false;
      for (let attempt = 0; attempt < 6; attempt++) {
        if (await downloadStartup(account, target)) { persisted = true; break; }
        await sleep(2000);
      }
      emit({status: persisted ? 'document_prepared' : 'startup_cloud_unverified', preparation, cloudStartupVerified: persisted, startupChanged: true, contentEditSent: false});
      if (!persisted) process.exitCode = 1;
      return;
    }
    if (command === 'configure') {
      const result = await bridge.command('enable-startup');
      emit({...result, next: 'Run word read headlessly to verify startup in a fresh process.', cloudPersistence: 'not_independently_verified'});
      if (result.status !== 'startup_saved') process.exitCode = 1;
      return;
    }
    const read = await bridge.command('read');
    if (read.status !== 'read_ok' || !Array.isArray(read.paragraphs)) fail(read.code || 'read_failed', 'Word did not return the bounded document read.');
    if (command === 'read') { emit({status: 'read_ok', target: {drive: target.drive, item: target.item, name: target.name}, paragraphs: read.paragraphs}); return; }
    if (command === 'preview') {
      const edit = previewParagraphs(read.paragraphs, options.find, options.replace);
      const cloud = await downloadParagraphs(account, target);
      if (cloudResult(cloud, edit) !== 'original_text_observed') fail('cloud_baseline_mismatch', 'The preview paragraph does not match cloud readback. Wait for synchronization, then preview again.');
      plan = makePlan(target, edit);
      writeJSON(operationFiles(account, plan.id).plan, plan, true);
      emit({status: 'preview', operation: plan.id, hash: plan.hash, name: target.name, before: edit.before, after: edit.after, limitations: 'A same-paragraph edit after the final precondition check can still race with Office.js. Different paragraphs may change independently.'}); return;
    }
    const current = previewParagraphs(read.paragraphs, plan.edit.find, plan.edit.replacement);
    if (current.before !== plan.edit.before || current.after !== plan.edit.after) fail('stale_preview', 'The target paragraph changed. No edit was sent; make a new preview.');
    if (cloudResult(await downloadParagraphs(account, target), plan.edit) !== 'original_text_observed') fail('cloud_baseline_mismatch', 'The cloud target changed after preview. No edit was sent.');
    await browserIdentity(browser.context, target, profile);
    dispatchFile = files.journal; activePlan = plan;
    const result = await bridge.command('replace', {edit: plan.edit}, () => markDispatch(files.journal, plan));
    writeJSON(files.journal, {operation: plan.id, hash: plan.hash, status: result.status, code: result.code, time: new Date().toISOString()});
    let verification = 'cloud_unverified';
    if (result.status !== 'refused_before_mutation') {
      // Reads may be repeated after a save. The mutation is never repeated, even after a transport failure.
      for (let attempt = 0; attempt < 6; attempt++) {
        verification = cloudResult(await downloadParagraphs(account, target), plan.edit);
        if (verification === 'cloud_text_verified') break;
        await sleep(2000);
      }
    }
    const final = {operation: plan.id, hash: plan.hash, status: verification === 'cloud_text_verified' ? verification : result.status === 'refused_before_mutation' ? result.status : 'uncertain_after_dispatch', sessionStatus: result.status, verification, replayAllowed: false, time: new Date().toISOString()};
    writeJSON(files.journal, final); emit(final);
    if (final.status !== 'cloud_text_verified') process.exitCode = 1;
  } catch (error) {
    const dispatched = dispatchFile && fs.existsSync(dispatchFile);
    emit({status: dispatched ? 'uncertain_after_dispatch' : error.code || 'failed', detail: dispatched ? 'The operation has a dispatch record. Use verify to check cloud content; do not replay the edit.' : safeMessage(error), ...(activePlan ? {operation: activePlan.id} : {}), ...(setupStarted ? {setupMayHaveChangedDocument: true, contentEditSent: false} : {})});
    process.exitCode = 1;
  } finally {
    await cleanup();
    process.removeListener('SIGINT', signal); process.removeListener('SIGTERM', signal);
  }
}
function safeMessage(error) {
  // Playwright errors can contain authenticated URLs. Only return our explicitly bounded application messages.
  return /^[a-z][a-z_]+$/.test(error.code || '') ? error.message : 'The command failed. Check local dependencies, browser availability and private setup; no automatic mutation retry occurred.';
}
