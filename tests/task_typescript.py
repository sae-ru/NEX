"""Independent emitted generator programs against checked AST task outcomes."""
import argparse,ast,hashlib,json,os,shutil,subprocess,sys,tempfile,time
from pathlib import Path

parser=argparse.ArgumentParser()
parser.add_argument('emitter');parser.add_argument('reference')
parser.add_argument('--output');parser.add_argument('--case',action='append',dest='selected')
args=parser.parse_args();source=Path(__file__).resolve().parents[1]
emitter=str(Path(args.emitter).resolve());reference=str(Path(args.reference).resolve())
node=os.environ.get('NEX_NODE','node');env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
out=Path(args.output).resolve() if args.output else Path(tempfile.mkdtemp(prefix='nex-task-typescript-'))
if args.output:out.mkdir(exist_ok=False)
started=time.monotonic();records=[]
def run(command,timeout=180):
 p=subprocess.run(list(map(str,command)),text=True,capture_output=True,env=env,timeout=timeout)
 if p.returncode:raise AssertionError((list(map(str,command)),p.returncode,p.stdout,p.stderr))
 return p.stdout

# Literal checked source fixtures are shared with native execution. This does
# not execute that script's native driver or borrow its request dispatch.
tree=ast.parse((source/'tests/task_native.py').read_text())
assignment=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='cases' for t in n.targets))
capacities=next(n for n in tree.body if isinstance(n,ast.For) and isinstance(n.target,ast.Name) and n.target.id=='capacity')
namespace={};exec(compile(ast.Module(body=[assignment,capacities],type_ignores=[]),'literal-native-fixtures','exec'),{'__builtins__':{},'str':str},namespace)
cases=namespace['cases']
extras=[
 ('large-fifo','fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let q:channel<i64>=channel_new<i64>(s,5000);var i:i64=0;while i<5000{assert(task_send(q,i));i=i+1;}assert(task_close(q));i=0;var total:i64=0;while i<5000{let value:i64=unwrap(task_recv(q));assert(value==i);total=total+value;i=i+1;}assert(!is_ok(task_recv(q)));return total;});}','12497500','',0),
 ('generic','fn echo<T>(value:T)->T !{task}{task_yield();return value;}fn main()->i64 !{task}{return echo(42);}','42','',0),
 ('guarded-expression','enum Reply{Ready(items:list<i64>);Empty();}fn gate(n:i64)->bool !{task}{task_yield();return n>0;}fn main()->i64 !{task}{let item:Reply=Reply::Ready([0,42]);return match item{Reply::Ready([x,y]) if gate(x)=>x,Reply::Ready([_,y]) if gate(y)=>y,_=>1};}','42','',0),
 ('nested-result','fn get()->result<str> !{task}{task_yield();return err<str>("E_INNER","inner");}fn main()->result<list<str>> !{task}{return ok(["owned",get()?]);}','{"error":{"code":"E_INNER","message":"inner"}}','',0),
 ('parallel-map','fn twice(n:i64)->i64{return n*2;}fn main()->i64 !{task}{task_yield();let values:list<i64>=parallel_map([20,1],twice,2);return values[0]+values[1];}','42','',0),
 ('cancel-send','fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let q:channel<str>=channel_new<str>(s,0);let a:task<unit>=task_spawn(s,fn()->unit !{task}{task_send(q,"owned send");});task_yield();assert(task_cancel(a));assert(task_close(q));assert(!is_ok(task_recv(q)));return 42;});}','42','',0),
 ('cancel-receiver','fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let q:channel<str>=channel_new<str>(s,0);let a:task<str>=task_spawn(s,fn()->str !{task}{return unwrap(task_recv(q));});task_yield();assert(task_cancel(a));let b:task<str>=task_spawn(s,fn()->str !{task}{return unwrap(task_recv(q));});assert(task_send(q,"live"));assert(task_wait(b)=="live");return 42;});}','42','',0),
 ('late-fork','fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let a:task<unit>=task_spawn(s,fn()->unit !{task}{task_yield();let b:task<i64>=task_spawn(s,fn()->i64{return 1/0;});});return 42;});}','TRAP:E_DIV_ZERO:2','',0),
 ('scope-drain-cycle','fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let q:channel<task<i64>>=channel_new<task<i64>>(s,1);let a:task<i64>=task_spawn(s,fn()->i64 !{task}{return with_tasks(1,fn(inner:task_scope)->i64 !{task}{let b:task<i64>=task_spawn(inner,fn()->i64 !{task}{return task_wait(unwrap(task_recv(q)));});return 42;});});task_send(q,a);return task_wait(a);});}','TRAP:E_TASK_CYCLE','',0),
]
native_names={c[0] for c in cases};fixture_hashes={}
available_native=len(cases);cases+=extras
if args.selected:
 requested=set(args.selected);assert requested<=set(c[0] for c in cases),requested
 cases=[c for c in cases if c[0] in requested]
