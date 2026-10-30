#!/usr/bin/env python3
"""Candidate027 AST/TaskIR/native O0/O2/Node agreement across real task pauses."""
import argparse,ast,json,os,platform,re,shutil,subprocess,tempfile,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('probe');p.add_argument('--compiler',required=True);p.add_argument('--output',type=Path);a=p.parse_args()
root=Path(__file__).resolve().parents[1];runtime=root/'runtime';probe=str(Path(a.probe).resolve());compiler=a.compiler
out=a.output.resolve() if a.output else Path(tempfile.mkdtemp(prefix='nex-typed-source-tasks-'));out.mkdir(parents=True,exist_ok=a.output is None)
started=time.monotonic();records=[];report={'ok':False,'candidate_language':'0.27','public027_enabled':False,'descriptor_abi':'0x4e45585400002701','cases':records,'commands':[]}
def save():report['seconds']=round(time.monotonic()-started,3);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
def run(label,cmd,allowed=(0,),timeout=180):
 r=subprocess.run(list(map(str,cmd)),text=True,capture_output=True,timeout=timeout,env={**os.environ,'NEX_RESOURCE_DIR':str(root)})
 (out/(label+'.stdout')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr)
 report['commands'].append({'label':label,'exit_code':r.returncode});save()
 assert r.returncode in allowed,(label,r.returncode,r.stdout[-2000:],r.stderr[-5000:],str(out))
 return r
