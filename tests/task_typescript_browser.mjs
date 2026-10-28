import {pathToFileURL} from 'node:url';
const {chromium,firefox,webkit}=await import(pathToFileURL(process.argv[2]).href);
const url=process.argv[3],records=[];
for(const [name,engine]of Object.entries({chromium,firefox,webkit})){
 const browser=await engine.launch({headless:true});
 try{
  const page=await browser.newPage();const errors=[];page.on('pageerror',error=>errors.push(String(error)));
  await page.goto(url,{waitUntil:'networkidle'});
  await page.getByRole('button',{name:'Start'}).click();
  await page.waitForFunction(()=>globalThis.__nexTaskBrowserState?.started&&globalThis.__nexTaskBrowserState.polls>0&&globalThis.__nexTaskBrowserState.ticks>0&&globalThis.__nexTaskBrowserState.frames>0,{},{timeout:10000});
  await page.getByRole('button',{name:'Stop'}).click();
  await page.waitForFunction(()=>globalThis.__nexTaskBrowserState?.done,{},{timeout:10000});
  const state=await page.evaluate(()=>globalThis.__nexTaskBrowserState);
  if(state.code!=='E_CANCELLED'||state.stopClicks!==1||!state.statistics?.completed||state.statistics.activeCalls!==0||state.statistics.retainedFrames!==0||errors.length)throw new Error(JSON.stringify({name,state,errors}));
  records.push({engine:name,version:browser.version(),ok:true,...state});
 }finally{await browser.close();}
}
process.stdout.write(JSON.stringify({ok:true,production_browser_engines:records.length,scope:'one checked pure-loop program through private emitted generator runtime; real timers, animation and button cancellation; not NEX UI adapter integration',records})+'\n');
