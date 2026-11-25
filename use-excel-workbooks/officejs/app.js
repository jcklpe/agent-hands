import {createLinksAdapter} from './links.mjs';
import {createLayoutAdapter} from './layout.mjs';
import {createReferencesAdapter} from './references.mjs';
import {createCommentsAdapter} from './comments.mjs';
import {createTextRunAdapter} from './text-runs.mjs';
(async()=>{
 const status=document.getElementById('status'), token=window.agentHandsRunToken;
 const request=async(route,body)=>{const response=await fetch(route,{method:body?'POST':'GET',headers:{'X-Agent-Hands':token,...(body?{'Content-Type':'application/json'}:{})},body:body?JSON.stringify(body):undefined});if(!response.ok)throw Error('Bridge unavailable');return response.json();};
 const cfg=await request('config');
 const properties=()=>new Promise((resolve,reject)=>Office.context.document.getFilePropertiesAsync(r=>r.status===Office.AsyncResultStatus.Succeeded?resolve(r.value):reject(Error('identity_unavailable'))));
 const guard=async()=>{
  const p=await properties(),url=new URL(p.url),guid=(url.searchParams.get('sourcedoc')||'').replace(/[{}]/g,'').toLowerCase();
  if(url.origin!==cfg.target.origin || !(cfg.target.guid && url.pathname.endsWith('/Doc.aspx') && guid===cfg.target.guid || decodeURIComponent(url.pathname)===cfg.target.canonicalPath))throw Object.assign(Error('target_mismatch'),{code:'target_mismatch'});
  return p.url;
 };
 await Office.onReady();
 if(Office.context.host!=='Excel'||Office.context.platform!=='OfficeOnline')throw Error('unsupported_host');
 const adapter=createTextRunAdapter(Excel,Office,guard);
 const commentAdapter=createCommentsAdapter(Excel,Office,guard);
 const linkAdapter=createLinksAdapter(Excel,Office,guard);
 const layoutAdapter=createLayoutAdapter(Excel,Office,guard);
 const referencesAdapter=createReferencesAdapter(Excel,Office,guard);
 await request('report',{id:'ready',host:Office.context.host,platform:Office.context.platform,url:await guard(),automaticStartup:Office.context.document.settings.get('Office.AutoShowTaskpaneWithDocument')===true});
 status.textContent='Connected to the owned Excel session.';
 while(true){
  const job=await request('next');
  if(job){
   let result;
   if(job.action==='read')result=await adapter.read(job.request);
   else if(job.action==='write')result=await adapter.write(job.request);
   else if(['comments-read','comments-add'].includes(job.action))result=await commentAdapter(job.action,job.request);
   else if(['links-read','links-add'].includes(job.action))result=await linkAdapter(job.action,job.request);
   else if(['layout-read','layout-apply'].includes(job.action))result=await layoutAdapter(job.action,job.request);
   else if(['references-read','references-apply'].includes(job.action))result=await referencesAdapter(job.action,job.request);
   else result={status:'refused_before_mutation',code:'unsupported_operation'};
   await request('report',{id:job.id,...result});
  }
  await new Promise(resolve=>setTimeout(resolve,500));
 }
})().catch(()=>{document.getElementById('status').textContent='Excel bridge unavailable.';});
