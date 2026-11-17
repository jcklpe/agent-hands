import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {execFileSync} from 'node:child_process';
import {ROOT,readJSON,fail} from '../../use-word-documents/scripts/core.mjs';

const label=process.argv[2];
if(process.argv.length!==3||!/^[-a-z0-9]{1,40}$/.test(label||''))fail('invalid_label','Choose a simple private readback label.');
const state=path.join(path.dirname(fileURLToPath(import.meta.url)),'state'),test=readJSON(path.join(state,'test.json'));
if(!/^Agent Hands PowerPoint coauthoring test \d{4}-\d{2}-\d{2}\.pptx$/.test(test.name))fail('invalid_target','Only the registered disposable presentation is supported.');
const destination=path.join(state,`${label}.pptx`);
if(fs.existsSync(destination))fail('already_exists','Do not overwrite a saved observation.');
execFileSync('bash',[path.join(ROOT,'use-microsoft-files/scripts/files'),'download',test.alias,test.item,'--drive',test.drive,'--out',destination],{timeout:120000,stdio:'pipe'});
fs.chmodSync(destination,0o600);
console.log(JSON.stringify({status:'downloaded',label,bytes:fs.statSync(destination).size}));
