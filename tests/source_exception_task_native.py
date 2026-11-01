"""Real private native task continuations at O0/O2, AST comparison and physical worker overlap."""
from host_fixture import run_native, host_cpp, probe_dll_inputs
import os
import argparse, ast, hashlib, json, os, platform, re, subprocess, tempfile
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('emitter');p.add_argument('reference');p.add_argument('compiler');p.add_argument('--output');p.add_argument('--case',action='append');p.add_argument('--profile',action='store_true');p.add_argument('--debug',action='store_true');a=p.parse_args();assert not(a.profile and a.debug)
source=Path(__file__).resolve().parents[1];runtime=source/'runtime'
out=Path(a.output or os.environ.get('NEX_EXCEPTION_TASK_NATIVE_OUTPUT') or tempfile.mkdtemp(prefix='nex-native-task-exceptions-')).resolve();out.mkdir(parents=True,exist_ok=True)
emitter=str(Path(a.emitter).resolve());reference=str(Path(a.reference).resolve());compiler=a.compiler
report={'ok':False,'cases':[],'stage_rejections':[],'parallel_runs':[],'ordinary_functional_only':True,'security_checks_deferred_by_user':True,'public_language':'0.24','private_identity':'0.25-prototype','compiled_native_task_execution':True,'public_build_support':False,'installed_SDK_acceptance_claimed':False,'commands':[]}
def save(): (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n', newline="\n")
def run(label,cmd,allowed=(0,),**kw):
    r=run_native(list(map(str,cmd)),text=True,capture_output=True,timeout=180,**kw)
    (out/(label+'.stdout')).write_text(r.stdout, newline="\n");(out/(label+'.stderr')).write_text(r.stderr, newline="\n")
    report['commands'].append({'label':label,'argv':list(map(str,cmd)),'exit_code':r.returncode});save()
    assert r.returncode in allowed,(label,r.returncode,r.stdout[-1000:],r.stderr[-4000:]);return r
save();run('target',[compiler,'-x','c','-S','-emit-llvm',os.devnull,'-o',out/'target.ll'])
target=(out/'target.ll').read_text();triple=re.search(r'target triple = "([^"]+)"',target)[1];layout=re.search(r'target datalayout = "([^"]+)"',target)[1]
objects=[];extra_flags=[]
runtime_names=['runtime.cpp','nex_files.cpp','nex_task_frame.cpp','nex_task_external.cpp','nex_resource_region.cpp','nex_external_resource.cpp','nex_resource_executor.cpp','nex_task_application.cpp']
if a.profile:
    runtime_names += ['nex_task_profile.cpp','nex_profile.cpp','third_party/tracy/public/TracyClient.cpp']
    extra_flags=['-DNEX_SOURCE_PROFILE_REAL','-DNEX_TASK_PROFILE_ENABLED',*['-D'+name for name in ['TRACY_ENABLE','TRACY_ON_DEMAND','TRACY_DELAYED_INIT','TRACY_MANUAL_LIFETIME','TRACY_ONLY_LOCALHOST','TRACY_NO_BROADCAST','TRACY_NO_CODE_TRANSFER','TRACY_NO_CALLSTACK','TRACY_NO_SYSTEM_TRACING','TRACY_NO_SAMPLING','TRACY_NO_CRASH_HANDLER','TRACY_NO_FRAME_IMAGE']]]
if a.debug:
    runtime_names += ['nex_task_debug.cpp'];extra_flags=['-DNEX_SOURCE_DEBUG_REAL','-DNEX_TASK_DEBUG_ENABLED','-I'+str(source/'tests')]
for name in runtime_names:
    obj=out/(Path(name).name+'.o');run('compile-'+name.replace('/','_'),[compiler,'-std=c++20','-O1','-g','-fPIC','-DNEX_PROFILE_ENABLED','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS',*extra_flags,'-I'+str(runtime),'-c',runtime/name,'-o',obj]);objects.append(obj)
host=out/'host.cpp';host.write_text(r'''
#include "nex_task_application.h"
#ifdef _WIN32
#include "host_dlfcn.h"
#else
#include <dlfcn.h>
#endif
#include <cstdio>
#include <mutex>
#include <map>
#include <condition_variable>
#include <set>
#include <thread>
#include <chrono>
#ifdef NEX_SOURCE_DEBUG_REAL
#include "source_exception_debug_host.h"
#endif
static std::mutex mutex;
static std::condition_variable changed;
static std::set<std::thread::id> workers;
static unsigned arrivals=0;
static std::mutex allocationsMutex;
static std::map<const void*,int> allocations;
#ifndef NEX_SOURCE_PROFILE_REAL
extern "C" void nex_profile_unwind(){}
extern "C" void nex_profile_allocation(const void *p,size_t,int pool){std::lock_guard lock(allocationsMutex);if(!allocations.emplace(p,pool).second)std::abort();}
extern "C" void nex_profile_free(const void *p){std::lock_guard lock(allocationsMutex);if(allocations.erase(p)!=1)std::abort();}
#else
extern "C" const char *nex_profile_build_info(){return "{\"schema\":\"nex.private-source-profile-build/1\",\"language\":\"0.25-prototype\",\"archived\":false,\"descriptor_abi\":\"0x4e45585400002501\"}";}
#endif
static void observe(const nexrt::NativeTaskFrame &frame,int64_t transition){
  if(transition!=4||!frame.pendingSource||(frame.pendingSource->code!="SYNC_A"&&frame.pendingSource->code!="SYNC_B"))return;
  std::unique_lock lock(mutex);workers.insert(std::this_thread::get_id());++arrivals;changed.notify_all();
  if(!changed.wait_for(lock,std::chrono::seconds(8),[]{return arrivals==2;}))throw nexrt::DataError("E_TEST","two native source-error steps did not overlap");
}
static nexrt::TaskBody root(nexrt::TaskGroup &group,nexrt::Value,nexrt::Value,const void *code){
  return nexrt::executeTaskFrame(group,nexrt::NativeTaskFrame(*static_cast<const nexrt::TaskCodeDescriptor*>(code),{},{}),observe);
}
int main(int argc,char **argv){try{
  if(argc<2)throw std::runtime_error("missing shared program");auto baseline=nexrt::liveObjects.load();
  void *library=dlopen(argv[1],RTLD_NOW|RTLD_LOCAL);if(!library)throw std::runtime_error(dlerror());
  int status=0;
  if(argc==4&&std::string(argv[2])=="observe"){
    auto address=reinterpret_cast<const nexrt::TaskCodeDescriptor*(*)()>(dlsym(library,argv[3]));if(!address)throw std::runtime_error(dlerror());
    bool publicRejected=false;{nexrt::RequestScope boundary(1000,1000);try{nexrt::executeTaskApplication(*address(),nexrt::TaskExecutionLimits{},{});}catch(const nexrt::Trap &e){publicRejected=e.code=="E_TASK_STATE";}if(!nexrt::inRequestScope())throw std::runtime_error("public rejection replaced its host request");}
    if(!publicRejected||nexrt::inRequestScope())throw std::runtime_error("public application entry accepted a private descriptor");
    {nexrt::RequestScope request(1000000,15000);nexrt::TaskGroup group(4,4096,{},false,true);auto ticket=group.spawnWithContext(root,address(),{},{});auto result=group.join(ticket);group.finish();status=int(result.scalar);}
    if(arrivals!=2||workers.size()!=2)throw std::runtime_error("native worker overlap was not demonstrated");
    std::fprintf(stderr,"NEX_TASK_OBSERVED {\"arrivals\":2,\"distinct_workers\":2,\"public_entry_rejected\":true}\n");
  }else{
    auto entry=reinterpret_cast<int(*)(int,const char *const*)>(dlsym(library,"main"));if(!entry)throw std::runtime_error(dlerror());
    const char *selected=argc==4&&std::string(argv[2])=="workers"?argv[3]:"1";
#ifdef NEX_SOURCE_DEBUG_REAL
    source_debug_test::start();const char *limit=std::getenv("NEX_PRIVATE_DEBUG_STEPS");
    const char *arguments[]={"nex-private-task","--nex-task-workers",selected,"--nex-task-steps",limit?limit:"1000000"};status=entry(5,arguments);source_debug_test::finish();
#else
    const char *arguments[]={"nex-private-task","--nex-task-workers",selected};status=entry(3,arguments);
#endif
  }
  if(nexrt::liveObjects.load()!=baseline)throw std::runtime_error("native task outcome retained managed values");
  {std::lock_guard lock(allocationsMutex);if(!allocations.empty())throw std::runtime_error("native task outcome retained tracked allocations");}
  dlclose(library);return status;
}catch(const std::exception &e){std::fprintf(stderr,"native test host: %s\n",e.what());return 71;}}
''', newline="\n")
host_binary=out/'host';export='-Wl,-export_dynamic' if platform.system()=='Darwin' else '-Wl,--export-dynamic'
run('link-host',[compiler,'-std=c++20','-O1','-g','-DNEX_PROFILE_ENABLED','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS',*extra_flags,'-I'+str(runtime),host,*objects,export,'-pthread',*(['-ldl'] if platform.system()!='Darwin' else []),'-o',host_binary])
fixtures=[];origins={}
f=source/'tests/source_exception_native.py';tree=ast.parse(f.read_text());node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='cases' for t in n.targets));fixtures += [('sequential-'+name,text) for name,text in ast.literal_eval(node.value)];origins[str(f.relative_to(source))]=hashlib.sha256(f.read_bytes()).hexdigest()
f=source/'tests/source_exception_tasks.cpp';fixtures += [('task-'+name,text) for kind,name,text in re.findall(r'\b(value|sourceError|trap)\("([^"]+)",R"\((.*?)\)"',f.read_text(),re.S) if name not in {'parent-budget','parent-cancellation'}];origins[str(f.relative_to(source))]=hashlib.sha256(f.read_bytes()).hexdigest()
for file,key in [('source_exception_tasks_typescript.py','fixtures'),('source_exception_task_ir_agreement.py','extra')]:
    f=source/'tests'/file;tree=ast.parse(f.read_text())
    if key=='fixtures':
        for n in tree.body:
            if isinstance(n,ast.AugAssign) and isinstance(n.target,ast.Name) and n.target.id==key: fixtures += [('task-'+item[1],item[2]) for item in ast.literal_eval(n.value)]
    else:
        n=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id==key for t in n.targets));fixtures += [('ir-'+name,text) for name,text in ast.literal_eval(n.value)]
    origins[str(f.relative_to(source))]=hashlib.sha256(f.read_bytes()).hexdigest()
