"""Explicit028 contracts: observable agreement and rejected source programs."""
from pathlib import Path
import argparse,hashlib,json,os,platform,re,subprocess,tempfile,time
from host_fixture import run_native,exit_code,probe_dll_inputs
p=argparse.ArgumentParser();p.add_argument('probe');p.add_argument('--compiler',required=True);p.add_argument('--native-host',required=True);p.add_argument('--output',type=Path);a=p.parse_args()
root=Path(__file__).resolve().parents[1];probe=str(Path(a.probe).resolve())
out=a.output.resolve() if a.output else Path(tempfile.mkdtemp(prefix='nex-source-contracts028-'));out.mkdir(parents=True,exist_ok=a.output is None)
env={**os.environ,'NEX_RESOURCE_DIR':str(root),'PYTHONDONTWRITEBYTECODE':'1'};node=env.get('NEX_NODE','node')
started=time.monotonic();records=[];report={'schema':'nex.source-contract-tests/1','ok':False,'language':'0.28','ordinary_CLI_tested':False,'cases':records,'commands':[]}
def save():
 report['seconds']=round(time.monotonic()-started,3);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
def run(label,cmd,allowed=(0,),timeout=180):
 r=run_native(list(map(str,cmd)),env=env,text=True,capture_output=True,timeout=timeout)
 (out/(label+'.stdout')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr)
 report['commands'].append({'label':label,'exit_code':r.returncode});save()
 assert r.returncode in allowed,(label,r.returncode,r.stdout[-2000:],r.stderr[-4000:])
 return r
