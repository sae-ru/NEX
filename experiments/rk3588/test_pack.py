#!/usr/bin/env python3
"""Pure NEX signed-byte packing checks across native/TypeScript/reference."""
import argparse,hashlib,json,os,subprocess
from pathlib import Path
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--sdk',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
origin=Path(__file__).resolve().parent;api=(origin/'npu-api.nex.in').read_text();pack=api[api.index('fn pack_int8'):api.index('server fn npu_matmul(')]
out=a.output.absolute();out.mkdir(exist_ok=False);project=out/'project';project.mkdir()
(project/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.20','entry':'main.nex'}))
source='''module packing;
@PACK@
fn main()->unit{}
test fn signed_examples()->unit{
 let original:list<i64>=[-128,-1,0,1,127];let value:bytes=unwrap(pack_int8(original));
 assert(value==unwrap(bytes([128,255,0,1,127])));assert(original==[-128,-1,0,1,127]);
 assert(unwrap(pack_int8([]))==unwrap(bytes([])));
 assert(error_code(pack_int8([-129]))=="E_INPUT_RANGE");assert(error_code(pack_int8([128]))=="E_INPUT_RANGE");
}
test fn all_int8_values()->unit{
 var inputs:list<i64>=[];var value:i64= -128;while value<128{inputs=push(inputs,value);value=value+1;}
 let data:bytes=unwrap(pack_int8(inputs));assert(len(data)==256);
 var i:i64=0;while i<256{var decoded:i64=data[i];if decoded>=128{decoded=decoded-256;}assert(decoded==inputs[i]);i=i+1;}
}
'''.replace('@PACK@',pack)
(project/'main.nex').write_text(source);sdk=a.sdk.resolve(strict=True)
results={}
for name,args in [('native',['test']),('typescript',['test','--target','web'])]:
 r=subprocess.run([str(sdk/'bin/nex'),*args,'--json'],cwd=project,env={**os.environ,'NEX_RESOURCE_DIR':str(sdk/'share/nex')},capture_output=True,text=True,timeout=300)
 (out/(name+'.stdout')).write_text(r.stdout);(out/(name+'.stderr')).write_text(r.stderr)
 assert r.returncode==0,(r.stdout,r.stderr)
 data=json.loads(r.stdout);assert data['ok'] and len(data['tests'])==2,data
 assert all(t['ok'] and t['web']==(name=='typescript') and t['native']==(name=='native') for t in data['tests'])
 results[name]=data
result={'schema':'nex.rk3588-pack-equivalence/1','ok':True,'api_sha256':hashlib.sha256(api.encode()).hexdigest(),'source_sha256':hashlib.sha256(source.encode()).hexdigest(),'scope':'Pure pack_int8 function from actual adapter; fixed signed encoding, all256 int8 inverse checks, bounds errors, immutable inputs; standard nex test backend agreement','results':results}
(out/'report.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps(result))