cases=[
 ('literal-true-legacy','fn main()->i64 !{task}{try{task_yield();throw(42);}catch(c,m) if true{task_yield();return 42;}}'),
 ('fatal-filter','fn guard()->bool !{task}{task_yield();assert(false);return true;}fn main()->i64 !{task,io}{try{try{throw(42);}catch(e:i64) if guard(){return 0;}catch(e:i64){return e;}}finally{print("MUST_NOT_RUN");}}'),
 ('scalar-kinds','fn main()->i64 !{task}{try{throw(true);}catch(e:bool){task_yield();assert(e);}try{throw(1.25);}catch(e:f64){task_yield();assert(e==1.25);}return 42;}'),
 ('enum-value','enum Failure{Missing(path:str);}fn main()->i64 !{task}{try{throw(Failure::Missing("path"));}catch(e:Failure){task_yield();match e{Failure::Missing(path)=>{assert(path=="path");return 42;}}}}'),
 ('result-value','fn main()->i64 !{task}{try{throw(ok(42));}catch(e:result<i64>){task_yield();assert(unwrap(e)==42);}try{throw(err<i64>("E","hidden"));}catch(e:result<i64>){task_yield();assert(!is_ok(e)&&error_code(e)=="E");}return 42;}'),
 ('bytes-value','fn main()->i64 !{task}{try{throw(utf8_bytes("λ"));}catch(e:bytes){task_yield();assert(len(e)==2);}return 42;}'),
 ('yield-scalar','fn main()->i64 !{task}{try{task_yield();throw(42);}catch(e:i64){task_yield();return e;}}'),
 ('guard-pause','fn decline(e:i64)->bool !{task,io}{task_yield();print(e);return false;}fn main()->i64 !{task,io}{try{throw(42);}catch(e:i64) if decline(e){return 0;}catch(e:i64){task_yield();return e;}}'),
 ('mismatch-skips-guard','fn forbidden()->bool !{task}{task_yield();assert(false);return true;}fn main()->i64 !{task}{try{throw([42]);}catch(e:str) if forbidden(){return 0;}catch(e:list<i64>){task_yield();return e[0];}}'),
 ('predicate-error-skips-siblings','fn replacement()->bool !{task,throw}{task_yield();throw(42);}fn main()->i64 !{task}{try{try{throw("old");}catch(e:str) if replacement(){return 0;}catch(e:i64){return 0;}}catch(e:i64){return e;}catch(c,m){return 0;}}'),
 ('handler-error-skips-siblings','fn main()->i64 !{task}{try{try{throw("old");}catch(e:str){task_yield();throw(42);}catch(e:i64){return 0;}}catch(e:i64){return e;}catch(c,m){return 0;}}'),
 ('retained-list','fn main()->i64 !{task}{var result:list<str>=["old"];try{throw(["λ","🙂"]);}catch(e:list<str>){task_yield();result=e;}task_yield();assert(result[0]=="λ"&&result[1]=="🙂");return 42;}'),
 ('pending-error-finally','fn main()->i64 !{task,io}{try{try{task_yield();throw([42]);}finally{task_yield();print("cleanup");}}catch(e:list<i64>){task_yield();return e[0];}}'),
 ('return-replaced','fn work()->i64 !{task,throw}{try{return 0;}finally{task_yield();throw([42]);}}fn main()->i64 !{task}{try{return work();}catch(e:list<i64>){task_yield();return e[0];}catch(c,m){return 0;}}'),
 ('result-replaced','fn work()->result<i64> !{task,throw}{try{let x:i64=err<i64>("E","hidden")?;return ok(x);}finally{task_yield();throw(42);}}fn main()->i64 !{task}{try{work();return 0;}catch(e:i64){return e;}catch(c,m){return 0;}}'),
 ('nested-finalizer-packet','fn main()->i64 !{task,io}{try{try{throw([42]);}finally{task_yield();try{throw("cleanup");}catch(e:str){task_yield();print(e);}}}catch(e:list<i64>){return e[0];}}'),
 ('repeat-future','fn main()->i64 !{task,throw}{return with_tasks(2,fn(s:task_scope)->i64 !{task,throw}{let child:task<i64>=task_spawn(s,fn()->i64 !{task,throw}{task_yield();throw([21]);});var sum:i64=0;var n:i64=0;while n<2{try{task_wait(child);}catch(e:list<i64>){task_yield();sum=sum+e[0];}n=n+1;}return sum;});}'),
 ('scope-close','fn main()->i64 !{task}{try{return with_tasks(2,fn(s:task_scope)->i64 !{task}{task_spawn(s,fn()->i64 !{task,throw}{task_yield();throw([42]);});return 0;});}catch(e:list<i64>){return e[0];}catch(c,m){return 0;}}'),
 ('heap-loop','fn main()->i64 !{task}{var n:i64=0;while n<200{try{task_yield();throw(["owned",str(n)]);}catch(e:list<str>) if false{assert(false);}catch(e:list<str>){task_yield();assert(e[0]=="owned");}n=n+1;}return 42;}'),
 ('parallel','struct Left{value:i64;}struct Right{value:i64;}fn main()->i64 !{task,throw}{return with_tasks(2,fn(s:task_scope)->i64 !{task,throw}{let a:task<i64>=task_spawn(s,fn()->i64 !{throw}{throw(Left(42));});let b:task<i64>=task_spawn(s,fn()->i64 !{throw}{throw(Right(43));});var sum:i64=0;try{task_wait(a);}catch(e:Left){sum=e.value;}try{task_wait(b);}catch(e:Right){assert(e.value==43);}return sum;});}'),
 ('uncaught','fn original()->unit !{task,throw}{task_yield();throw(["hidden payload"]);}fn main()->unit !{task,throw}{try{try{original();}catch(e:list<str>){task_yield();throw;}}finally{task_yield();}}'),
 ('fatal','fn main()->i64 !{task}{try{task_yield();return 9223372036854775807+1;}catch(e:i64){return 0;}catch(c,m){return 0;}}'),
]
# Build the same ordinary functional native host used by existing exception-task
# tests, with independently tracked Data/Handle retirement and real worker overlap.
tree=ast.parse((root/'tests/source_exception_task_native.py').read_text())
host_node=next(n for n in tree.body if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Attribute) and isinstance(n.value.func.value,ast.Name) and n.value.func.value.id=='host' and n.value.func.attr=='write_text')
host_text=ast.literal_eval(host_node.value.args[0]).replace('"SYNC_A"','"Left"').replace('"SYNC_B"','"Right"')
# Exercise real cross-cohort call and typed-helper rejection before starting the
# two-worker overlap run, without changing a descriptor already in use.
host_text=host_text.replace('bool publicRejected=false;',r'''{
    nexrt::RequestScope boundary(1000,1000);auto legacy=*address();legacy.abi=nexrt::taskCodeSourceExceptionABI;
    nexrt::NativeTaskFrame caller(legacy,{},{});bool rejected=false;
    try{nex_task_frame_call_at(&caller,const_cast<nexrt::TaskCodeDescriptor*>(address()),nullptr,nullptr,-1,0,nullptr);}
    catch(const nexrt::Trap &e){rejected=e.code=="E_TASK_STATE";}
    if(!rejected||caller.pendingCall)throw std::runtime_error("mixed typed/public task cohorts were accepted");
  }{
    nexrt::RequestScope boundary(1000,1000);auto legacy=*address();legacy.abi=nexrt::taskCodeSourceExceptionABI;
    nexrt::NativeTaskFrame caller(legacy,{},{});caller.pendingSource=std::make_shared<const nexrt::NativeSourceException>("legacy","value","",1);bool rejected=false;
    try{nex_task_frame_source_enter_at(&caller,nullptr);}catch(const nexrt::Trap &e){rejected=e.code=="E_TASK_STATE";}
    if(!rejected||!caller.pendingSource||!caller.caughtSource.empty())throw std::runtime_error("typed helper accepted a legacy frame or changed it on rejection");
  }bool publicRejected=false;''')