assert len(fixtures)==74,len(fixtures)
fixtures += [('physical-source-overlap','''fn a()->i64 !{task,throw}{task_yield();throw("SYNC_A","first");}fn b()->i64 !{task,throw}{task_yield();throw("SYNC_B","second");}fn main()->i64 !{task,throw}{return with_tasks(2,fn(s:task_scope)->i64 !{task}{let a:task<i64>=task_spawn(s,a);let b:task<i64>=task_spawn(s,b);try{let n:i64=task_wait(a);assert(false);}catch(code,message){assert(code=="SYNC_A");}try{let n:i64=task_wait(b);assert(false);}catch(code,message){assert(code=="SYNC_B");}return 42;});}''')]
if a.profile: fixtures += [('profile-data-cancel-code','''fn cancel_source()->i64 !{task,throw}{task_yield();throw("E_CANCELLED","user data");}fn main()->i64 !{task,throw}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let t:task<i64>=task_spawn(s,cancel_source);try{return task_wait(t);}catch(code,message){assert(code=="E_CANCELLED");return 42;}});}''')]
debug_specs={}
if a.debug:
    tree=ast.parse((source/'tests/source_exception_task_debug.py').read_text());node=next(n for n in tree.body if isinstance(n,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='DEBUG_CASES' for t in n.targets))
    for name,text,expectations,limit in ast.literal_eval(node.value):fixtures.append((name,text));debug_specs[name]=(expectations,limit)
