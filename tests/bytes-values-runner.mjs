import * as nex from '../web/nex-runtime.ts';
import {readFileSync} from 'node:fs';
const require=(condition,message='managed byte runtime assertion failed')=>{if(!condition)throw new Error(message);};
const hex=value=>Buffer.from(value.toUint8Array()).toString('hex');
const unhex=value=>nex.ByteBuffer.copy(Buffer.from(value,'hex'));
const schema={schema:'nex.wire/2',root:'bytes',records:{},enums:{}};
const site=['bytes-test.nex',37,9,'byte-operation'];
function error(code,action) {
  try {action();} catch(e) {require(e instanceof nex.NexError&&e.code===code&&e.site===site);return;}
  throw new Error('expected '+code);
}
export function selfTest() {
  let cases=0;
  const run=action=>{action();++cases;};
  run(()=>{
    const value=nex.unwrap(nex.bytesFromIntegers([0n,127n,128n,255n]));require(hex(value)==='007f80ff');
    for(const item of [-1n,256n])require(nex.errorCode(nex.bytesFromIntegers([item]))==='E_RANGE');
    require(nex.length(nex.ByteBuffer.empty())===0n&&nex.representation(nex.ByteBuffer.empty())==='""');
  });
  run(()=>{
    const value=unhex('00010203ff'),alias=value,sliced=nex.bytesSlice(value,1n,3n),changed=nex.bytesSet(value,1n,255n);
    require(nex.equal(alias,unhex('00010203ff'))&&hex(changed)==='00ff0203ff'&&hex(sliced)==='010203');
    require(nex.equal(nex.list([sliced,nex.ok(sliced)]),nex.list([unhex('010203'),nex.ok(unhex('010203'))])));
    require(!nex.equal(sliced,unhex('010204'))&&!nex.equal(sliced,'AQID')&&!nex.equal(sliced,nex.list([1n,2n,3n])));
    require(hex(nex.bytesConcat(sliced,sliced))==='010203010203'&&hex(nex.bytesPush(sliced,255n))==='010203ff');
  });
  run(()=>{
    for(const text of ['', 'A\0B', 'Я🧠', '\ufefftext', 'e\u0301'])require(nex.unwrap(nex.decodeUTF8(nex.utf8Bytes(text)))===text);
    for(const bad of ['80','c080','c328','eda080','f4908080','f09f92','ff'])require(nex.errorCode(nex.decodeUTF8(unhex(bad)))==='E_UTF8');
    error('E_UTF8',()=>nex.utf8Bytes('\ud800',site));
  });
  run(()=>{
    require(hex(nex.unwrap(nex.decodeBase64('AP+AQQ==')))==='00ff8041');
    for(const bad of ['Zh==','AA-_','AA==\n','A==='])require(nex.errorCode(nex.decodeBase64(bad))==='E_BASE64');
    require(nex.representation(unhex('00ff8041'))==='"AP+AQQ=="'&&nex.str(unhex('00ff8041'))==='"AP+AQQ=="');
  });
  run(()=>{
    const value=unhex('00ff8041'),wire=nex.encodeJSON(value);require(wire==='"AP+AQQ=="'&&nex.equal(value,nex.unwrap(nex.decodeJSON(wire,schema))));
    for(const bad of ['"Zh=="','"AA== "','[]','1','null','"AA-_"'])require(nex.errorCode(nex.decodeJSON(bad,schema))==='E_JSON');
    for(const version of ['nex.wire/1','nex.wire/2']) {
      const old={schema:version,root:{record:'bytes'},records:{bytes:[{name:'value',type:'i64'}]},enums:{}};
      require(nex.unwrap(nex.decodeJSON('{"value":"7"}',old)).value===7n);
    }
    const nominal=nex.record('Buffer',[['data',value]]),compound={schema:'nex.wire/2',root:{record:'Buffer'},records:{Buffer:[{name:'data',type:'bytes'}]},enums:{}};
    require(nex.equal(nominal,nex.unwrap(nex.decodeJSON(nex.encodeJSON(nominal),compound))));
  });
  run(()=>{
    const maximum=nex.ByteBuffer.copy(new Uint8Array(786429).fill(255)),wire=nex.encodeJSON(maximum);
    require(wire.length===1048574&&nex.length(nex.unwrap(nex.decodeJSON(wire,schema)))===786429n);
    error('E_JSON',()=>nex.encodeJSON(nex.bytesPush(maximum,255n),site));
  });
  run(()=>{
    const value=unhex('00');
    error('E_BOUNDS',()=>nex.bytesSet(value,-1n,256n,site));error('E_BOUNDS',()=>nex.bytesSet(value,1n,256n,site));
    error('E_RANGE',()=>nex.bytesSet(value,0n,256n,site));error('E_RANGE',()=>nex.bytesPush(value,-1n,site));
    error('E_BOUNDS',()=>nex.bytesIndex(value,9223372036854775807n,site));
    error('E_BOUNDS',()=>nex.bytesSlice(value,1n,9223372036854775807n,site));require(nex.length(value)===1n);
  });
  return cases;
}
function observed(value) {
  const wire=nex.encodeJSON(value),decoded=nex.decodeJSON(wire,schema),utf8=nex.decodeUTF8(value);
  require(nex.isOk(decoded));
  return {ok:true,hex:hex(value),length:String(nex.length(value)),display:nex.representation(value),wire,wire_hex:hex(nex.unwrap(decoded)),utf8_ok:nex.isOk(utf8),utf8:nex.isOk(utf8)?nex.unwrap(utf8):nex.errorCode(utf8)};
}
function command(request) {
  try {
    const [op,a,b,c]=request;
    if(op==='decode'){const result=nex.decodeJSON(a,schema);return nex.isOk(result)?observed(nex.unwrap(result)):{ok:false,code:nex.errorCode(result)};}
    if(op==='construct'){const result=nex.bytesFromIntegers(a.map(BigInt));return nex.isOk(result)?observed(nex.unwrap(result)):{ok:false,code:nex.errorCode(result)};}
    const value=unhex(a);
    if(op==='set')return observed(nex.bytesSet(value,BigInt(b),BigInt(c),site));
    if(op==='push')return observed(nex.bytesPush(value,BigInt(b),site));
    if(op==='slice')return observed(nex.bytesSlice(value,BigInt(b),BigInt(c),site));
    if(op==='concat')return observed(nex.bytesConcat(value,unhex(b),site));
    if(op==='at')return {ok:true,integer:String(nex.bytesIndex(value,BigInt(b),site))};
    return observed(value);
  } catch(e) {if(!(e instanceof nex.NexError))throw e;return {ok:false,code:e.code};}
}
if(process.argv[2]==='--self-test')console.log(selfTest()+' managed TypeScript byte value cases passed');
else for(const line of readFileSync(0,'utf8').split('\n'))if(line)console.log(JSON.stringify(command(JSON.parse(line))));