cases=[
('ordinary',"""fn inc(x:i64)->i64 requires(x>=0) ensures(r=>r==x+1){return x+1;}
fn main()->i64{let action:fn(i64)->i64=inc;assert(action(41)==42);return 42;}""",None,''),
('generic',"""fn same<T>(a:T,b:T)->bool{return a==b;}
fn identity<T>(value:T)->T requires(same<T>(value,value)) ensures(r=>(fn(x:T)->T{return x;})(r)==value){return value;}
fn phantom<T:wire>()->i64 ensures(r=>r==42){return 42;}
fn main()->i64{assert(identity("λ🙂")=="λ🙂");assert(identity([1,2])==[1,2]);assert(phantom<str>()==42&&phantom<i64>()==42);return 42;}""",None,''),
('kinds',"""struct Box<T>{value:T;}
fn identity<F<_>,T>(value:F<T>)->F<T> ensures(r=>r==value){return value;}
trait Item{type Value;fn get(value:Self)->Item::Value<Self>;}
fn extract<T>(value:Box<T>)->T{return value.value;}
impl boxed<T>:Item for Box<T>{type Value=T;get=extract<T>;}
fn read<T:Item>(value:T)->Item::Value<T> ensures(r=>r==Item<T>::get(value)){return Item<T>::get(value);}
fn main()->i64{assert(identity<Box,str>(Box<str>("🙂"))==Box<str>("🙂"));assert(read(Box<i64>(42))==42);return 42;}""",None,''),
('pre-before-body',"""fn work()->i64 !{io} requires(false){try{print("MUST_NOT_RUN");return 42;}finally{print("MUST_NOT_RUN");}}
fn main()->i64 !{io}{try{return work();}catch(c,m){return 0;}}""",'E_ASSERT',''),
('predicate-overflow',"""fn work()->i64 requires(9223372036854775807+1>0){return 42;}
fn main()->i64{return work();}""",'E_OVERFLOW',''),
('predicate-short-circuit',"""fn work()->i64 requires(true||(1/0==0)) ensures(value=>value==42&&(true||(9223372036854775807+1==0))){return 42;}
fn main()->i64{return work();}""",None,''),
('ranking-negative',"""fn main()->i64 !{io}{while true invariant(true) decreases(-1){print("MUST_NOT_RUN");}return 42;}""",'E_ASSERT',''),
('pre-location',"""fn work()->i64
 requires(false)
 {return 42;}
fn main()->i64{return work();}""",'E_ASSERT',''),
('post-location',"""fn work()->str
 ensures(value=>false)
 {return "owned";}
fn main()->i64{work();return 42;}""",'E_ASSERT',''),
('post-after-finally',"""fn work()->str !{io} ensures(r=>false){try{print("body");return "owned";}finally{print("finally");}}
fn main()->i64 !{io}{try{work();return 0;}finally{print("MUST_NOT_RUN");}}""",'E_ASSERT','body\nfinally\n'),
('error-skips-post',"""fn work()->list<str> !{io,throw} ensures(r=>false){try{throw(["owned","λ"]);}finally{print("finally");}}
fn main()->i64 !{io,throw}{try{work();return 0;}catch(e:list<str>){assert(e==["owned","λ"]);return 42;}}""",None,'finally\n'),
('result-and-finally',"""fn failure()->result<i64> ensures(r=>!is_ok(r)){let x:i64=err<i64>("E","expected")?;return ok(x);}
fn choose<T>(a:T,b:T)->T ensures(r=>r==b){try{return a;}finally{return b;}}
fn main()->i64{assert(!is_ok(failure()));assert(choose(["old"],["new"])==["new"]);return 42;}""",None,''),
('unit',"""fn work(x:str)->unit !{io} requires(len(x)>0) ensures(len(x)>0){print(x);}
fn main()->i64 !{io}{work("λ");return 42;}""",None,'λ\n'),
('pure-handled-source-errors',"""fn recovered(n:i64)->bool{try{throw(n);}catch(e:i64){return e>=0;}}
fn checked(n:i64)->i64 requires(recovered(n)) ensures(r=>recovered(r)){return n;}
fn main()->i64{var i:i64=0;while i<2 invariant(recovered(i)) decreases(2-i){i=i+1;}return checked(42);}""",None,''),
('recursion',"""fn sum(n:i64)->i64 requires(n>=0&&n<10) ensures(r=>r>=n){if n==0{return 0;}return n+sum(n-1);}
fn main()->i64{assert(sum(6)==21);return 42;}""",None,''),
('loop-values',"""fn repeat<T>(value:T,n:i64)->list<T> requires(n>=0&&n<8) ensures(r=>len(r)==n){
var i:i64=0;var items:list<T>=[];
while i<n invariant(i>=0&&i<=n) invariant(len(items)==i) decreases(n-i){items=items+[value];i=i+1;}return items;}
fn main()->i64{assert(repeat("🙂",3)==["🙂","🙂","🙂"]);return 42;}""",None,''),
('loop-false',"""fn main()->i64{while false invariant(true) decreases(1/0){assert(false);}return 42;}""",None,''),
('loop-entry',"""fn condition()->bool !{io}{print("MUST_NOT_RUN");return true;}
fn main()->i64 !{io}{while condition() invariant(false) decreases(1/0){}return 42;}""",'E_ASSERT',''),
('loop-descent',"""fn main()->i64 !{io}{var i:i64=0;while i<2 invariant(i<=2) decreases(1){print("body");i=i+1;}return 42;}""",'E_ASSERT','body\n'),
('loop-helpers',"""fn valid(i:i64)->bool{return i>=0&&i<=2;}
fn rank(i:i64)->i64{return 2-i;}
fn main()->i64{var i:i64=0;while i<2 invariant((fn()->bool{return valid(i);})()) decreases(rank(i)){i=i+1;}return 42;}""",None,''),
('loop-shadow',"""fn main()->i64{var i:i64=0;while i<2 invariant(i<=2) decreases(2-i){i=i+1;let i:str="shadow";assert(i=="shadow");}return 42;}""",None,''),
('loop-early',"""fn main()->i64{while true invariant(true) decreases(42){return 42;}return 0;}""",None,''),
('loop-finalizer',"""fn main()->i64{var i:i64=0;while i<2 invariant(i>=0&&i<=2) decreases(2-i){try{throw(i);}catch(e:i64){assert(e==i);}finally{i=i+1;}}return 42;}""",None,''),
('nested-loops',"""fn main()->i64{var i:i64=0;while i<3 invariant(i<=3) decreases(3-i){var j:i64=0;while j<2 invariant(j<=2) decreases(2-j){j=j+1;}i=i+1;}return 42;}""",None,''),
('lexical-names',"""fn requires(ensures:i64)->i64{return ensures;}
fn main()->i64{let invariant:i64=42;let decreases:i64=0;return requires(invariant+decreases);}""",None,''),
('generated-name-collisions',"""fn nex_source_contract_body_work()->i64{return 0;}
fn work(x:i64)->i64 requires(x>=0) ensures(r=>r==x){let nex_source_contract_result_work:i64=0;return x+nex_source_contract_result_work;}
fn main()->i64{let nex_source_contract_rank_1:i64=42;var i:i64=0;while i<2 invariant(i<=2) decreases(2-i){i=i+1;}assert(nex_source_contract_body_work()==0);return work(nex_source_contract_rank_1);}""",None,''),
('task',"""fn work<T>(value:T)->T !{task} ensures(r=>r==value){
var i:i64=0;while i<2 invariant(i<=2) decreases(2-i){task_yield();i=i+1;}return value;}
fn body(scope:task_scope)->i64 !{task,throw}{let result:list<str>=task_wait(task_spawn(scope,fn()->list<str> !{task}{return work(["owned","🙂"]);}));assert(result==["owned","🙂"]);return 42;}
fn main()->i64 !{task,throw}{return with_tasks(2,body);}""",None,''),
('task-post',"""fn work(value:list<str>)->list<str> !{task} ensures(r=>false){task_yield();return value;}
fn body(scope:task_scope)->i64 !{task,throw}{task_wait(task_spawn(scope,fn()->list<str> !{task}{return work(["owned","🙂"]);}));return 0;}
fn main()->i64 !{task,throw}{return with_tasks(2,body);}""",'E_ASSERT',''),
('task-error-skips-post',"""fn work(value:list<str>)->list<str> !{task,throw} ensures(r=>false){try{task_yield();throw(["old"]);}finally{task_yield();throw(value);}}
fn body(scope:task_scope)->i64 !{task,throw}{try{task_wait(task_spawn(scope,fn()->list<str> !{task,throw}{return work(["owned","🙂"]);}));return 0;}catch(e:list<str>){assert(e==["owned","🙂"]);return 42;}}
fn main()->i64 !{task,throw}{return with_tasks(2,body);}""",None,''),
]
rejects=[
('pre-effect','fn bad()->i64 !{io} requires((fn()->bool !{io}{print("bad");return true;})()){return 1;}','E_EFFECT'),
('post-effect','fn bad()->i64 !{io} ensures(r=>(fn()->bool !{io}{print(r);return true;})()){return 1;}','E_EFFECT'),
('unused-generic','fn bad<T>(value:T)->T requires(value+value==value){return value;}','E_TYPE'),
('post-shadow','fn bad(x:i64)->i64 ensures(x=>true){return x;}','E_CONTRACT_SYNTAX'),
('pre-result','fn bad()->i64 requires(result==1){return 1;}','E_NAME'),
('post-body-local','fn bad()->i64 ensures(r=>inside==r){let inside:i64=1;return inside;}','E_NAME'),
('pre-type','fn bad()->i64 requires(1){return 1;}','E_TYPE'),
('lazy-effect','fn effect()->bool !{io}{return true;}fn bad()->i64 !{io} requires(true||effect()){return 1;}','E_EFFECT'),
('loop-effect','fn bad()->unit !{io}{while false invariant((fn()->bool !{io}{print("bad");return true;})()) decreases(1){}}','E_EFFECT'),
('loop-throw-grant','fn boom()->bool !{throw}{throw(42);}fn bad()->unit{try{while false invariant(boom()) decreases(1){}}catch(e:i64){}}','E_EFFECT'),
('loop-propagation','fn bad()->result<i64>{while false invariant(unwrap(ok(true))) decreases(ok(1)?){ }return ok(1);}','E_RESULT_RETURN'),
('loop-missing-rank','fn bad()->unit{while false invariant(true){}}','E_CONTRACT_SYNTAX'),
('loop-missing-invariant','fn bad()->unit{while false decreases(1){}}','E_CONTRACT_SYNTAX'),
]
rejects += [
 ('too-many-pre','fn bad()->i64 '+('requires(true) '*65)+'{return 1;}','E_CONTRACT_LIMIT'),
 ('too-many-invariants','fn bad()->unit{while false '+('invariant(true) '*65)+' decreases(1){}}','E_CONTRACT_LIMIT'),
 ('UTF8-clause-size','fn bad()->i64 requires("'+('🙂'*1025)+'"==""){return 1;}','E_CONTRACT_LIMIT'),
]
runner=r"""import * as program from './program.ts';
import * as nex from './nex-runtime.ts';
import * as sourceException from './nex-source-exception-runtime.ts';
const logs=[];console.log=(x)=>logs.push(String(x));
let actual;
try {
 let value;
 if(ASYNC){const task=await import('./nex-task-runtime.ts');value=await task.runTypedSourceErrors(task.call(()=>program.main()),program.sourceErrorContracts);}
 else value=program.main();
 actual={kind:'return',value:typeof value==='bigint'?value.toString():value??null};
}catch(error){
 if(error instanceof nex.NexError)actual={kind:'trap',code:error.code,line:error.site?.[1]??0};
 else if(sourceException.details(error)!==undefined)actual={kind:'exception'};
 else throw error;
}
process.stdout.write(JSON.stringify({...actual,output:logs.join('\n')+(logs.length?'\n':'')})+'\n');
"""
save()
host=out/'host.ll';run('host',[a.compiler,'-x','c','-S','-emit-llvm',os.devnull,'-o',host])
t=host.read_text();triple=re.search(r'target triple = "(.*?)"',t)[1];layout=re.search(r'target datalayout = "(.*?)"',t)[1];programs=[]
for name,text,error,stdout in cases:
 d=out/name;d.mkdir();f=d/'main.nex';f.write_text('module contracts;\n'+text)
 check=json.loads(run(name+'-check',[probe,'check',f]).stdout)
 assert check['language']=='0.28';(d/'checked.json').write_text(json.dumps(check,indent=2)+'\n')
 if name!='lexical-names':
  prior=run(name+'-retained',[probe,'retained',f],allowed=(1,));assert 'E_PARSE' in prior.stderr or 'E_LANGUAGE_VERSION' in prior.stderr
 for mode in ['reference','ast','ir']:
  if name.startswith('task') and mode=='reference':continue
  actual=json.loads(run(name+'-'+mode,[probe,mode,f]).stdout)
  assert actual['kind']==('trap' if error else 'return'),(name,mode,actual)
  if error:assert actual['code']==error,(name,mode,actual)
  else:assert actual['value']==42,(name,mode,actual)
  if name in ['pre-location','post-location']:assert actual['line']==3,(name,mode,actual)
  assert actual.get('output','')==stdout,(name,mode,actual,stdout)
 for opt in ['0','2']:
  e=d/('O'+opt);e.mkdir();run(name+'-emit'+opt,[probe,'emit',f,e,triple,layout,str(opt=='2').lower()])
  lib=e/('program.dylib' if platform.system()=='Darwin' else 'program.dll' if os.name=='nt' else 'program.so')
  flags=['-dynamiclib','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared',*probe_dll_inputs(probe,out)] if os.name=='nt' else ['-shared','-fPIC']
  run(name+'-compile'+opt,[a.compiler,'-O'+opt,*flags,e/'program.ll','-o',lib])
  for workers in ([1,4] if name.startswith('task') else [1]):
   actual=run(name+'-native'+opt+'-'+str(workers),[a.native_host,'run',lib,str(workers)],allowed=(70 if error else exit_code(42),))
   assert actual.stdout==stdout,(name,opt,workers,actual.stdout,stdout)
   if error:assert error in actual.stderr and 'NEX_SOURCE_EXCEPTION' not in actual.stderr,(name,opt,workers,actual.stderr)
   else:assert not actual.stderr,(name,opt,workers,actual.stderr)
   if name in ['pre-location','post-location']:
    diagnostic=json.loads(next(line.split(' ',1)[1] for line in actual.stderr.splitlines() if line.startswith('NEX_NATIVE_TRAP ')))
    assert diagnostic['reported_line']==3,(name,opt,diagnostic)
 run(name+'-typescript',[probe,'typescript',f,d]);mapping=json.loads((d/'nex-map.json').read_text());assert mapping['schema']=='nex.development-typescript/028-1' and mapping['language']=='0.28'
 (d/'run.mjs').write_text(runner.replace('ASYNC',str(name.startswith('task')).lower()))
 actual=json.loads(run(name+'-node',[node,'--experimental-strip-types','--disable-warning=ExperimentalWarning',d/'run.mjs']).stdout)
 assert actual['kind']==('trap' if error else 'return') and actual['output']==stdout,(name,actual)
 if error:assert actual['code']==error,(name,actual)
 else:assert actual['value']=='42',(name,actual)
 if name in ['pre-location','post-location']:assert actual['line']==3,(name,'node',actual)
 if name.startswith('task'):
  tested=json.loads(run(name+'-CPP-web-test',[probe,'typescript-run',f,d/'CPP-test']).stdout)
  assert tested['exit_code']==(1 if error else 0) and tested['stdout']==stdout,(name,tested)
  if error:assert error in tested['stderr'],(name,tested)
  else:assert not tested['stderr'],(name,tested)
 programs.append(d/'program.ts')
 records.append({'name':name,'source_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'native_optimizations':['O0','O2'],'AST':True,'TaskIR':True,'Node':True,'passed':True});save()
for name,text,code in rejects:
 d=out/('reject-'+name);d.mkdir();f=d/'main.nex';f.write_text('module refused;\n'+text+'\nfn main()->i64{return 42;}')
 r=run(name+'-rejected',[probe,'check',f],allowed=(1,))
 assert code in r.stderr,(name,code,r.stderr)
 records.append({'name':name,'rejected':True,'code':code,'passed':True});save()
tsc=Path(os.environ['NEX_TSC']);pin=json.loads((root/'web/package.json').read_text())['devDependencies']['typescript'];assert json.loads((tsc.parent.parent/'package.json').read_text())['version']==pin
run('strict-typescript',[node,tsc,'--noEmit','--strict','--target','ES2022','--module','ESNext','--moduleResolution','bundler','--allowImportingTsExtensions',*programs])
report.update(ok=True,success_and_trap_cases=len(cases),refusals=len(rejects),native_executions=sum(4 if n.startswith('task') else 2 for n,_,_,_ in cases),strict_TypeScript=True);save()
print(json.dumps({'ok':True,'cases':len(cases),'refusals':len(rejects),'report':str(out/'report.json')}))