runner='''import * as task from './nex-task-runtime.ts';
import * as nex from './nex-runtime.ts';
import {entry} from './program.ts';
const logs=[];console.log=(value)=>logs.push(String(value));
const controller=new AbortController();let statistics;let yields=0;let polls=0;
const options={signal:controller.signal,complete:value=>{statistics=value;},observe:(job,r)=>{
 if(r.operation==='$poll')++polls;
 if(r.operation==='task_yield'){++yields;if(MODE==='cancel'&&job===0)controller.abort();}
}};
let observation;
try{const result=await task.run(task.call(()=>entry(...INPUTS),INPUTS),options);observation={ok:true,representation:result===undefined?'0':nex.representation(result)};}
catch(error){observation={ok:false,code:error.code??'HOST_ERROR',line:error.site?.[1]??0,message:error.message};}
if(!statistics||statistics.activeCalls||statistics.retainedFrames)throw new Error('generator teardown left logical frames/calls');
process.stdout.write(JSON.stringify({...observation,stdout:logs.join('\\n')+(logs.length?'\\n':''),statistics,yields,polls})+'\\n');
'''
programs=[]
try:
 for name,body,expected,prefix,_ in cases:
  path=out/(name+'.nex');path.write_text('module native_steps;\n'+body+'\n')
  if name in native_names:fixture_hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
  folder=out/name;metadata=json.loads(run([emitter,path,folder,'main']))
  assert metadata['ok'] and not metadata['public_source_tasks'] and metadata['schema']=='nex.private-typescript-task-map/1'
  mapping=json.loads((folder/'nex-map.json').read_text());assert mapping['schema']==metadata['schema'] and not mapping['public_source_tasks'] and 'revision' not in mapping
  (folder/'package.json').write_text('{"type":"module"}\n')
  mode='parameter' if name=='parameter' else 'cancel' if name=='cancel-call' else 'ordinary'
  (folder/'run.mjs').write_text(runner.replace('MODE',json.dumps(mode)).replace('INPUTS','[21n]' if mode=='parameter' else '[]'))
  actual_text=run([node,'--experimental-strip-types','--disable-warning=ExperimentalWarning',folder/'run.mjs'])
  (folder/'result.json').write_text(actual_text);actual=json.loads(actual_text)
  oracle_text=run([reference,path,mode]);(folder/'reference.json').write_text(oracle_text);oracle=json.loads(oracle_text)
  assert actual['stdout']==oracle['stdout']==prefix,(name,actual,oracle)
  if expected.startswith('TRAP:'):
   parts=expected.split(':');assert actual['ok'] is oracle['ok'] is False and actual['code']==oracle['code']==parts[1],(name,actual,oracle)
   if len(parts)>2 and parts[2]!='0':assert actual['line']==oracle['line']==int(parts[2]),(name,actual,oracle)
  else:assert actual['ok'] is oracle['ok'] is True and actual['representation']==oracle['representation']==expected,(name,actual,oracle)
  records.append({'name':name,'ok':True,'steps':actual['statistics']['steps'],'yields':actual['yields'],'polls':actual['polls']});programs.append(str(folder/'program.ts'))
  print(name+' passed',flush=True)

 host=None
 if not args.selected:
  spin=out/'host-spin.nex';spin.write_text('module host_spin;server fn secret()->str{return "UNREACHABLE_SERVER_TASK_SECRET";}fn spin()->i64{var i:i64=0;while true{i=i+1;}return 0;}fn main()->i64 !{task}{return spin();}')
  folder=out/'host-spin';run([emitter,spin,folder,'main']);(folder/'package.json').write_text('{"type":"module"}\n');programs.append(str(folder/'program.ts'))
  assert 'UNREACHABLE_SERVER_TASK_SECRET' not in (folder/'program.ts').read_text()
  assert 'secret' not in (folder/'nex-map.json').read_text()
  script=out/'scope-spawn'/'host.mjs';shutil.copy2(source/'tests/task_typescript_host.mjs',script)
  raw=run([node,'--experimental-strip-types','--disable-warning=ExperimentalWarning',script]);(out/'host-boundary-result.json').write_text(raw);host=json.loads(raw)
  assert host['ok'] and host['host_guard_cases']==16 and host['actual_node_host_cancellation'] and host['event_loop_timer_ticks']>0 and host['compiler_checkpoint_turns']>0,host
 # Use the exact pinned TypeScript compiler, preferring an operator-selected
 # existing installation. Otherwise install locked packages from the cache;
 # npm lifecycle scripts and external network are disabled.
 tsc=os.environ.get('NEX_TSC')
 if tsc:
  tsc=Path(tsc).resolve();assert tsc.is_file(),tsc
 else:
  assert os.environ.get('NEX_NPM_CACHE'),'Set NEX_TSC to the pinned compiler or NEX_NPM_CACHE to its populated offline package cache'
  tool=out/'typecheck-tool';tool.mkdir();shutil.copy2(source/'web/package.json',tool/'package.json');shutil.copy2(source/'web/package-lock.json',tool/'package-lock.json')
  run([os.environ.get('NEX_NPM','npm'),'ci','--ignore-scripts','--offline','--prefix',tool,'--cache',os.environ['NEX_NPM_CACHE']])
  tsc=tool/'node_modules/typescript/bin/tsc'
 package=json.loads((tsc.parent.parent/'package.json').read_text());pin=json.loads((source/'web/package.json').read_text())['devDependencies']['typescript'];assert package['version']==pin,(package['version'],pin)
 checked=subprocess.run([node,str(tsc),'--noEmit','--strict','--target','ES2022','--module','ESNext','--moduleResolution','bundler','--allowImportingTsExtensions','--lib','ES2022,DOM',*programs],text=True,capture_output=True,env=env,timeout=180)
 (out/'typecheck.stdout').write_text(checked.stdout);(out/'typecheck.stderr').write_text(checked.stderr);assert checked.returncode==0,checked.stdout+checked.stderr
 report={'ok':True,'source_scenarios':len(records),'native_fixture_scenarios':sum(r['name'] not in {c[0] for c in extras} for r in records),'available_native_scenarios':available_native,'independent_asynchronous_typescript':True,'native_source_fixture_sha256':fixture_hashes,'host_boundary':host,'independent_ast_agreement':True,'actual_native_execution_in_this_test':False,'strict_typecheck':True,'typescript_version':package['version'],'public_source_tasks':False,'records':records,'seconds':round(time.monotonic()-started,3)}
 (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
except BaseException:
 print('Failed TypeScript task sources/runtime/results retained at '+str(out),file=sys.stderr);raise
else:
 if not args.output:shutil.rmtree(out)
