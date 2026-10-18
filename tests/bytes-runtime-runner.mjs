import {ByteBuffer, ByteError} from '../web/nex-bytes.ts';
import {readFileSync} from 'node:fs';
const require=(condition)=>{if(!condition)throw new Error('byte runtime assertion failed');};
const hex=(value)=>Buffer.from(value.toUint8Array()).toString('hex');
const unhex=(value)=>ByteBuffer.copy(Buffer.from(value,'hex'));
function error(code, action) {
  try {action();} catch(e) {require(e instanceof ByteError&&e.code===code);return;}
  throw new Error('expected byte error '+code);
}
if (process.argv[2]==='--self-test') {
  const empty=ByteBuffer.empty();require(empty.length===0n&&empty.base64()==='');
  error('E_BOUNDS',()=>empty.at(0n));error('E_BOUNDS',()=>empty.set(0n,1n));
  const imported=new Uint8Array([0,255,128,65]), value=ByteBuffer.copy(imported);imported[0]=7;
  const exported=value.toUint8Array();exported[1]=1;require(hex(value)==='00ff8041');
  require(Object.isFrozen(value)&&Object.getOwnPropertyNames(value).length===0);
  require(Object.isFrozen(ByteBuffer.prototype)&&Object.isFrozen(ByteBuffer));
  require(!Reflect.set(ByteBuffer.prototype,'toUint8Array',()=>imported));
  require(!Reflect.set(ByteBuffer,'copy',()=>value));
  let rejected=false;try{Reflect.construct(ByteBuffer,[Symbol(),imported,0,4]);}catch(e){rejected=e instanceof TypeError;}require(rejected);
  const source=unhex('00010203'), alias=source, changed=source.set(1n,255n);
  require(hex(source)==='00010203'&&alias.equals(source)&&hex(changed)==='00ff0203');
  require(hex(source.append(128n))==='0001020380'&&source.length===4n);
  const slice=unhex('0001020304').slice(1n,4n).slice(1n,2n);
  require(hex(slice)==='0203'&&slice.at(0n)===2n&&hex(slice.concat(slice))==='02030203');
  require(hex(ByteBuffer.fromIntegers([0n,127n,128n,255n]))==='007f80ff');
  for(const n of [-1n,256n])error('E_RANGE',()=>ByteBuffer.fromIntegers([n]));
  error('E_RANGE',()=>source.append(-1n));error('E_RANGE',()=>source.set(0n,256n));
  for(const index of [-1n,4n,9223372036854775807n])error('E_BOUNDS',()=>source.at(index));
  for(const [start,count] of [[-1n,0n],[0n,-1n],[5n,0n],[3n,2n],[1n,9223372036854775807n]])error('E_BOUNDS',()=>source.slice(start,count));
  require(source.slice(4n,0n).length===0n);
  for(const text of ['Zg==\n','Zg==\r\n','Zg==\0','Zh==','Zm9='])error('E_BASE64',()=>ByteBuffer.fromBase64(text));
  console.log('8 immutable byte runtime cases passed');
} else {
  const input=readFileSync(0,'utf8');
  for(const line of input.split('\n')) {
    if(!line)continue;require(line.length>=2&&line[1]===' ');
    try {
      if(line[0]==='E')console.log(unhex(line.slice(2)).base64());
      else if(line[0]==='D')console.log(hex(ByteBuffer.fromBase64(line.slice(2))));
      else throw new Error('unknown byte request');
    } catch(e) {if(!(e instanceof ByteError))throw e;console.log('ERR:'+e.code);}
  }
}
