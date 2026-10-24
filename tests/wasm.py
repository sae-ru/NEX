"""Observable scalar Wasm ABI, checked semantics, bounds and artifact integrity."""
import hashlib,json,os,random,shutil,subprocess,unittest
from pathlib import Path
import support as harness
LOW=-(1<<63);HIGH=(1<<63)-1
SOURCE='''module wasm_matrix;
fn identity<T:integer>(x:T)->T{return x;}
fn zero()->i64{return 1/0;}
fn overflow()->i64{return 9223372036854775807+1;}
fn pair(x:i64,y:i64)->i64{return x+y;}
fn recurse(n:i64)->i64{if n==0{return 0;}return recurse(n-1)+1;}
pub fn compute(op:i64,x:i64,y:i64)->i64{
 if op==0{return x+y;}if op==1{return x-y;}if op==2{return x*y;}
 if op==3{return x/y;}if op==4{return x%y;}if op==5{return -x;}
 if op==6{assert(x==y);return 0;}
 if op==7{return pair(zero(),overflow());}
 if op==8{assert(!(false&&(zero()==0)));assert(true||(overflow()==0));return x;}
 if op==9{var i:i64=0;var total:i64=0;while i<y{total=total+x;i=i+1;}return total;}
 if op==10{return identity(x);}return recurse(x);
}
pub client fn invert(x:bool)->bool{return !x;}
pub fn nothing()->unit{assert(true);}
server fn excluded()->str !{io}{print("WASM_SERVER_SECRET_EXCLUDED_060");return "WASM_SERVER_SECRET_EXCLUDED_060";}
'''
def quotient(a,b):
 magnitude=abs(a)//abs(b);return -magnitude if (a<0)!=(b<0) else magnitude

