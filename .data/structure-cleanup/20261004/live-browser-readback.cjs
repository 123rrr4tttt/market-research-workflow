const { chromium } = require('/Users/wangyiliang/market-research-workflow/main/frontend-modern/node_modules/@playwright/test');
const fs=require('fs');
const E='/Users/wangyiliang/market-research-workflow/.data/structure-cleanup/20261004';
(async()=>{
 const browser=await chromium.launch({headless:true});
 const context=await browser.newContext();
 const page=await context.newPage();
 const errors=[]; let bootstrap=false,status=false,ws=false;
 page.on('pageerror',e=>errors.push(e.message));
 page.on('response',r=>{if(r.url().includes('8172/api/auth/bootstrap')&&r.status()===200)bootstrap=true;if(r.url().includes('8172/api/codex/status')&&r.status()===200)status=true;});
 page.on('websocket',()=>{ws=true;});
 try{
  await page.goto('http://localhost:5173/#/workbench/agent');
  await page.getByTestId('codex-agent-frame').waitFor({timeout:45000});
  await page.frameLocator('[data-testid="codex-agent-frame"]').locator('#root').waitFor({state:'attached',timeout:45000});
  const response=await context.request.get('http://127.0.0.1:8172/api/auth/bootstrap');
  const auth=await response.json();
  const token=auth.data?.accessToken||auth.accessToken;
  if(!token)throw new Error('bootstrap token unavailable');
  const headers={Authorization:'Bearer '+token};
  const runtime=await context.request.get('http://127.0.0.1:8172/api/codex/status',{headers});
  const observations=[];
  for(const [thread,turn,marker] of [
    ['01a1060e-968e-7502-bfbb-cbb615369e3b','01a1060e-a9d3-7f53-b863-aa1625be17e0','MRW_NATIVE_CHAIN_OK'],
    ['01a1066b-3c98-7d50-b9fd-1c00095b8a5b','01a1066b-3ec4-74e3-b824-4aab4a8cf6d8','MRW_STRUCTURE_NATIVE_OK']
  ]){
    const r=await context.request.get(`http://127.0.0.1:8172/api/threads/${thread}/turns/${turn}/items`,{headers});
    const text=await r.text();
    observations.push({thread,turn,http:r.status(),marker_readback:text.includes(marker)});
  }
  await page.waitForTimeout(2000);
  const result={status:'passed',mode:'local-host-oauth-direct',iframe_src:await page.getByTestId('codex-agent-frame').getAttribute('src'),iframe_mounted:true,bootstrap_http:response.status(),runtime_status_http:runtime.status(),browser_bootstrap_observed:bootstrap,browser_runtime_status_observed:status,websocket_observed:ws,page_errors:errors,threads:observations,new_provider_turns:0};
  if(response.status()!==200||runtime.status()!==200||!bootstrap||!status||!ws||errors.length||observations.some(x=>x.http!==200||!x.marker_readback))throw new Error(JSON.stringify(result));
  fs.writeFileSync(E+'/live-browser-readback.json',JSON.stringify(result,null,2)+'\n');
  console.log(JSON.stringify(result));
 }finally{await browser.close();}
})().catch(e=>{console.error(e.message);process.exit(1)});