objects=[]
for name in ['runtime.cpp','nex_files.cpp','nex_task_frame.cpp','nex_task_external.cpp','nex_resource_region.cpp','nex_external_resource.cpp','nex_resource_executor.cpp','nex_task_application.cpp']:
 obj=out/(name+'.o');run('compile-'+name,[compiler,'-std=c++20','-O1','-g','-fPIC','-DNEX_PROFILE_ENABLED','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS','-I'+str(runtime),'-c',runtime/name,'-o',obj]);objects.append(obj)
host=out/'host.cpp';host.write_text(host_text);host_binary=out/'host';export='-Wl,-export_dynamic' if platform.system()=='Darwin' else '-Wl,--export-dynamic'
run('link-host',[compiler,'-std=c++20','-O1','-g','-DNEX_PROFILE_ENABLED','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS','-I'+str(runtime),host,*objects,export,'-pthread',*(['-ldl'] if platform.system()!='Darwin' else []),'-o',host_binary])
run('target',[compiler,'-x','c','-S','-emit-llvm','/dev/null','-o',out/'target.ll']);text=(out/'target.ll').read_text();triple=re.search(r'target triple = "([^"]+)"',text)[1];layout=re.search(r'target datalayout = "([^"]+)"',text)[1]
node=os.environ.get('NEX_NODE','node');programs=[]
runner=r"""import * as program from './program.ts';
import * as nex from './nex-runtime.ts';import * as task from './nex-task-runtime.ts';import * as sourceException from './nex-source-exception-runtime.ts';
const logs=[];console.log=v=>logs.push(String(v));let actual;
try{const value=await task.runSourceErrors(task.call(()=>program.main()),e=>sourceException.details(e)!==undefined);actual={kind:'return',value:typeof value==='bigint'?Number(value):value??null};}
catch(error){const detail=sourceException.details(error);if(detail)actual={kind:'exception',code:detail.code,message:detail.message,line:detail.site[1]};else if(error instanceof nex.NexError)actual={kind:'trap',code:error.code};else throw error;}
process.stdout.write(JSON.stringify({...actual,output:logs.join('\n')+(logs.length?'\n':'')})+'\n');
"""
for name,text in cases:
 d=out/name;d.mkdir();source=d/'main.nex';source.write_text('module typed_tasks;\n'+text)
 expected=json.loads(run(name+'-ast',[probe,'ast',source]).stdout);actual_ir=json.loads(run(name+'-ir',[probe,'ir',source]).stdout);assert actual_ir==expected,(name,expected,actual_ir)
 assert expected['kind']==('exception' if name=='uncaught' else 'trap' if name.startswith('fatal') else 'return'),(name,expected)
 if expected['kind']=='return':assert expected['value']==42,(name,expected)
 if name.startswith('fatal'):assert expected['code']==('E_ASSERT' if name=='fatal-filter' else 'E_OVERFLOW'),(name,expected)
 for opt in ['0','2']:
  o=d/('O'+opt);o.mkdir();run(name+'-emit'+opt,[probe,'emit',source,o,triple,layout,str(opt=='2').lower()]);lib=o/('program.dylib' if platform.system()=='Darwin' else 'program.so')
  flags=['-dynamiclib','-undefined','dynamic_lookup'] if platform.system()=='Darwin' else ['-shared','-fPIC'];run(name+'-link'+opt,[compiler,'-O'+opt,*flags,o/'program.ll','-o',lib])
  for workers in [1,4]:
   r=run(name+'-run'+opt+'-'+str(workers),[host_binary,lib,'workers',str(workers)],allowed=(0,42,70))
   if expected['kind']=='return':assert r.returncode==42 and r.stdout==expected['output'] and not r.stderr,(name,workers,r.returncode,r.stdout,r.stderr)
   elif expected['kind']=='exception':
    row=next(json.loads(line.split(' ',1)[1]) for line in r.stderr.splitlines() if line.startswith('NEX_SOURCE_EXCEPTION '));assert r.returncode==70 and 'hidden payload' not in r.stderr
    for key in ['code','message','line']:assert row[key]==expected[key],(name,key,row,expected)
   else:assert r.returncode==70 and expected['code'] in r.stderr and 'NEX_SOURCE_EXCEPTION' not in r.stderr,(name,r.stderr,expected)
   records.append({'name':name,'optimization':'O'+opt,'workers':workers,'native':True,'passed':True});save()
  if name=='parallel':
   descriptor=json.loads((o/'descriptor.json').read_text());r=run(name+'-overlap'+opt,[host_binary,lib,'observe',descriptor['symbol']],allowed=(42,));assert '"distinct_workers":2' in r.stderr and '"public_entry_rejected":true' in r.stderr
 run(name+'-typescript',[probe,'typescript',source,d]);mapping=json.loads((d/'nex-map.json').read_text());assert mapping['execution']=='task-generator' and mapping['public_revision'] is False and mapping['schema']=='nex.development-typescript/027-2'
 (d/'run.mjs').write_text(runner);actual=json.loads(run(name+'-node',[node,'--experimental-strip-types','--no-warnings',d/'run.mjs']).stdout)
 for key in ['kind','value','code','message','line','output']:
  if key in expected:assert actual[key]==expected[key],(name,key,expected,actual)
 programs.extend(d.glob('*.ts'))
