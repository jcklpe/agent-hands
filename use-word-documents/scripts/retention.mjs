import fs from 'node:fs';
import path from 'node:path';
import {readJSON, hash, fail, noSymlinks, lockAccount} from './core.mjs';

export function retentionPlan(account, now = Date.now()) {
  const files = [];
  for (const relative of ['plans', 'powerpoint/plans']) {
    const root = path.join(account.dir, relative); noSymlinks(root);
    if (!fs.existsSync(root)) continue;
    for (const name of fs.readdirSync(root).sort()) {
      if (!/^[a-f0-9]{8}(-[a-f0-9]{4}){3}-[a-f0-9]{12}\.json$/.test(name)) continue;
      const file = path.join(root, name), journal = file.replace(/\.json$/, '.journal.json');
      noSymlinks(file); noSymlinks(journal);
      const plan = readJSON(file), {hash:digest, ...body} = plan;
      if (digest !== hash(body) || name !== plan.id + '.json') fail('unsafe_retention_record', 'A stored plan does not match its operation or digest; inspect it before cleanup.');
      const created = Date.parse(plan.created);
      if (!Number.isFinite(created) || created > now) continue;
      let reason;
      if (!fs.existsSync(journal)) {
        if (now - created >= 7*86400_000) reason = 'unused_preview_7_days';
      } else {
        const receipt = readJSON(journal), completed = Date.parse(receipt.time);
        if (receipt.operation !== plan.id || receipt.hash !== digest) fail('unsafe_retention_record', 'Stored plan and receipt identities differ; inspect before cleanup.');
        if (receipt.status === 'cloud_text_verified' && Number.isFinite(completed) && completed <= now && now - completed >= 30*86400_000) reason = 'verified_plan_content_30_days';
      }
      if (reason) files.push({file: path.relative(account.dir,file), operation:plan.id, digest, reason});
    }
  }
  return {status:'retention_preview', files, hash:hash(files), receiptsRetained:true, unresolvedWritesRetained:true};
}
export function retirePlanContent(account, expectedHash) {
  const release = lockAccount(account);
  try {
    const plan = retentionPlan(account);
    if (!expectedHash || expectedHash !== plan.hash) fail('retention_preview_changed', 'Cleanup candidates changed; inspect a new preview before execution.');
    let removed = 0;
    try { for (const entry of plan.files) { fs.unlinkSync(path.join(account.dir,entry.file)); removed++; } }
    catch { fail('retention_partial', 'Some plan content may have been removed; receipts remain. Inspect a new preview before another cleanup.'); }
    return {status:'plan_content_retired', removed, receiptsRetained:true, unresolvedWritesRetained:true};
  } finally { release(); }
}
