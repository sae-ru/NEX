import { chromium, firefox, webkit } from 'playwright';
import assert from 'node:assert/strict';
import { readFileSync, writeFileSync } from 'node:fs';
const config = JSON.parse(readFileSync(process.argv[2], 'utf8'));
const results = [];
for (const [name, engine] of Object.entries({chromium, firefox, webkit})) {
  const browser = await engine.launch({headless:true});
  // This ephemeral certificate is scoped to the test context. Mobile checks
  // install the test CA in their owned simulator/debug host instead.
  const context = await browser.newContext({ignoreHTTPSErrors:true});
  const page = await context.newPage();
  const calls = [];
  page.on('response', response => {
    if (response.url().startsWith(config.api + '/api/')) calls.push({status:response.status(),origin:response.url().startsWith(config.api+'/api/')});
  });
  const rows = () => page.getByRole('list',{name:'Tasks'}).getByRole('listitem');
  async function until(predicate, message) {
    for (let i=0;i<100;i++) { if(await predicate()) return; await page.waitForTimeout(100); }
    throw new Error(message + ': ' + await page.getByRole('status').innerText());
  }
  async function login(token) {
    await page.getByLabel('Bearer token').fill(token);
    await page.getByRole('button',{name:'Sign in',exact:true}).click();
    await until(async()=>await page.getByRole('status').innerText()==='Saved data loaded.','API sign in failed');
  }
  try {
    await page.goto(config.client);
    assert.equal(await page.locator('meta[name="nex-api-origin"]').getAttribute('content'),config.api);
    if(config.phase==='restart') {
      await login(config.tokens[name].alice);
      assert.equal(await rows().count(),1);
      assert.match(await rows().first().innerText(),new RegExp('persist-'+name));
      results.push({engine:name,phase:config.phase,checks:['persistent state after native server restart']});
      continue;
    }
    await page.getByLabel('Bearer token').fill('invalid-runtime-credential');
    await page.getByRole('button',{name:'Sign in',exact:true}).click();
    await until(async()=>(await page.getByRole('status').innerText()).includes('Authentication failed'),'CORS hid401');
    await login(config.tokens[name].alice);assert.equal(await rows().count(),0);
    const input=page.getByLabel('New or replacement task text');
    await input.fill('Cross origin Я🧠 '+name);
    await page.getByRole('button',{name:'Add task',exact:true}).click();
    await until(async()=>await rows().count()===1,'POST failed');
    assert.match(await rows().first().innerText(),/Cross origin Я🧠/);
    await rows().first().getByRole('button',{name:'Mark complete',exact:true}).click();
    await until(async()=>await rows().first().getByRole('button',{name:'Mark active',exact:true}).count()===1,'PUT failed');
    await page.getByRole('link',{name:'Active tasks',exact:true}).click();assert.equal(await rows().count(),0);
    await page.goBack();assert.equal(await rows().count(),1);
    await page.getByRole('button',{name:'Sign out',exact:true}).click();
    await login(config.tokens[name].bob);assert.equal(await rows().count(),0);
    await page.getByRole('button',{name:'Sign out',exact:true}).click();
    await login(config.tokens[name].alice);assert.equal(await rows().count(),1);
    await rows().first().getByRole('button',{name:'Delete',exact:true}).click();
    await until(async()=>await rows().count()===0,'DELETE failed');
    await input.fill('persist-'+name);await page.getByRole('button',{name:'Add task',exact:true}).click();
    await until(async()=>await rows().count()===1,'Persistent POST failed');
    await page.reload();assert.equal(await page.getByLabel('Bearer token').inputValue(),'');
    await login(config.tokens[name].alice);assert.equal(await rows().count(),1);
    assert(calls.some(call=>call.status===401));assert(calls.some(call=>call.status===201));
    results.push({engine:name,phase:config.phase,checks:['explicit HTTPS destination','readable401','Unicode CRUD','principal isolation','route navigation','reload requires runtime credentials'],requests:calls});
  } finally {await context.close();await browser.close();}
}
writeFileSync(config.result,JSON.stringify({ok:true,results},null,2)+'\n');
console.log(JSON.stringify({ok:true,browsers:results.length,phase:config.phase}));
