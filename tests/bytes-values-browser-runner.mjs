import {readFileSync,writeFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
const [modulePath,url,reportPath]=process.argv.slice(2);
const engines=await import(pathToFileURL(modulePath).href);
// Reuse the maintained pure value cases, replacing only Node's hex adapter.
// The browser imports emitted JavaScript and uses its own TextEncoder/Decoder.
const source=readFileSync(new URL('./bytes-values-runner.mjs',import.meta.url),'utf8');
const checks=`
const require=(condition,message='browser managed byte assertion failed')=>{if(!condition)throw new Error(message);};
const hex=value=>Array.from(value.toUint8Array(),v=>v.toString(16).padStart(2,'0')).join('');
const unhex=value=>nex.ByteBuffer.copy(Array.from({length:value.length/2},(_,i)=>parseInt(value.slice(i*2,i*2+2),16)));
`+source.slice(source.indexOf('const schema='),source.indexOf('\nfunction observed(')).replace('export function selfTest()','function selfTest()');
const report={ok:false,browsers:[]};
try {
  for(const name of ['chromium','firefox','webkit']) {
    const browser=await engines[name].launch({headless:true});
    try {
      const page=await browser.newPage(),errors=[];
      page.on('pageerror',error=>errors.push(error.message));
      await page.goto(url);
      const cases=await page.evaluate(async checks=>{
        const nex=await import('/nex-runtime.js');
        return new Function('nex',checks+'\nreturn selfTest();')(nex);
      },checks);
      if(cases!==7||errors.length)throw new Error('browser runtime checks failed: '+JSON.stringify(errors));
      report.browsers.push({name,version:browser.version(),managed_value_cases:cases,page_errors:errors});
    } finally {await browser.close();}
  }
  report.ok=true;
} finally {writeFileSync(reportPath,JSON.stringify(report,null,2)+'\n');}
console.log(JSON.stringify(report));
