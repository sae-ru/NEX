"""Compose explicit028 source contracts with detached checked projections."""
from pathlib import Path
import argparse,copy,hashlib,json,os,platform,re,tempfile,time
from host_fixture import run_native,exit_code,probe_dll_inputs

parser=argparse.ArgumentParser();parser.add_argument('probe',type=Path);parser.add_argument('--native-host',type=Path,required=True);parser.add_argument('--compiler',required=True);parser.add_argument('--output',type=Path);a=parser.parse_args()
W=Path(__file__).resolve().parents[1];probe=a.probe.resolve();out=a.output.resolve() if a.output else Path(tempfile.mkdtemp(prefix='nex-contract-projection028-'));out.mkdir(parents=True,exist_ok=a.output is None)
env={**os.environ,'NEX_RESOURCE_DIR':str(W),'PYTHONDONTWRITEBYTECODE':'1'};node=env.get('NEX_NODE','node');started=time.monotonic()
report={'schema':'nex.source-contract-projection-tests/1','ok':False,'language':'0.28','cases':[],'commands':[]}
def save():
 report['seconds']=round(time.monotonic()-started,3);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
def run(label,command,allowed=(0,)):
 r=run_native(list(map(str,command)),env=env,text=True,capture_output=True,timeout=180)
 (out/(label+'.stdout')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr)
 report['commands'].append({'label':label,'exit':r.returncode});save()
 assert r.returncode in allowed,(label,r.returncode,r.stdout[-2000:],r.stderr[-3500:])
 return r
