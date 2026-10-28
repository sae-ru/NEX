import {readFileSync, writeFileSync} from 'node:fs';
import {pathToFileURL} from 'node:url';
const [modulePath, url, reportPath]=process.argv.slice(2);
const engines=await import(pathToFileURL(modulePath).href);
const vectors=[[],[0],[255],[128],[0,255,128,0,195,40],Array.from({length:256},(_,i)=>i),Array.from({length:1025},(_,i)=>(i*31)%256)];
const expected=vectors.map(value=>Buffer.from(value).toString('base64'));
const report={ok:false,browsers:[]};
try {
  for(const name of ['chromium','firefox','webkit']) {
    const browser=await engines[name].launch({headless:true});
    try {
      const page=await browser.newPage(), errors=[];
      page.on('pageerror',error=>errors.push(error.message));
      await page.goto(url);
      const checked=await page.evaluate(async ({vectors,expected})=>{
        const {ByteBuffer,ByteError}=await import('/nex-bytes.js');
        let assertions=0;
        const require=(condition)=>{++assertions;if(!condition)throw new Error('browser byte assertion failed');};
        const equal=(a,b)=>a.length===b.length&&a.every((v,i)=>v===b[i]);
        const values=(value)=>Array.from(value.toUint8Array());
        const error=(code,action)=>{
          try{action();}catch(e){require(e instanceof ByteError&&e.code===code);return;}
          throw new Error('missing expected byte error '+code);
        };
        for(let i=0;i<vectors.length;++i) {
          const input=new Uint8Array(vectors[i]), value=ByteBuffer.copy(input), output=value.toUint8Array();
          require(value.length===BigInt(vectors[i].length));require(value.base64()===expected[i]);
          require(equal(values(ByteBuffer.fromBase64(expected[i])),vectors[i]));
          if(input.length){input[0]^=255;output[0]^=255;require(equal(values(value),vectors[i]));}
        }
        const source=ByteBuffer.fromIntegers([0n,255n,128n,65n]), alias=source, changed=source.set(1n,7n);
        require(equal(values(source),[0,255,128,65]));require(alias.equals(source));
        require(equal(values(changed),[0,7,128,65]));require(equal(values(source.append(42n)),[0,255,128,65,42]));
        const slice=source.slice(1n,3n).slice(1n,2n);
        require(equal(values(slice),[128,65]));require(slice.at(0n)===128n);
        require(equal(values(slice.concat(slice)),[128,65,128,65]));
        require(source.slice(4n,0n).length===0n);require(ByteBuffer.empty().concat(source).equals(source));
        for(const value of [-1n,256n,9223372036854775807n,-9223372036854775808n])
          error('E_RANGE',()=>ByteBuffer.fromIntegers([value]));
        for(const index of [-1n,4n,9223372036854775807n])error('E_BOUNDS',()=>source.at(index));
        error('E_BOUNDS',()=>ByteBuffer.empty().at(0n));error('E_BOUNDS',()=>source.slice(1n,9223372036854775807n));
        error('E_RANGE',()=>source.set(0n,256n));error('E_RANGE',()=>source.append(-1n));
        for(const text of ['Zg','Zg=','Zg===','====','A===','Zm=8','Zg==\n','Zg==\r\n','Zg==\0','Zg== ','AA-_','Zh==','Zm9=','Zg==AAAA','ЯAAA','🧠AA'])
          error('E_BASE64',()=>ByteBuffer.fromBase64(text));
        require(Object.isFrozen(source)&&Object.getOwnPropertyNames(source).length===0);
        require(Object.isFrozen(ByteBuffer.prototype)&&Object.isFrozen(ByteBuffer));
        require(!Reflect.set(ByteBuffer.prototype,'toUint8Array',()=>new Uint8Array(4)));
        require(!Reflect.set(ByteBuffer,'copy',()=>source));
        let rejected=false;try{Reflect.construct(ByteBuffer,[Symbol(),new Uint8Array(4),0,4]);}catch(e){rejected=e instanceof TypeError;}
        require(rejected);return {ok:true,assertions};
      },{vectors,expected});
      if(errors.length||!checked.ok)throw new Error(JSON.stringify(errors));
      report.browsers.push({name,version:browser.version(),...checked,page_errors:errors});
    } finally {await browser.close();}
  }
  report.ok=true;
} finally {writeFileSync(reportPath,JSON.stringify(report,null,2)+'\n');}
console.log(JSON.stringify(report));
