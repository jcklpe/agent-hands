import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {initialize} from '../scripts/browser.mjs';
import {makePlan, hash, writeJSON, lockAccount} from '../scripts/core.mjs';
import {retentionPlan, retirePlanContent} from '../scripts/retention.mjs';

test('retention preserves uncertain writes and receipts, refuses stale previews and active owners', async () => {
  const root=fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(),'office-retention-')));
  try {
    const account=await initialize('demo',43189,root);
    const create=(days,status)=>{
      let plan=makePlan({alias:'demo'},{find:'old',replacement:'new',before:'old',after:'new'});
      delete plan.hash;plan.created=new Date(Date.now()-days*86400_000).toISOString();plan.hash=hash(plan);
      const file=path.join(account.dir,'plans',plan.id+'.json');writeJSON(file,plan,true);
      if(status)writeJSON(file.replace(/\.json$/,'.journal.json'),{operation:plan.id,hash:plan.hash,status,time:plan.created},true);
      return file;
    };
    const unused=create(8), verified=create(31,'cloud_text_verified'), uncertain=create(90,'uncertain_after_dispatch'), recent=create(1), awaiting=create(90,'save_returned');
    const plan=retentionPlan(account);
    assert.equal(plan.files.length,2);assert.ok(fs.existsSync(unused));
    assert.throws(()=>retirePlanContent(account,'wrong'),{code:'retention_preview_changed'});
    const release=lockAccount(account);assert.throws(()=>retirePlanContent(account,plan.hash),{code:'profile_busy'});release();
    assert.equal(retirePlanContent(account,plan.hash).removed,2);
    assert.ok(!fs.existsSync(unused));assert.ok(!fs.existsSync(verified));
    assert.ok(fs.existsSync(verified.replace(/\.json$/,'.journal.json')));
    for(const file of [uncertain,recent,awaiting])assert.ok(fs.existsSync(file));
    assert.equal(retentionPlan(account).files.length,0);
  } finally {fs.rmSync(root,{recursive:true,force:true});}
});
