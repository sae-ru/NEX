import assert from 'node:assert/strict';
import fs from 'node:fs';
import {pathToFileURL} from 'node:url';
const [url,packageFile,output]=process.argv.slice(2);
const engines=await import(pathToFileURL(packageFile).href);
const results=[];
function save(){fs.writeFileSync(output,JSON.stringify({ok:results.length===3&&results.every(row=>row.ok),engines:results},null,2));}
for(const name of ['chromium','firefox','webkit']){
 const browser=await engines[name].launch({headless:true});
 const row={name,version:browser.version(),ok:false};results.push(row);save();
 try{
  const page=await browser.newPage({viewport:{width:1280,height:800}});
  await page.goto(url,{waitUntil:'networkidle'});
  const left=page.getByLabel('First integer'),right=page.getByLabel('Second integer');
  const multiply=page.getByRole('button',{name:'Multiply'});
  await page.waitForFunction(()=>!document.querySelector('#multiply').disabled);
  async function compute(a,b,expected,keyboard=false){
   await left.fill(a);await right.fill(b);
   if(keyboard)await right.press('Enter');else await multiply.click();
   await page.waitForFunction(text=>document.querySelector('#answer').textContent===text,expected);
  }
  await compute('6','7','42',true);
  await compute('9007199254740993','1','9007199254740993');
  await compute('-9223372036854775808','1','-9223372036854775808');
  await compute('9223372036854775807','2','E_OVERFLOW: i64 arithmetic overflow');
  await compute('1.5','2','Use whole decimal integers.');
  await compute('6','7','42',true);
  await page.setViewportSize({width:390,height:844});
  assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true);
  await left.focus();await page.keyboard.press('Tab');assert.equal(await right.evaluate(element=>element===document.activeElement),true);
  await page.keyboard.press('Tab');assert.equal(await multiply.evaluate(element=>element===document.activeElement),true);
  await page.screenshot({path:output+'.'+name+'.png',fullPage:true});
  row.ok=true;row.checks=['exact_i64','minimum_i64','overflow','invalid_integer','post_error_recovery','keyboard_submit','focus_order','narrow_viewport'];save();
 }catch(error){row.error=String(error);save();throw error;}
 finally{await browser.close();}
}
save();
