const { chromium } = require('/Users/wangyiliang/market-research-workflow/main/frontend-modern/node_modules/@playwright/test');
const fs = require('fs');
const root = '/Users/wangyiliang/market-research-workflow/.data/readiness-repair/20261004-daily-chain';
(async()=>{
 const context = await chromium.launchPersistentContext(root+'/user-browser-profile',{headless:false,viewport:{width:1280,height:900}});
 const page = context.pages()[0] || await context.newPage();
 let exchange = false, codexStatus = false;
 page.on('response', r=>{ if(r.url().includes('/api/v1/codex-auth/webui/bootstrap') && r.request().method()==='POST' && r.status()===200) exchange=true; if(r.url().includes('/codex/api/codex/status') && r.status()===200)codexStatus=true; });
 await page.goto('http://localhost:5173/#/workbench/agent');
 console.log('USER_BROWSER_READY: authorize in the visible frontend window');
 let last='';
 for(let i=0;i<3600;i++){
  await new Promise(r=>setTimeout(r,2000));
  try {
   const res=await context.request.get('http://localhost:5173/api/v1/codex-auth/status'); const body=await res.json(); const auth=body.data?.authenticated===true;
   if(auth && !page.url().startsWith('http://localhost:5173')) await page.goto('http://localhost:5173/#/workbench/agent');
   const iframe=await page.locator('[data-testid="codex-agent-frame"]').count();
   const state={authenticated:auth,iframe_mounted:iframe>0,exchange_http_200:exchange,codex_status_http_200:codexStatus};
   fs.writeFileSync(root+'/user-browser-readback.json',JSON.stringify(state,null,2)+'\n');
   const v=JSON.stringify(state);if(v!==last){console.log(v);last=v;}
   if(auth && iframe && exchange && codexStatus){console.log('REAL_USER_BROWSER_CHAIN_PASSED');break;}
  }catch(e){console.log('browser observation error: '+e.name);}
 }
 // Retain the real user window and its authenticated context for the user.
 await new Promise(()=>{});
})().catch(e=>{console.log('browser launch error: '+e.name);process.exit(1)});