class Wasm(harness.ToolchainCase):
 def setUp(self):
  super().setUp();(self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.21','entry':'main.nex'}))
 def wasm(self,entry='compute',profile='release',**kw):
  doctor=self.cli('doctor');linker=os.environ.get('NEX_WASM_LD',doctor.get('wasm_linker',''))
  if not linker or not Path(linker).is_file():self.skipTest('matching LLVM22.1 wasm-ld is not installed')
  return self.cli('build','--target','wasm','--entry',entry,'--profile',profile,timeout=180,**kw)
 def node(self,body,typescript=False):
  path=self.root/('driver.ts' if typescript else 'driver.mjs');path.write_text(body)
  args=[os.environ.get('NEX_NODE','node')]
  if typescript:args+=['--experimental-strip-types','--no-warnings']
  result=subprocess.run([*args,str(path)],cwd=self.root,capture_output=True,text=True,timeout=60)
  self.assertEqual(result.returncode,0,result.stdout+result.stderr)
  return json.loads(result.stdout)
 def imports(self,build):
  return 'import fs from "node:fs";\nimport {createNexWasm,descriptor} from '+json.dumps(Path(build['wrapper']).as_uri())+';\nconst raw=fs.readFileSync('+json.dumps(build['module'])+');\nconst instance=await createNexWasm(raw);\n'
 def test_discovery_and_invalid_options_do_not_create_graphs(self):
  descriptor=self.cli('describe')['wasm_features'];self.assertEqual(descriptor['abi'],1)
  pack=json.loads((harness.REPO/'llm/language-pack.json').read_text())
  self.assertEqual(descriptor,pack['wasm_features'])
  self.assertEqual(descriptor['limits']['call_depth'],64);self.assertEqual(descriptor['javascript_i64'],'BigInt')
  self.assertIn('BigInt',self.cli('guide','--kind','wasm')['text'])
  for command in [('run',),('test',),('build','--library'),('build','--directory','x'),('build','--toolchain','x')]:
   self.assertEqual(self.cli(*command,'--target','wasm',ok=False)['code'],'E_OPTION')
   self.assertFalse((self.root/'.nex').exists())
 def test_boundary_seeded_and_rejected_values_agree_with_other_backends(self):
  rng=random.Random(20261019);bounds=[LOW,LOW+1,-(1<<32),-2,-1,0,1,2,1<<32,HIGH-1,HIGH]
  pairs=[(a,b) for a in bounds for b in bounds]
  pairs +=[(rng.randint(LOW,HIGH),rng.randint(LOW,HIGH)) for _ in range(35)]
  pairs +=[(rng.randint(-(1<<30),1<<30),rng.randint(-(1<<30),1<<30)) for _ in range(25)]
  cases=[]
  for op in range(5):
   for a,b in pairs:
    code=None
    if op in (3,4) and b==0:value=None;code='E_DIV_ZERO'
    else:
     value=[lambda:a+b,lambda:a-b,lambda:a*b,lambda:quotient(a,b),lambda:a-quotient(a,b)*b][op]()
     if not LOW<=value<=HIGH:code='E_OVERFLOW';value=None
    cases.append({'args':list(map(str,[op,a,b])),'value':str(value) if value is not None else None,'code':code})
  cases +=[{'args':list(map(str,[5,a,0])),'value':str(-a) if a!=LOW else None,'code':'E_OVERFLOW' if a==LOW else None} for a in bounds]
  for args,value in [([8,42,0],42),([9,-3,7],-21),([10,HIGH,0],HIGH),([11,15,0],15),([6,7,7],0)]:
   cases.append({'args':list(map(str,args)),'value':str(value),'code':None})
  cases +=[{'args':['7','0','0'],'value':None,'code':'E_DIV_ZERO'},{'args':['6','1','2'],'value':None,'code':'E_ASSERT'}]
  valid=[c for c in cases if c['code'] is None]
  checks=''.join('assert(compute('+','.join(c['args'])+')=='+c['value']+');' for c in valid)
  self.source(SOURCE+'test fn matrix()->unit{'+checks+'}\nfn main()->unit{}')
  self.cli('test',timeout=180);self.cli('test','--target','web',timeout=180)
  ts=self.root/'typescript';self.cli('emit','--kind','typescript','--entry','compute','--directory',ts)
  (self.root/'package.json').write_text('{"type":"module"}')
  for profile in ('debug','release'):
   with self.subTest(profile=profile):
    build=self.wasm(profile=profile)
    body=self.imports(build)+'import {entry} from "./typescript/program.ts";\nconst cases='+json.dumps(cases)+';\n'
    body+='''let accepted=0,rejected=0;
for(const row of cases){
 const args=row.args.map(BigInt);let native,other,first,second;
 try{native=instance.call(args)}catch(error){first=error;}
 try{other=entry(...args)}catch(error){second=error;}
 if(row.code){
  if(first?.code!==row.code||second?.code!==row.code)throw Error('wrong rejection');
  if(!first.site?.site||first.site.site!==second.site?.[3]||first.line!==second.site?.[1])throw Error('wrong operation mapping');
  rejected++;
 }else{
  if(first||second||String(native)!==row.value||native!==other)throw Error('result disagreement');accepted++;
 }
}
console.log(JSON.stringify({accepted,rejected}));
'''
    result=self.node(body,typescript=True);self.assertEqual(result,{'accepted':len(valid),'rejected':len(cases)-len(valid)})
 def test_native_rejections_match_interpreter_and_wasm(self):
  bad=[('compute(0,9223372036854775807,1)','E_OVERFLOW'),('compute(3,1,0)','E_DIV_ZERO'),
       ('compute(5,-9223372036854775808,0)','E_OVERFLOW'),('compute(7,0,0)','E_DIV_ZERO'),('compute(6,1,2)','E_ASSERT')]
  self.source(SOURCE+''.join('fn bad_'+str(i)+'()->i64{return '+call+';}\n' for i,(call,_) in enumerate(bad)))
  for i,(_,code) in enumerate(bad):
   entry='bad_'+str(i);reference=self.cli('eval','--entry',entry,ok=False)
   self.assertEqual(reference['code'],code)
   native=self.cli('run','--entry',entry,ok=False,timeout=180)
   self.assertEqual(native['native_diagnostics']['diagnostics'][0]['report']['code'],code)
   build=self.wasm(entry)
   result=self.node(self.imports(build)+'''let error;try{instance.call([])}catch(observed){error=observed;}
console.log(JSON.stringify({code:error?.code,site:error?.site?.site}));''')
   self.assertEqual(result,{'code':code,'site':reference['operation_site']})
 def test_budget_depth_validation_and_post_trap_recovery(self):
  self.source(SOURCE);build=self.wasm()
  body=self.imports(build)+'''const Original=WebAssembly.Instance;let creations=0;
WebAssembly.Instance=class extends Original{constructor(...args){super(...args);creations++;}};
const bad=[[[9n,1n,1000n],{budget:10},'E_WASM_BUDGET'],[[11n,1000n,0n],{},'E_WASM_DEPTH'],
 [[0,1n,2n],{},'E_WASM_INPUT'],[[0n,9223372036854775808n,0n],{},'E_WASM_INPUT'],[[0n,1n,2n],{budget:0},'E_WASM_INPUT']];
for(const [args,options,code] of bad){
 let error;try{instance.call(args,options)}catch(observed){error=observed;}
 if(error?.code!==code)throw Error('wrong resource/input error '+error?.code);
 if(instance.call([2n,6n,7n])!==42n)throw Error('trapped instance was reused');
}
for(let i=0;i<100;i++){
 const before=creations;
 try{instance.call([11n,1000n,0n])}catch(error){if(error.code!=='E_WASM_DEPTH')throw error;}
 if(instance.call([2n,6n,7n])!==42n)throw Error('stack state leaked across traps');
 if(creations!==before+1)throw Error('trapped Wasm instance was not replaced');
}
WebAssembly.Instance=Original;
for(const args of [[0n,,2n],new BigInt64Array([0n,1n,2n]),null,[0n,1n]]){
 let code;try{instance.call(args)}catch(error){code=error.code;}
 if(code!=='E_WASM_INPUT')throw Error('coerced or sparse arguments accepted');
}
for(const settings of [null,[],1,{budget:1.5},{budget:NaN},{budget:10000001}]){
 let code;try{instance.call([0n,1n,2n],settings)}catch(error){code=error.code;}
 if(code!=='E_WASM_INPUT')throw Error('invalid call settings accepted');
}
for(const options of [null,[],{budget:0},{budget:Infinity}]){
 let code;try{await createNexWasm(raw,options)}catch(error){code=error.code;}
 if(code!=='E_WASM_INPUT')throw Error('invalid factory options accepted');
}
if(typeof SharedArrayBuffer==='function'){
 let code;try{await createNexWasm(new Uint8Array(new SharedArrayBuffer(raw.length)))}catch(error){code=error.code;}
 if(code!=='E_WASM_MODULE')throw Error('shared module bytes accepted');
}
const mutated=raw.slice();mutated[mutated.length-1]^=1;let rejected;
try{await createNexWasm(mutated)}catch(error){rejected=error.code;}
if(rejected!=='E_WASM_MODULE')throw Error('module integrity not checked');
console.log(JSON.stringify({ok:true,repeated_traps:100}));'''
  self.assertEqual(self.node(body),{'ok':True,'repeated_traps':100})
 def test_bool_and_unit_abi_accept_only_checked_input_types(self):
  self.source(SOURCE);boolean=self.wasm('invert');unit=self.wasm('nothing')
  body=self.imports(boolean)+'const createUnit=(await import('+json.dumps(Path(unit['wrapper']).as_uri())+')).createNexWasm;\n'
  body+='const unit=await createUnit(fs.readFileSync('+json.dumps(unit['module'])+'));\n'
  body+='''if(instance.call([true])!==false||instance.call([false])!==true||unit.call([])!==undefined)throw Error('wrong scalar ABI');
for(const value of [0,1,0n,1n,'true',null]){
 let code;try{instance.call([value])}catch(error){code=error.code;}
 if(code!=='E_WASM_INPUT')throw Error('bool coercion accepted');
}console.log(JSON.stringify({ok:true}));'''
  self.assertTrue(self.node(body)['ok'])
 def test_unsupported_reachable_code_and_profiles_are_explicitly_rejected(self):
  cases=[('fn main()->str{return "x";}','E_WASM_TYPE'),('fn main()->f64{return 1.0;}','E_WASM_TYPE'),
   ('fn main()->i64{let x:list<i64>=[1];return x[0];}','E_WASM_TYPE'),
   ('fn main()->unit !{io}{print(1);}','E_WASM_REALM'),('server fn main()->i64{return 1;}','E_WASM_REALM'),
   ('fn main()->i64{let f:fn(i64)->i64=fn(x:i64)->i64{return x;};return f(1);}','E_WASM_TYPE'),
   ('server extern fn main()->i64 !{ffi}=foreign("sample","x","'+'0'*64+'");','E_WASM_REALM')]
  for source,code in cases:
   with self.subTest(source=source):
    self.source('module unsupported;'+source);self.assertEqual(self.wasm('main',ok=False)['code'],code)
  self.source('module unsupported;fn main()->i64{return 1;}')
  self.assertEqual(self.wasm('main',profile='profile',ok=False)['code'],'E_OPTION')
 def test_literal_percent_quoted_unicode_and_newline_paths(self):
  self.root=self.root/'Wasm output % "quoted", \\ 🧠\nnext';self.root.mkdir()
  self.file=self.root/'main.nex'
  (self.root/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.21','entry':'main.nex'}))
  self.source(SOURCE)
  temporary=self.root/'temporary % "quoted", 🧠';temporary.mkdir()
  env={name:str(temporary) for name in ['TMPDIR','TMP','TEMP','TEMPDIR']}
  for profile in ['debug','release']:
   build=self.wasm(profile=profile,env=env)
   self.assertIn('%',build['module']);self.assertTrue(Path(build['module']).is_file())
   self.assertTrue(self.wasm(profile=profile,env=env)['cached'])
   # Node's ESM loader rejects a literal POSIX backslash in file URLs.
   # Verify the exact generated bytes through an independent physical runtime
   # directory while keeping all actual compiler/cache/export paths literal.
   runtime=Path(self.temp.name)/('independent runtime '+profile);runtime.mkdir()
   for field,name in [('module','module.wasm'),('wrapper','module.mjs')]:
    shutil.copyfile(build[field],runtime/name)
    self.assertEqual(Path(build[field]).read_bytes(),(runtime/name).read_bytes())
   independent={**build,'module':str(runtime/'module.wasm'),'wrapper':str(runtime/'module.mjs')}
   body=self.imports(independent)+"console.log(JSON.stringify({value:String(instance.call([0n,9007199254740993n,1n]))}));"
   driver=runtime/'driver.mjs';driver.write_text(body)
   result=subprocess.run([os.environ.get('NEX_NODE','node'),str(driver)],cwd=runtime,capture_output=True,text=True,timeout=60)
   self.assertEqual(result.returncode,0,result.stdout+result.stderr)
   self.assertEqual(json.loads(result.stdout),{'value':'9007199254740994'})
  copied=self.root/'copied output % 🧠'
  exported=self.cli('build','--target','wasm','--entry','compute','--profile','release','-o',copied,env=env,timeout=180)
  self.assertEqual(Path(exported['module']).read_bytes(),Path(build['module']).read_bytes())
 def test_cache_archived_revision_source_exclusion_and_export(self):
  self.source(SOURCE);first=self.wasm();self.assertFalse(first['cached']);self.assertTrue(self.wasm()['cached'])
  for name in ['module','wrapper','metadata','mlir','llvm']:
   self.assertNotIn(b'WASM_SERVER_SECRET_EXCLUDED_060',Path(first[name]).read_bytes())
  module=Path(first['module']);original=module.read_bytes();module.write_bytes(original+b'x')
  self.assertFalse(self.wasm()['cached']);self.assertEqual(module.read_bytes(),original)
  revision=first['revision'];self.file.write_text(SOURCE.replace('return x*y','return x+y'))
  changed=self.wasm();self.assertNotEqual(changed['build_key'],first['build_key'])
  self.file.unlink();destination=self.root/'copied module'
  historical=self.cli('build','--revision',revision,'--target','wasm','--entry','compute','--profile','release','-o',destination,timeout=180)
  self.assertEqual(Path(historical['module']).read_bytes(),original)
  self.assertEqual({p.name for p in destination.iterdir()},{'module.wasm','module.mjs','module.json','THIRD_PARTY_NOTICES.txt'})
  self.assertEqual(self.cli('build','--revision',revision,'--target','wasm','--entry','compute','-o',destination,ok=False)['code'],'E_EXISTS')

if __name__=='__main__':unittest.main()