cases=[
 ('loop','''fn advance(x:i64)->i64 requires(x>=0 && x<=8) ensures(value=>value==x){
 var i:i64=0;
 while i<x invariant(i>=0 && i<=x) decreases(x-i){i=i+1;}
 return i;
 }
 fn main()->i64{assert(advance(3)==3);return 42;}''','advance',['x>=0 && x<=8'],['value==x'],1,None,''),
 ('pre','''fn advance(x:i64)->i64 requires(x>50) ensures(value=>value==x){return x;}
 fn main()->i64{return advance(42);}''','advance',['true'],['true'],0,'E_ASSERT',''),
 ('post','''fn advance(x:i64)->i64 requires(x>=0) ensures(value=>value==x+1){return x;}
 fn main()->i64{return advance(42);}''','advance',['true'],['true'],0,'E_ASSERT',''),
 ('generic','''fn identity<T>(item:T)->T requires(item==item) ensures(value=>value==item){return item;}
 fn main()->i64{assert(identity(["owned","🙂"])==["owned","🙂"]);assert(identity(42)==42);return 42;}''','identity',['item==item'],['value==item'],0,None,''),
 ('finally','''fn observe(text:str)->unit !{io} requires(len(text)>0) ensures(len(text)>0){try{print(text);}finally{print("finally");}}
 fn main()->i64 !{io}{observe("λ");return 42;}''','observe',['len(text)>0'],['len(text)>0'],0,None,'λ\nfinally\n'),
 ('escaping','''fn fail()->unit !{throw} requires(true) ensures(false){throw(42);}
 fn main()->i64 !{throw}{try{fail();return 0;}catch(error:i64){return error;}}''','fail',['true'],['false'],0,None,''),
 ('loop-shadow','''fn advance(x:i64)->i64 requires(x>=0 && x<=8) ensures(value=>value==x){
 var i:i64=0;
 while i<x invariant(i>=0 && i<=x) decreases(x-i){i=i+1;let i:str="shadow";assert(i=="shadow");}
 return i;
 }
 fn main()->i64{assert(advance(3)==3);return 42;}''','advance',['x>=0 && x<=8'],['value==x'],1,None,''),
]
runner="""import * as program from './program.ts';import * as nex from './nex-runtime.ts';const logs=[];console.log=x=>logs.push(String(x));let result;try{result={kind:'return',value:String(program.main())};}catch(error){if(!(error instanceof nex.NexError))throw error;result={kind:'trap',code:error.code};}process.stdout.write(JSON.stringify({...result,output:logs.join('\\n')+(logs.length?'\\n':'')})+'\\n');"""
save();host=out/'host.ll';run('host',[a.compiler,'-x','c','-S','-emit-llvm',os.devnull,'-o',host]);text=host.read_text();triple=re.search(r'target triple = "(.*?)"',text)[1];layout=re.search(r'target datalayout = "(.*?)"',text)[1];programs=[]
for name,body,symbol,pre,post,loop_count,error,stdout in cases:
 d=out/name;d.mkdir();source=d/'main.nex';original='module composition;\n'+body;source.write_text(original);original=source.read_bytes().decode('utf-8')
 contract=json.loads(run(name+'-template',[probe,'contract-template',source,'composition::'+symbol]).stdout)
 assert contract['language']=='0.28';rule=contract['functions'][0];assert len(rule['loops'])==loop_count
 rule['requires']=pre;rule['ensures']=post;rule['returns']='' if symbol in ['observe','fail'] else 'value'
 for loop in rule['loops']:loop.update(invariants=['i>=0 && i<=x'],decreases='x-i')
 file=d/'contracts.json';file.write_text(json.dumps(contract)+'\n');receipt=d/'receipt.json'
 projected=json.loads(run(name+'-project',[probe,'runtime-contract',source,file,receipt]).stdout)
 assert projected['language']=='0.28' and projected['origin_bundle']['files']['main.nex']==original
 assert projected['revision']!=projected['origin_revision'] and not projected['proof_performed']
 candidate=d/'candidate';candidate.mkdir();bundle=projected['bundle'];assert bundle['entry']=='main.nex' and set(bundle['files'])=={'main.nex'}
 f=candidate/'main.nex';f.write_text(bundle['files']['main.nex'],encoding='utf-8',newline='')
 for mode in ['reference','ast','ir']:
  actual=json.loads(run(name+'-'+mode,[probe,mode,f]).stdout)
  assert actual['kind']==('trap' if error else 'return') and actual['output']==stdout,(name,mode,actual)
  if error:assert actual['code']==error
  else:assert actual['value']==42
 for opt in ['0','2']:
  e=d/('O'+opt);e.mkdir();run(name+'-emit'+opt,[probe,'emit',f,e,triple,layout,str(opt=='2').lower()])
  library=e/('program.dylib' if platform.system()=='Darwin' else 'program.dll' if os.name=='nt' else 'program.so')
  flags=['-dynamiclib','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared',*probe_dll_inputs(a.native_host,out)] if os.name=='nt' else ['-shared','-fPIC']
  run(name+'-compile'+opt,[a.compiler,'-O'+opt,*flags,e/'program.ll','-o',library])
  actual=run(name+'-native'+opt,[a.native_host,'run',library,'1'],allowed=(70 if error else exit_code(42),))
  assert actual.stdout==stdout
  if error:assert error in actual.stderr and 'NEX_SOURCE_EXCEPTION' not in actual.stderr
  else:assert not actual.stderr
 run(name+'-typescript',[probe,'typescript',f,candidate]);(candidate/'run.mjs').write_text(runner)
 actual=json.loads(run(name+'-node',[node,'--experimental-strip-types','--disable-warning=ExperimentalWarning',candidate/'run.mjs']).stdout)
 assert actual['kind']==('trap' if error else 'return') and actual['output']==stdout,(name,actual)
 if error:assert actual['code']==error
 else:assert actual['value']=='42'
 programs.append(candidate/'program.ts')
 assert source.read_bytes()==original.encode('utf-8')
 report['cases'].append({'name':name,'AST_TaskIR_Node_native_O0_O2':True,'original_preserved':True,'loop_annotations':loop_count,'passed':True});save()
 if name=='loop':
  # A review-bound JSON annotation must follow the original body through the
  # lowered source wrapper. Inline clauses do not implicitly request a proof.
  proof=json.loads(run('loop-explicit-proof',[probe,'verify-contract',source,file,d/'proof']).stdout)
  assert proof['ok'] and proof['language']=='0.28' and all(x['status']=='proven' for x in proof['functions']),proof
  report['cases'].append({'name':'explicit_scalar_loop_proof','passed':True});save()
  changed=copy.deepcopy(contract);changed['language']='0.27';bad=d/'wrong-language.json';bad.write_text(json.dumps(changed)+'\n');destination=d/'must-not-exist.json'
  actual=run('wrong-language-refused',[probe,'runtime-contract',source,bad,destination],allowed=(1,));assert 'E_CONTRACT' in actual.stderr and not destination.exists()
  report['cases'].append({'name':'cross_language_contract_refused_before_output','passed':True});save()
tsc=Path(os.environ['NEX_TSC']);pin=json.loads((W/'web/package.json').read_text())['devDependencies']['typescript'];assert json.loads((tsc.parent.parent/'package.json').read_text())['version']==pin
run('strict-typescript',[node,tsc,'--noEmit','--strict','--target','ES2022','--module','ESNext','--moduleResolution','bundler','--allowImportingTsExtensions',*programs])
report.update(ok=True,native_executions=2*len(cases),strict_TypeScript=True);save();print(json.dumps({'ok':True,'cases':len(report['cases']),'native_executions':report['native_executions'],'report':str(out/'report.json')}))