# Authority-bearing payloads remain rejected until their ownership transfer proof
# is implemented; an unrelated typed catch must not conceal an escaping channel.
rejections=[
 ('payload-authority','fn main()->unit !{task,throw}{with_tasks(1,fn(s:task_scope)->unit !{task,throw}{throw(channel_new<i64>(s,1));});}','E_TYPED_EXCEPTION_AUTHORITY'),
 ('handler-assignment','fn main()->unit !{task,throw}{with_tasks(1,fn(outer:task_scope)->unit !{task,throw}{let leaked:channel<i64>=with_tasks(1,fn(inner:task_scope)->channel<i64> !{task}{var value:channel<i64>=channel_new<i64>(outer,1);try{value=channel_new<i64>(inner,1);throw(42);}catch(e:i64){task_yield();}return value;});});}','E_TASK_LIFETIME'),
]
for name,text,code in rejections:
 f=out/(name+'.nex');f.write_text('module rejected;\n'+text);r=run(name,[probe,'check',f],allowed=(1,));assert code in r.stderr,(name,r.stderr)
tsc=Path(os.environ['NEX_TSC']);pin=json.loads((root/'web/package.json').read_text())['devDependencies']['typescript'];assert json.loads((tsc.parent.parent/'package.json').read_text())['version']==pin
run('strict-typescript',[node,tsc,'--noEmit','--strict','--target','ES2022','--module','ESNext','--moduleResolution','bundler','--allowImportingTsExtensions','--lib','ES2022,DOM',*programs])
report.update(ok=True,programs=len(cases),native_comparisons=len(records),AST_TaskIR_Node_comparisons=len(cases),actual_native_worker_overlap_runs=2,physical_Data_and_Handle_retirement=True,strict_TypeScript=True,rejected_programs=len(rejections),typescript_version=pin);save()
print(json.dumps({k:report[k] for k in ['ok','programs','native_comparisons','AST_TaskIR_Node_comparisons','actual_native_worker_overlap_runs','physical_Data_and_Handle_retirement','strict_TypeScript','rejected_programs']}))
if not a.output:shutil.rmtree(out)
