#!/usr/bin/env python3
"""Candidate027 AST/TaskIR/native O0/O2/Node agreement across real task pauses."""
import argparse,ast,hashlib,json,os,platform,re,shutil,subprocess,tempfile,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('probe');p.add_argument('--compiler',required=True);p.add_argument('--crypto-library');p.add_argument('--crypto-include');p.add_argument('--output',type=Path);a=p.parse_args()
root=Path(__file__).resolve().parents[1];runtime=root/'runtime';probe=str(Path(a.probe).resolve());compiler=a.compiler
out=a.output.resolve() if a.output else Path(tempfile.mkdtemp(prefix='nex-typed-source-tasks-'));out.mkdir(parents=True,exist_ok=a.output is None)
started=time.monotonic();records=[];report={'ok':False,'candidate_language':'0.27','public027_enabled':False,'descriptor_abi':'0x4e45585400002702','cases':records,'commands':[]}
def save():report['seconds']=round(time.monotonic()-started,3);(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
def run(label,cmd,allowed=(0,),timeout=180):
 r=subprocess.run(list(map(str,cmd)),text=True,capture_output=True,timeout=timeout,env={**os.environ,'NEX_RESOURCE_DIR':str(root),'NEX_FILES_ROOT':str(out),'NEX_TYPED_HOST_CATALOG':str(out/'host.json') if label.startswith('native-resource-') else '', 'NEX_PRIVATE_HOST_EVENTS':str(out/(label+'.events'))})
 (out/(label+'.stdout')).write_text(r.stdout);(out/(label+'.stderr')).write_text(r.stderr)
 report['commands'].append({'label':label,'exit_code':r.returncode});save()
 assert r.returncode in allowed,(label,r.returncode,r.stdout[-2000:],r.stderr[-5000:],str(out))
 if label.startswith('native-resource-') and re.search(r'-(ast|ir|run[02]-[14])$',label):
  events=(out/(label+'.events')).read_text();assert events.count('F')>0 and events.count('F')==events.count('X'),(label,events)
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
cases += [
 ('authority-local-channel','fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{try{throw(channel_new<i64>(s,1));}catch(q:channel<i64>){task_yield();assert(task_send(q,42));return unwrap(task_recv(q));}});}'),
 ('authority-ancestor-channel','fn main()->i64 !{task,throw}{return with_tasks(1,fn(outer:task_scope)->i64 !{task,throw}{let q:channel<i64>=channel_new<i64>(outer,1);try{with_tasks(1,fn(inner:task_scope)->unit !{throw}{throw(q);});}catch(e:channel<i64>){assert(task_send(e,42));return unwrap(task_recv(e));}catch(c,m){return 0;}return 0;});}'),
 ('authority-scope','fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{try{throw(s);}catch(owner:task_scope){let q:channel<i64>=channel_new<i64>(owner,1);assert(task_send(q,42));return unwrap(task_recv(q));}});}'),
 ('authority-closure','fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let q:channel<i64>=channel_new<i64>(s,1);try{throw(fn()->i64 !{task}{assert(task_send(q,42));return unwrap(task_recv(q));});}catch(f:fn()->i64 !{task}){task_yield();return f();}});}'),
 ('authority-future','fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task,throw}{let value:task<i64>=task_spawn(s,fn()->i64{return 42;});try{throw(value);}catch(e:task<i64>){task_yield();return task_wait(e);}});}'),
 ('authority-repeated-future','fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task,throw}{let q:channel<i64>=channel_new<i64>(s,2);let child:task<i64>=task_spawn(s,fn()->i64 !{task,throw}{task_yield();throw(q);});var n:i64=0;while n<2{try{task_wait(child);}catch(e:channel<i64>){assert(e==q);assert(task_send(e,21));n=n+1;}}return unwrap(task_recv(q))+unwrap(task_recv(q));});}'),
 ('authority-implicit-ancestor','fn main()->i64 !{task,throw}{return with_tasks(1,fn(outer:task_scope)->i64 !{task,throw}{let q:channel<i64>=channel_new<i64>(outer,1);try{with_tasks(1,fn(inner:task_scope)->unit !{task}{task_spawn(inner,fn()->unit !{task,throw}{task_yield();throw(q);});});}catch(e:channel<i64>){assert(e==q);assert(task_send(e,42));return unwrap(task_recv(e));}catch(c,m){return 0;}return 0;});}'),
 ('authority-nested-aggregate','struct Problem{value:list<result<channel<i64>>>;}fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let q:channel<i64>=channel_new<i64>(s,1);try{throw(Problem([ok(q)]));}catch(e:Problem){task_yield();let retained:channel<i64>=unwrap(e.value[0]);assert(retained==q);assert(task_send(retained,42));return unwrap(task_recv(q));}});}'),
 ('authority-finally-replacement','fn main()->i64 !{task,throw}{try{return with_tasks(1,fn(s:task_scope)->i64 !{task,throw}{try{throw(channel_new<i64>(s,1));}finally{task_yield();throw(42);}});}catch(e:i64){return e;}catch(c,m){return 0;}}'),
 ('authority-projection','struct Pair{outer:channel<i64>;inner:channel<i64>;}fn main()->i64 !{task,throw}{return with_tasks(1,fn(outer:task_scope)->i64 !{task,throw}{let safe:channel<i64>=channel_new<i64>(outer,1);let selected:channel<i64>=with_tasks(1,fn(inner:task_scope)->channel<i64> !{task}{try{throw(Pair(safe,channel_new<i64>(inner,1)));}catch(e:Pair){task_yield();return e.outer;}});assert(selected==safe);assert(task_send(selected,42));return unwrap(task_recv(safe));});}'),
 ('authority-runtime-channel','fn main()->i64 !{task,throw}{try{return with_tasks(1,fn(s:task_scope)->i64 !{task,throw}{let pipe:channel<channel<i64>>=channel_new<channel<i64>>(s,1);assert(task_send(pipe,channel_new<i64>(s,1)));throw(unwrap(task_recv(pipe)));});}catch(q:channel<i64>){return 0;}catch(c,m){return 0;}}'),
 ('authority-runtime-scope','fn main()->i64 !{task,throw}{try{return with_tasks(1,fn(s:task_scope)->i64 !{task,throw}{let pipe:channel<task_scope>=channel_new<task_scope>(s,1);assert(task_send(pipe,s));throw(unwrap(task_recv(pipe)));});}catch(q:task_scope){return 0;}catch(c,m){return 0;}}'),
 ('authority-runtime-implicit','fn main()->i64 !{task,throw}{try{return with_tasks(1,fn(s:task_scope)->i64 !{task}{task_spawn(s,fn()->unit !{task,throw}{let pipe:channel<channel<i64>>=channel_new<channel<i64>>(s,1);assert(task_send(pipe,channel_new<i64>(s,1)));throw(unwrap(task_recv(pipe)));});return 0;});}catch(q:channel<i64>){return 0;}catch(c,m){return 0;}}'),
 ('native-file-owned','server fn main()->i64 !{task,fs,throw}{try{with_tasks(1,server fn(s:task_scope)->unit !{task,fs,throw}{let f:file=unwrap(file_open_read("input"));throw(f);});}catch(f:file){assert(len(unwrap(file_read(f,1)))==1);assert(file_close(f));return 42;}catch(c,m){return 0;}return 0;}'),
 ('native-file-unobserved','server fn main()->i64 !{task,fs,throw}{try{with_tasks(1,server fn(s:task_scope)->unit !{task,fs}{task_spawn(s,server fn()->unit !{task,fs,throw}{let f:file=unwrap(file_open_read("input"));throw(f);});});}catch(f:file){assert(len(unwrap(file_read(f,1)))==1);assert(file_close(f));return 42;}catch(c,m){return 0;}return 0;}'),
 ('native-file-alias','struct Problem{first:file;second:file;}server fn main()->i64 !{task,fs,throw}{try{with_tasks(1,server fn(s:task_scope)->unit !{task,fs,throw}{let f:file=unwrap(file_open_read("input"));throw(Problem(f,f));});}catch(e:Problem){assert(file_is_open(e.first));assert(file_close(e.first));assert(!file_is_open(e.second));return 42;}catch(c,m){return 0;}return 0;}'),
]
(out/'input').write_bytes(b'abc')
# Build the same ordinary functional native host used by existing exception-task
# tests, with independently tracked Data/Handle retirement and real worker overlap.
tree=ast.parse((root/'tests/source_exception_task_native.py').read_text())
host_node=next(n for n in tree.body if isinstance(n,ast.Expr) and isinstance(n.value,ast.Call) and isinstance(n.value.func,ast.Attribute) and isinstance(n.value.func.value,ast.Name) and n.value.func.value.id=='host' and n.value.func.attr=='write_text')
host_text=ast.literal_eval(host_node.value.args[0]).replace('"SYNC_A"','"Left"').replace('"SYNC_B"','"Right"')
host_text=host_text.replace('status=entry(3,arguments);','const char *catalog=std::getenv("NEX_TYPED_HOST_CATALOG");const char *foreignArguments[]={"nex-private-task","--nex-task-workers",selected,"--nex-foreign",catalog};status=entry(catalog&&*catalog?5:3,catalog&&*catalog?foreignArguments:arguments);')
# Exercise real cross-cohort call and typed-helper rejection before starting the
# two-worker overlap run, without changing a descriptor already in use.
host_text=host_text.replace('bool publicRejected=false;',r'''for(auto retainedABI:{nexrt::taskCodeSourceExceptionABI,nexrt::taskCodeTypedErrorDevelopmentABI}){
    nexrt::RequestScope boundary(1000,1000);auto legacy=*address();legacy.abi=retainedABI;
    nexrt::NativeTaskFrame caller(legacy,{},{});bool rejected=false;
    try{nex_task_frame_call_at(&caller,const_cast<nexrt::TaskCodeDescriptor*>(address()),nullptr,nullptr,-1,0,nullptr);}
    catch(const nexrt::Trap &e){rejected=e.code=="E_TASK_STATE";}
    if(!rejected||caller.pendingCall)throw std::runtime_error("new authority cohort accepted a retained task call");
  }{
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

crypto=[a.crypto_library] if a.crypto_library else ([str(Path('/opt/homebrew/opt/openssl@3/lib/libcrypto.dylib'))] if platform.system()=='Darwin' else ['-lcrypto'])
include=a.crypto_include or ('/opt/homebrew/opt/openssl@3/include' if platform.system()=='Darwin' else None)
flags=['-DNEX_PROFILE_ENABLED','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS','-DNEX_FOREIGN_ENABLED','-I'+str(runtime),*(['-I'+include] if include else [])]
objects=[]
for name in ['runtime.cpp','nex_files.cpp','files_runtime.cpp','nex_task_frame.cpp','nex_task_external.cpp','nex_resource_region.cpp','nex_external_resource.cpp','nex_resource_executor.cpp','nex_task_application.cpp','foreign_runtime.cpp','nex_foreign.cpp','nex_ffi_loader.cpp','nex_ffi.cpp','nex_ffi_types.cpp','nex_ffi_resources.cpp','nex_json.cpp']:
 obj=out/(name+'.o');run('compile-'+name,[compiler,'-std=c++20','-O1','-g','-fPIC',*flags,'-c',runtime/name,'-o',obj]);objects.append(obj)
host=out/'host.cpp';host.write_text(host_text);host_binary=out/'host';export='-Wl,-export_dynamic' if platform.system()=='Darwin' else '-Wl,--export-dynamic'
run('link-host',[compiler,'-std=c++20','-O1','-g',*flags,host,*objects,*crypto,export,'-pthread',*(['-ldl'] if platform.system()!='Darwin' else []),'-o',host_binary])
run('target',[compiler,'-x','c','-S','-emit-llvm','/dev/null','-o',out/'target.ll']);text=(out/'target.ll').read_text();triple=re.search(r'target triple = "([^"]+)"',text)[1];layout=re.search(r'target datalayout = "([^"]+)"',text)[1]
# A real pinned C FFI producer constructs opaque resources; source programs
# exercise their error paths with both independent engines and native workers.
tree=ast.parse((root/'tests/source_exception_host.py').read_text())
literal=lambda name:ast.literal_eval(next(n.value for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(v,ast.Name) and v.id==name for v in n.targets)))
declarations=literal('DECLARATIONS');module=literal('MODULE')
signature=out/'signature.nex';signature.write_text('module typed_tasks;\n'+declarations.replace('@PIN@','0'*64)+'server fn main()->i64 !{task}{return 42;}')
signatures=json.loads(run('resource-signatures',[probe,'signatures',signature]).stdout)
bundle=out/'bundle';bundle.mkdir();exports=[]
for name,operation in [('create',1),('read',2),('add',3),('ordinary',4),('bad',5)]:
 digest=hashlib.sha256(json.dumps(signatures[name],ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest();exports.append('{sizeof(nex_ffi_export_v1),0,'+json.dumps(name)+','+json.dumps(digest)+',callback,(void*)'+str(operation)+'}')
producer=out/'module.c';producer.write_text(module.replace('EXPORTS',','.join(exports)))
run('resource-module',[compiler,'-x','c','-std=c11','-shared','-fPIC','-fvisibility=hidden','-I'+str(runtime),producer,'-o',bundle/'module'])
(bundle/'NOTICE').write_text('NEX typed error authority conformance fixture\n')
sha=lambda file:hashlib.sha256(file.read_bytes()).hexdigest()
manifest={'schema':'nex.foreign-bundle/1','platform':('macos' if platform.system()=='Darwin' else 'linux')+'-'+({'arm64':'arm64','aarch64':'arm64','x86_64':'x86_64'}[platform.machine()]),'entry':'module','files':[{'path':name,'sha256':sha(bundle/name)} for name in ['module','NOTICE']],'exports':{name:hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest() for name,value in signatures.items()},'notices':['NOTICE']}
(bundle/'manifest.json').write_text(json.dumps(manifest)+'\n');pin=sha(bundle/'manifest.json')
(out/'host.json').write_text(json.dumps({'schema':'nex.foreign-host/1','module_limit':2,'resource_limit':4,'resource_bytes':32,'libraries':{'host':{'directory':str(bundle),'manifest_sha256':pin,'exports':list(signatures)}}})+'\n')
resource_cases=[
 ('owned','server fn main()->i64 !{task,ffi,throw}{try{with_tasks(1,server fn(s:task_scope)->unit !{task,ffi,throw}{throw(create(42));});}catch(e:Counter){task_yield();assert(read(e)==42);assert(resource_close(e));return 42;}catch(c,m){return 0;}return 0;}'),
 ('unobserved','server fn main()->i64 !{task,ffi,throw}{try{with_tasks(1,server fn(s:task_scope)->unit !{task,ffi}{task_spawn(s,server fn()->unit !{task,ffi,throw}{task_yield();throw(create(42));});});}catch(e:Counter){assert(read(e)==42);assert(resource_close(e));return 42;}catch(c,m){return 0;}return 0;}'),
 ('aliased','struct Problem{first:Counter;second:Counter;}server fn main()->i64 !{task,ffi,throw}{try{with_tasks(1,server fn(s:task_scope)->unit !{task,ffi,throw}{let resource:Counter=create(42);throw(Problem(resource,resource));});}catch(e:Problem){assert(read(e.first)==42);assert(resource_close(e.first));assert(!resource_is_open(e.second));return 42;}catch(c,m){return 0;}return 0;}'),
 ('mixed-file','struct Problem{resource:Counter;file:file;}server fn main()->i64 !{task,ffi,fs,throw}{try{with_tasks(1,server fn(s:task_scope)->unit !{task,ffi,fs,throw}{throw(Problem(create(42),unwrap(file_open_read("input"))));});}catch(e:Problem){assert(read(e.resource)==42);assert(len(unwrap(file_read(e.file,1)))==1);assert(resource_close(e.resource));assert(file_close(e.file));return 42;}catch(c,m){return 0;}return 0;}'),
 ('runtime-mixed','struct Problem{resource:Counter;channel:channel<i64>;file:file;}server fn main()->i64 !{task,ffi,fs,throw}{try{return with_tasks(1,server fn(s:task_scope)->i64 !{task,ffi,fs,throw}{let q:channel<channel<i64>>=channel_new<channel<i64>>(s,1);assert(task_send(q,channel_new<i64>(s,1)));throw(Problem(create(42),unwrap(task_recv(q)),unwrap(file_open_read("input"))));});}catch(e:Problem){return 0;}catch(c,m){return 0;}}'),
]
cases += [('native-resource-'+name,declarations.replace('@PIN@',pin)+text) for name,text in resource_cases]
node=os.environ.get('NEX_NODE','node');programs=[];node_comparisons=0
runner=r"""import * as program from './program.ts';
import * as nex from './nex-runtime.ts';import * as task from './nex-task-runtime.ts';import * as sourceException from './nex-source-exception-runtime.ts';
const logs=[];console.log=v=>logs.push(String(v));let actual;
try{const value=await task.runTypedSourceErrors(task.call(()=>program.main()),program.sourceErrorContracts);actual={kind:'return',value:typeof value==='bigint'?Number(value):value??null};}
catch(error){const detail=sourceException.details(error);if(detail)actual={kind:'exception',code:detail.code,message:detail.message,line:detail.site[1]};else if(error instanceof nex.NexError)actual={kind:'trap',code:error.code};else throw error;}
process.stdout.write(JSON.stringify({...actual,output:logs.join('\n')+(logs.length?'\n':'')})+'\n');
"""
for name,text in cases:
 d=out/name;d.mkdir();source=d/'main.nex';source.write_text('module typed_tasks;\n'+text)
 expected=json.loads(run(name+'-ast',[probe,'ast',source]).stdout);actual_ir=json.loads(run(name+'-ir',[probe,'ir',source]).stdout);assert actual_ir==expected,(name,expected,actual_ir)
 assert expected['kind']==('exception' if name=='uncaught' else 'trap' if name.startswith(('fatal','authority-runtime-','native-resource-runtime-')) else 'return'),(name,expected)
 if expected['kind']=='return':assert expected['value']==42,(name,expected)
 if name.startswith('fatal'):assert expected['code']==('E_ASSERT' if name=='fatal-filter' else 'E_OVERFLOW'),(name,expected)
 if name.startswith(('authority-runtime-','native-resource-runtime-')):assert expected['code']=='E_TASK_SCOPE',(name,expected)
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
 if name.startswith(('native-file-','native-resource-')):
  r=run(name+'-typescript-realm',[probe,'typescript',source,d],allowed=(1,));assert 'E_REALM' in r.stderr and not (d/'program.ts').exists();continue
 run(name+'-typescript',[probe,'typescript',source,d]);mapping=json.loads((d/'nex-map.json').read_text());assert mapping['execution']=='task-generator' and mapping['public_revision'] is False and mapping['schema']=='nex.development-typescript/027-3'
 (d/'run.mjs').write_text(runner);actual=json.loads(run(name+'-node',[node,'--experimental-strip-types','--no-warnings',d/'run.mjs']).stdout)
 for key in ['kind','value','code','message','line','output']:
  if key in expected:assert actual[key]==expected[key],(name,key,expected,actual)
 programs.extend(d.glob('*.ts'))
 node_comparisons+=1
# Statically known escapes must be rejected; channel-mediated unknown provenance
# above must instead reach the real runtime guard without a checker bypass.
rejections=[
 ('payload-authority','fn main()->unit !{task,throw}{with_tasks(1,fn(s:task_scope)->unit !{task,throw}{throw(channel_new<i64>(s,1));});}','E_TASK_LIFETIME'),
 ('handler-assignment','fn main()->unit !{task,throw}{with_tasks(1,fn(outer:task_scope)->unit !{task,throw}{let leaked:channel<i64>=with_tasks(1,fn(inner:task_scope)->channel<i64> !{task}{var value:channel<i64>=channel_new<i64>(outer,1);try{value=channel_new<i64>(inner,1);throw(42);}catch(e:i64){task_yield();}return value;});});}','E_TASK_LIFETIME'),
]
for name,text,code in rejections:
 f=out/(name+'.nex');f.write_text('module rejected;\n'+text);r=run(name,[probe,'check',f],allowed=(1,));assert code in r.stderr,(name,r.stderr)
tsc=Path(os.environ['NEX_TSC']);pin=json.loads((root/'web/package.json').read_text())['devDependencies']['typescript'];assert json.loads((tsc.parent.parent/'package.json').read_text())['version']==pin
run('strict-typescript',[node,tsc,'--noEmit','--strict','--target','ES2022','--module','ESNext','--moduleResolution','bundler','--allowImportingTsExtensions','--lib','ES2022,DOM',*programs])
report.update(ok=True,programs=len(cases),native_comparisons=len(records),AST_TaskIR_comparisons=len(cases),AST_TaskIR_Node_comparisons=node_comparisons,actual_native_worker_overlap_runs=2,physical_Data_and_Handle_retirement=True,strict_TypeScript=True,rejected_programs=len(rejections),typescript_version=pin);save()
print(json.dumps({k:report[k] for k in ['ok','programs','native_comparisons','AST_TaskIR_Node_comparisons','actual_native_worker_overlap_runs','physical_Data_and_Handle_retirement','strict_TypeScript','rejected_programs']}))
if not a.output:shutil.rmtree(out)