if a.case: fixtures=[(n,s) for n,s in fixtures if n in a.case];assert len(fixtures)==len(a.case)
report['fixtures']=origins;report['selected_programs']=len(fixtures);save()
for name,text in fixtures:
    d=out/(("case-"+name) if os.name=="nt" and name.upper()=="NUL" else name);d.mkdir(exist_ok=True);(d/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.24','entry':'main.nex'}), newline="\n");f=d/'main.nex';f.write_text('module native_task_exception;\n'+text+'\n', newline="\n")
    limit=debug_specs[name][1] if a.debug else 1000000
    expected=json.loads(run(name+'-reference',[reference,'reference',f,str(limit)]).stdout);(d/'reference.json').write_text(json.dumps(expected,ensure_ascii=False,indent=2)+'\n', newline="\n")
    for optimization in ['0','2']:
        e=d/('O'+optimization);e.mkdir(exist_ok=True)
        if name=='task-client-pruning':
            rejected=run(name+'-emit-O'+optimization,[emitter,'emit',f,e,triple,layout,str(optimization=='2').lower()],allowed=(1,));assert 'E_REALM' in rejected.stderr
            report['stage_rejections'].append({'name':name,'optimization':optimization,'code':'E_REALM','source_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'reason':'client realm has no native application entry','passed':True});save();continue
        run(name+'-emit-O'+optimization,[emitter,'emit',f,e,triple,layout,str(optimization=='2').lower(),*(['profile'] if a.profile else ['debug'] if a.debug else [])])
        library=e/('program.dylib' if platform.system()=='Darwin' else 'program.so')
        run(name+'-link-O'+optimization,[compiler,'-O'+optimization,'-shared','-fPIC',e/'program.ll',*(probe_dll_inputs(host_binary,e) if os.name=='nt' else ['-Wl,-undefined,dynamic_lookup'] if platform.system()=='Darwin' else []),'-o',library])
        environment={**os.environ}
        if a.profile:
            environment.pop('NEX_TRACY',None);environment.update(NEX_PROFILE_OUTPUT=str(e/'profile.json'),NEX_PROFILE_EVENTS='100000')
        if a.debug:
            plans=[]
            for tag,visits in debug_specs[name][0].items():
                line=next(i for i,text in enumerate(f.read_text().splitlines(),1) if '// STOP:'+tag in text);plans.append(str(line)+':'+str(len(visits)))
            environment.update(NEX_PRIVATE_DEBUG_OUTPUT=str(e/'observations.jsonl'),NEX_PRIVATE_DEBUG_LINES=','.join(plans),NEX_PRIVATE_DEBUG_STEPS=str(limit))
        result=run_native([str(host_binary),str(library)],text=True,capture_output=True,timeout=40,env=environment);(e/'stdout.txt').write_text(result.stdout, newline="\n");(e/'stderr.txt').write_text(result.stderr, newline="\n")
        debug_stats=None
        if a.debug:
            debug_stats=json.loads(next(line.split(' ',1)[1] for line in result.stderr.splitlines() if line.startswith('NEX_PRIVATE_DEBUG ')))
            result.stderr=''.join(line+'\n' for line in result.stderr.splitlines() if not line.startswith('NEX_PRIVATE_DEBUG '))
        if expected['kind']=='return':
            assert result.returncode==(expected['value'] or 0)%256 and result.stdout==expected['output'] and not result.stderr,(name,optimization,expected,result.returncode,result.stdout,result.stderr)
        elif expected['kind']=='exception':
            assert result.returncode==70,(name,optimization,result.returncode,result.stderr)
            record=next(json.loads(line.split(' ',1)[1]) for line in result.stderr.splitlines() if line.startswith('NEX_SOURCE_EXCEPTION '))
            for key in ['code','message','line']: assert record[key]==expected[key],(name,key,record,expected)
            assert record['source'] is not None and result.stdout==expected['output'],(name,record,expected)
            operations=json.loads((e/'metadata.json').read_text())['operations'];original=next(op for op in operations if op['site']==record['source']['operation_site'] and op['function_hash']==record['source']['function_hash'])
            assert original['kind']=='statement.throw' and original['line']==expected['line'] and original['column']==expected['column'],(name,original,expected)
            assert record['source']['function_source_hash']==original['function_source_hash'] and record['source']['byte_begin']==original['begin'] and record['source']['byte_end']==original['end'],(name,record,original)
        else:
            assert result.returncode==70 and expected['code'] in result.stderr and 'NEX_SOURCE_EXCEPTION ' not in result.stderr,(name,optimization,expected,result.returncode,result.stderr)
        item={'name':name,'optimization':optimization,'source_sha256':hashlib.sha256(f.read_bytes()).hexdigest(),'expected':expected,'native_exit':result.returncode,'passed':True}
        if a.debug:
            item.update(debug_statistics=debug_stats,debug_observations_sha256=hashlib.sha256((e/'observations.jsonl').read_bytes()).hexdigest())
        if a.profile:
            profile=json.loads((e/'profile.json').read_text());assert profile['schema']=='nex.profile-runtime/2' and profile['kind']=='native_tasks' and not profile['incomplete'],(name,profile)
            assert all(t['terminal'] and not t['active_invocations'] for t in profile['tasks']),(name,'unfinished task profile')
            item['profile_sha256']=hashlib.sha256((e/'profile.json').read_bytes()).hexdigest()
        if not(a.profile or a.debug) and name in {'task-future-repeated','task-spawn-after-recovery','task-drain-cancels-parked-sibling','task-body-error-cancels-children','task-body-precedence','task-nested-groups','task-future-own-group','task-nul-unicode'}:
            for workers in [2,4]:
                r=run(name+'-workers'+str(workers)+'-O'+optimization,[host_binary,library,'workers',str(workers)],allowed=(42,));assert not r.stderr and r.stdout==expected['output']
                report['parallel_runs'].append({'name':name,'optimization':optimization,'workers':workers,'passed':True})
        if name=='physical-source-overlap':
            symbol=json.loads((e/'metadata.json').read_text())['descriptor_symbol'];r=run(name+'-observe-O'+optimization,[host_binary,library,'observe',symbol],allowed=(42,));observed=json.loads(next(line.split(' ',1)[1] for line in r.stderr.splitlines() if line.startswith('NEX_TASK_OBSERVED ')));assert observed['arrivals']==observed['distinct_workers']==2;item['physical_overlap']=observed
        report['cases'].append(item);save()
report.update(ok=True,comparisons=len(report['cases']),source_programs=len(fixtures),native_source_programs=len(report['cases'])//2,all_current_handles_terminal=True);save();print(json.dumps({'ok':True,'comparisons':len(report['cases']),'stage_rejections':len(report['stage_rejections']),'report':str(out/'report.json')}))
