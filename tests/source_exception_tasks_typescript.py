"""Private generator task errors vs the independent AST task scheduler."""
import argparse,hashlib,json,os,re,subprocess,tempfile,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('probe');p.add_argument('--output');a=p.parse_args()
source=Path(__file__).resolve().parents[1];probe=str(Path(a.probe).resolve());node=os.environ.get('NEX_NODE','node')
out=Path(a.output or os.environ.get('NEX_EXCEPTION_TASK_TYPESCRIPT_OUTPUT') or tempfile.mkdtemp(prefix='nex-task-exception-ts-')).resolve();out.mkdir(parents=True,exist_ok=True)
env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'};started=time.monotonic();records=[];programs=[]
report={'ok':False,'public_language':'0.24','private_identity':'0.25-prototype','public_source_support':False,'private_task_typescript':True,'native_task_exceptions':False,'ordinary_functional_only':True,'security_checks_deferred_by_user':True,'cases':records}
def save():
 report['seconds']=round(time.monotonic()-started,3);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
def run(cmd,timeout=120):
 r=subprocess.run(list(map(str,cmd)),text=True,capture_output=True,env=env,timeout=timeout)
 if r.returncode:raise AssertionError((list(map(str,cmd)),r.returncode,r.stdout,r.stderr))
 return r.stdout
fixture_file=source/'tests/source_exception_tasks.cpp';raw=fixture_file.read_text()
fixtures=[(kind,name,text,200 if name=='scheduler-budget' else 1000000) for kind,name,text in re.findall(r'\b(value|sourceError|trap)\("([^"]+)",R"\((.*?)\)"',raw,re.S) if name not in {'parent-budget','parent-cancellation'}]
assert len(fixtures)==27,len(fixtures)
fixtures += [('value','result-error-priority','fn main()->i64 !{task,throw}{let value:result<i64>=with_tasks(2,fn(s:task_scope)->result<i64> !{task}{let failed:task<i64>=task_spawn(s,fn()->i64 !{throw}{throw("CHILD","ignored");});task_yield();return err<i64>("RESULT","wins");});assert(!is_ok(value)&&error_code(value)=="RESULT");return 42;}',1000000),('value','client-pruning','server fn secret()->str !{throw}{throw("SERVER_SECRET","MUST_NOT_SHIP");}client fn main()->i64 !{task}{try{task_yield();throw("CLIENT","visible");}catch(code,message){return 42;}}',1000000)]
fixtures += [('value','source-code-looks-fatal','fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let child:task<i64>=task_spawn(s,fn()->i64 !{throw}{throw("E_LIMIT","user data");});try{return task_wait(child);}catch(code,message){assert(code=="E_LIMIT"&&message=="user data");return 42;}});}',1000000),('trap','nested-budget','fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{try{while true{task_yield();}}catch(code,message){return 0;}return 42;});}',200)]
runner=r'''import * as program from './program.ts';import * as nex from './nex-runtime.ts';import * as task from './nex-task-runtime.ts';import * as sourceException from './nex-source-exception-runtime.ts';
const logs=[];console.log=(value)=>logs.push(String(value));let record,statistics;
try{const value=await task.runSourceExceptionPrototype(task.call(()=>program.main()),error=>sourceException.details(error)!==undefined,{steps:STEPS,timeoutMs:10000,workers:2,complete:s=>statistics=s});record={kind:'return',value:typeof value==='bigint'?value.toString():value??null};}
catch(error){const payload=sourceException.details(error);if(payload!==undefined)record={kind:'exception',code:payload.code,message:payload.message,file:payload.site[0],line:payload.site[1],column:payload.site[2],site:payload.site[3]};else if(error instanceof nex.NexError)record={kind:'trap',code:error.code,line:error.site?.[1]??0};else throw error;}
if(!statistics||!statistics.completed||statistics.retainedFrames||statistics.activeCalls||statistics.externalPending||statistics.externalReservedBytes||statistics.externalMailbox)throw new Error('task source-error execution retained state');
process.stdout.write(JSON.stringify({...record,output:logs.join('\n')+(logs.length?'\n':''),statistics})+'\n');
'''
save()
for kind,name,text,steps in fixtures:
 d=out/name;d.mkdir(exist_ok=True);(d/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.24','entry':'main.nex'}));f=d/'main.nex';f.write_text('module task_exception;\n'+text+'\n')
 reference=json.loads(run([probe,'reference',f,str(steps)]));(d/'reference.json').write_text(json.dumps(reference,indent=2)+'\n')
 run([probe,'typescript',f,d]);mapping=json.loads((d/'nex-map.json').read_text());assert mapping['schema']=='nex.private-typescript-exception-map/1' and mapping['language']=='0.25-prototype' and mapping['task_source_exceptions'] is True and mapping['execution']=='task-generator' and not mapping['source_support'] and 'revision' not in mapping
 script=d/'run.mjs';script.write_text(runner.replace('STEPS',str(steps)));actual=json.loads(run([node,'--experimental-strip-types','--disable-warning=ExperimentalWarning',script]));(d/'actual.json').write_text(json.dumps(actual,indent=2)+'\n')
 assert actual['kind']==reference['kind'],(name,actual,reference)
 if actual['kind']=='return':
  expected=str(reference['value']) if type(reference['value']) is int else reference['value'];assert actual['value']==expected,(name,actual,reference)
 elif actual['kind']=='exception':
  for k in ['code','message','line','column','file']:assert actual[k]==reference[k],(name,k,actual,reference)
  assert any(op['site']==actual['site'] and op['kind']=='statement.throw' for fn in mapping['functions'] for op in fn['operations']),name
 else:assert actual['code']==reference['code'],(name,actual,reference)
 if 'output' in reference:assert actual['output']==reference['output'],(name,actual,reference)
 if name=='client-pruning':
  emitted=(d/'program.ts').read_text()+json.dumps(mapping);assert 'SERVER_SECRET' not in emitted and 'MUST_NOT_SHIP' not in emitted and 'nex_user_secret' not in emitted
 records.append({'name':name,'kind':actual['kind'],'source_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'passed':True,'completed':actual['statistics']['completed'],'retained_frames':actual['statistics']['retainedFrames'],'active_calls':actual['statistics']['activeCalls']});programs.append(d/'program.ts');save()
# These simultaneous drivers share one module but no error-classification state.
boundary=out/'driver-boundaries';boundary.mkdir(exist_ok=True)
import shutil
for name in ['nex-runtime.ts','nex-bytes.ts','nex-task-runtime.ts','nex-source-exception-runtime.ts']:shutil.copy2(out/fixtures[0][1]/name,boundary/name)
(boundary/'run.mjs').write_text(r"""import * as nex from './nex-runtime.ts';import * as task from './nex-task-runtime.ts';import * as source from './nex-source-exception-runtime.ts';
let count=0,statistics=[];
const classify=e=>source.details(e)!==undefined;
const finish=s=>{if(!s.completed||s.activeCalls||s.retainedFrames||s.externalPending||s.externalReservedBytes||s.externalMailbox)throw new Error('driver leaked state');statistics.push(s);};
const raised=(code)=>{try{source.raise(code,'payload',['driver.nex',7,3,'original']);}catch(e){return e;}};
const first=raised('E_LIMIT'),second=raised('SECOND'),host=new Error('host failure');
const call=(error)=>task.call(function*(){yield task.request('task_yield',[]);throw error;});
const check=async(promise,expected)=>{try{await promise;throw new Error('failure missing');}catch(e){if(e!==expected)throw new Error('wrong error identity');++count;}};
await Promise.all([
 check(task.runSourceExceptionPrototype(call(first),classify,{complete:finish}),first),
 check(task.runSourceExceptionPrototype(call(second),classify,{complete:finish}),second),
 check(task.runSourceExceptionPrototype(call(host),classify,{complete:finish}),host),
 (async()=>{try{await task.run(call(first),{complete:finish});throw new Error('public run accepted source classification');}catch(e){if(!(e instanceof Error)||e===first||source.details(e)!==undefined)throw e;++count;}})()
]);
const controller=new AbortController();
try{await task.runSourceExceptionPrototype(task.call(function*(){while(true)yield task.request('task_yield',[]);}),classify,{signal:controller.signal,observe:()=>controller.abort(),complete:finish});throw new Error('cancellation missing');}catch(e){if(!(e instanceof nex.NexError)||e.code!=='E_CANCELLED'||source.details(e)!==undefined)throw e;++count;}
try{await task.runSourceExceptionPrototype(task.call(function*(){while(true)yield task.request('task_yield',[]);}),classify,{timeoutMs:5,steps:1000000,complete:finish});throw new Error('deadline missing');}catch(e){if(!(e instanceof nex.NexError)||e.code!=='E_TIMEOUT'||source.details(e)!==undefined)throw e;++count;}
process.stdout.write(JSON.stringify({ok:true,cases:count,completed_drivers:statistics.length})+'\n');
""")
controls=json.loads(run([node,'--experimental-strip-types','--disable-warning=ExperimentalWarning',boundary/'run.mjs']));assert controls['ok'] and controls['cases']==6 and controls['completed_drivers']==6
(boundary/'result.json').write_text(json.dumps(controls,indent=2)+'\n')
# The exact pinned compiler is an explicit prerequisite, as for the other private TS probes.
tsc=Path(os.environ['NEX_TSC']).resolve();assert tsc.is_file();package=json.loads((tsc.parent.parent/'package.json').read_text());pin=json.loads((source/'web/package.json').read_text())['devDependencies']['typescript'];assert package['version']==pin
checked=subprocess.run([node,str(tsc),'--noEmit','--strict','--target','ES2022','--module','ESNext','--moduleResolution','bundler','--allowImportingTsExtensions','--lib','ES2022,DOM',*map(str,programs)],text=True,capture_output=True,env=env,timeout=180)
(out/'typecheck.stdout').write_text(checked.stdout);(out/'typecheck.stderr').write_text(checked.stderr);assert checked.returncode==0,checked.stdout+checked.stderr
report.update(ok=True,comparisons=len(records),reference_fixture_file_sha256=hashlib.sha256(fixture_file.read_bytes()).hexdigest(),driver_boundaries=controls,strict_typecheck=True,typescript_version=package['version'],reference_agreement=True,actual_native_task_execution=False);save();print(json.dumps({'ok':True,'comparisons':len(records),'typescript_version':package['version'],'report':str(out/'report.json')}))
