"""Execute real MLIR/LLVM compiled continuation steps through the OS scheduler."""
import argparse,contextlib,json,os,re,shutil,subprocess,sys,tempfile
from pathlib import Path

parser=argparse.ArgumentParser();parser.add_argument('nex');parser.add_argument('probe');parser.add_argument('--sanitizer',choices=('address','thread'))
args=parser.parse_args();nex,probe=map(lambda s:str(Path(s).resolve()),(args.nex,args.probe))
sanitize=(['-fsanitize=address,undefined','-fno-sanitize-recover=all','-fno-omit-frame-pointer'] if args.sanitizer=='address' else ['-fsanitize=thread','-fno-omit-frame-pointer'] if args.sanitizer=='thread' else [])
source=Path(__file__).resolve().parents[1]
env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
if args.sanitizer=='address':env.update(ASAN_OPTIONS='detect_leaks=1:halt_on_error=1:abort_on_error=1',UBSAN_OPTIONS='halt_on_error=1:print_stacktrace=1')
if args.sanitizer=='thread':env.update(TSAN_OPTIONS='halt_on_error=1:abort_on_error=1')
def run(args,**kw):
 p=subprocess.run(list(map(str,args)),text=True,capture_output=True,env=env,timeout=180,**kw)
 if p.returncode:raise AssertionError(str(args)+'\n'+p.stdout+p.stderr)
 return p.stdout
doctor=json.loads(run([nex,'doctor','--json']));clang=doctor['native_compiler']
target=run([clang,'-S','-emit-llvm','-x','c++','-','-o','-'],input='')
triple=re.search(r'target triple = "([^"]+)"',target)[1]
layout=re.search(r'target datalayout = "([^"]+)"',target)[1]

driver=r'''
#include "nex_task_frame.h"
#include <cstdio>
#include <cstdlib>
#include <map>
#include <mutex>
#include <atomic>
#include <array>
#include <barrier>
#include <set>
#include <thread>
extern "C" int64_t SYMBOL(void*);
extern "C" const nexrt::TaskCodeDescriptor *DESCRIPTOR();
extern "C" void *nex_closure_code(nexrt::Handle*);
extern "C" nexrt::Handle *nex_closure_new(void*,int64_t);
static std::mutex mutex;
static std::map<const void*,std::pair<int,std::thread::id>> objects;
static std::atomic<int> resumes{0};
static std::atomic<bool> ready{false},deepYielded{false};
static std::vector<void*> order;
static std::set<std::thread::id> workers;
static std::barrier rendezvous(WORKERS);
static std::atomic<int> started{0};
static void require(bool x){if(!x)std::abort();}
extern "C" void nex_profile_enter(const char*,const char*,int64_t,const char*){}
extern "C" void nex_profile_leave(){}
extern "C" void nex_profile_unwind(){}
extern "C" void nex_profile_allocation(const void *p,size_t,int pool){std::lock_guard lock(mutex);require(objects.emplace(p,std::make_pair(pool,std::this_thread::get_id())).second);}
extern "C" void nex_profile_free(const void *p){std::lock_guard lock(mutex);require(objects.erase(p)==1);}
static int64_t step(void *frame){
 if(!ready.load())return 1;
 if(WORKERS>1&&started.fetch_add(1)<WORKERS)rendezvous.arrive_and_wait();
 {std::lock_guard lock(mutex);order.push_back(frame);workers.insert(std::this_thread::get_id());}
 return SYMBOL(frame);
}
static void observe(const nexrt::NativeTaskFrame &frame,int64_t transition){
 if(frame.depth>1&&transition==1)deepYielded=true;
 ++resumes;std::lock_guard lock(mutex);for(auto [p,record]:objects)require(record.first!=0||record.second!=std::this_thread::get_id());
}
static const std::array<int64_t,SLOTCOUNT> kinds{KINDS};
static const std::array<uint32_t,PARAMCOUNT> parameters{PARAMETERS};
static nexrt::TaskBody task(nexrt::TaskGroup &group,nexrt::Value,nexrt::Value){
 nexrt::NativeTaskFrame frame(*DESCRIPTOR(),INPUTARGS,{});frame.step=step;return nexrt::executeTaskFrame(group,std::move(frame),observe);
}
int main(){
 // Descriptor arrays are caller-owned; a retained frame must copy its kinds.
 {std::vector<int64_t> schema{0};std::vector<uint32_t> params{0};
  nexrt::NativeTaskFrame f({step,schema,params},{nexrt::Value(21)});
  schema.clear();params.clear();require(f.read(0,0).scalar==21);
  auto invalid=[&](auto action){bool failed=false;try{action();}catch(const nexrt::DataError &e){require(e.code=="E_TASK_STATE");failed=true;}require(failed);};
  invalid([&]{f.write(0,nexrt::Value(1,true),1);});require(f.read(0,0).scalar==21);
  invalid([&]{f.read(-1,0);});invalid([&]{f.read(1,0);});
  f.drop(0);invalid([&]{f.read(0,0);});
  nex_task_frame_return_i64(&f,42,0);require(f.result.scalar==42);
  invalid([&]{nex_task_frame_pc(&f);});invalid([&]{nex_task_frame_return_unit(&f);});
  std::array<int64_t,1> floating{2};std::array<uint32_t,1> argument{0};nexrt::Value bad;bad.tag=nexrt::Value::Floating;bad.scalar=INT64_C(0x7ff8000000000000);
  bool rejected=false;try{nexrt::NativeTaskFrame invalidFloat({step,floating,argument},{bad});}catch(const nexrt::DataError &e){require(e.code=="E_FLOAT");rejected=true;}require(rejected);
 }
 {nexrt::RequestScope protocol;
  auto invalid=[&](auto action){bool failed=false;try{action();}catch(const nexrt::DataError &e){require(e.code=="E_TASK_STATE");failed=true;}require(failed);};
  std::array<int64_t,2> types{0,0},params{0,0},captures{0,0};
  nexrt::TaskCodeDescriptor d{step,types.data(),params.data(),captures.data(),nexrt::taskCodeABI,2,0,0,4};
  auto bad=d;bad.abi=0;invalid([&]{nexrt::NativeTaskFrame f(bad,{},{});});
  bad=d;bad.parameterCount=2;invalid([&]{nexrt::NativeTaskFrame f(bad,{nexrt::Value(1),nexrt::Value(2)},{});});
  bad=d;bad.parameterCount=1;params[0]=3;invalid([&]{nexrt::NativeTaskFrame f(bad,{nexrt::Value(1)},{});});params[0]=0;
  bad=d;bad.captureCount=1;invalid([&]{nexrt::NativeTaskFrame f(bad,{},{});});
  nexrt::NativeTaskFrame typed(d,{},{});invalid([&]{nex_task_frame_return_i64(&typed,42,0);});
  auto trapped=[&](const char *code,auto action){bool failed=false;try{action();}catch(const nexrt::Trap &e){require(e.code==code);failed=true;}require(failed);};
  auto closure=nex_task_closure_new_at(&d,0,nullptr);
  trapped("E_FUNCTION",[&]{nex_closure_code(closure);});
  auto ordinary=nex_closure_new(reinterpret_cast<void*>(step),0);
  auto arguments=nexrt::makeHandle(nexrt::Value(std::make_shared<nexrt::Data>(nexrt::Data::List)));
  nexrt::NativeTaskFrame caller(d,{},{});
  trapped("E_TASK_STATE",[&]{nex_task_frame_call_at(&caller,nullptr,ordinary,arguments,-1,1,nullptr);});
  nex_task_closure_bind_at(ordinary,&d,nullptr);require(nex_closure_code(ordinary)==reinterpret_cast<void*>(step));
  nex_task_frame_call_at(&caller,nullptr,ordinary,arguments,-1,1,nullptr);require(caller.pendingCall&&caller.pendingCall->step==step);
  trapped("E_TASK_STATE",[&]{nex_task_closure_bind_at(ordinary,&d,nullptr);});
 }
 std::string result;
 {nexrt::RequestScope request(1000000,30000);nexrt::TaskGroup group(WORKERS);
  std::vector<nexrt::TaskGroup::Ticket> tickets;
  for(int i=0;i<REPEATS;++i)tickets.push_back(group.spawn(task));
  ready=true;
  if(CANCEL_CASE){auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(5);while(!deepYielded.load()){require(std::chrono::steady_clock::now()<deadline);std::this_thread::yield();}require(group.cancel(tickets.front()));}
  for(auto ticket:tickets){std::string current;
   try{current=nexrt::representation(group.join(ticket));}
   catch(const nexrt::Trap &e){auto located=dynamic_cast<const nexrt::LocatedTrap*>(&e);if(e.code!="E_CANCELLED")require(located&&located->source.find("function_hash")!=std::string::npos&&located->source.find("operation_site")!=std::string::npos);current="TRAP:"+e.code+(e.code=="E_CANCELLED"?"":":"+std::to_string(e.line));}
   require(result.empty()||result==current);result=current;
  }
  group.finish();
 }
 require(nexrt::liveObjects==0);{std::lock_guard lock(mutex);require(objects.empty());}
 require(resumes>=MINIMUM);nex_runtime_finish();
 if(WORKERS==1&&REPEATS>1)require(order.size()>2&&order[0]!=order[1]);
 require(workers.size()==WORKERS);
 std::printf("RESULT=%s\n",result.c_str());
}
'''
cases=[
 ('unit','''fn main()->unit !{task}{task_yield();}''','0','',2),
 ('parameter','''fn main(value:i64)->i64 !{task}{task_yield();return value*2;}''','42','',2),
 ('loop','''fn main()->i64 !{task}{var n:i64=0;var total:i64=0;while n<7{total=total+n;task_yield();n=n+1;}return total*2;}''','42','',8),
 ('heap','''fn main()->str !{task}{let items:list<str>=["A🧠\\u0000","two"];task_yield();return items[0]+items[1];}''','"A🧠\\u0000two"','',2),
 ('float','''fn main()->f64 !{task}{var value:f64=1.5;task_yield();value=value*2.0;task_yield();return value;}''','3e0','',3),
 ('closure','''fn main()->i64 !{task}{var base:i64=40;let add:fn(i64)->i64=fn(x:i64)->i64{return base+x;};base=99;task_yield();return add(2);}''','42','',2),
 ('helper','''fn twice(x:i64)->i64{return x*2;}fn main()->i64 !{task}{task_yield();return twice(21);}''','42','',2),
 ('short','''fn noisy()->bool !{io}{print(999);return true;}fn main()->bool !{task,io}{let a:bool=false&&noisy();task_yield();return a||(true||noisy());}''','true','',2),
 ('patterns','''enum Box{Items(values:list<i64>);Empty;}fn main()->i64 !{task}{let box:Box=Box::Items([21,2]);task_yield();match box{Box::Items([x,y]) if x>10=>{task_yield();return x*y;},_=>{return 0;}}}''','42','',3),
 ('propagate','''fn main()->result<i64> !{task}{let before:result<str>=err<str>("E_STOP","stop");task_yield();let value:str=before?;return ok(len(value));}''','{"error":{"code":"E_STOP","message":"stop"}}','',2),
 ('unwrap-trap','''fn main()->i64 !{task,io}{print(7);task_yield();let result:result<i64>=err<i64>("E_ITEM","bad");return unwrap(result);}''','TRAP:E_RESULT:2','7\n',1),
 ('overflow','''fn main()->i64 !{task,io}{print(7);task_yield();let value:i64=9223372036854775807;return value+1;}''','TRAP:E_OVERFLOW:2','7\n',1),
 ('direct','fn twice(x:i64)->i64 !{task}{task_yield();return x*2;}fn main()->i64 !{task}{return twice(21);}','42','',3),
 ('nested','fn add(a:i64,b:i64)->i64 !{task}{task_yield();return a+b;}fn main()->i64 !{task}{return add(add(20,1),add(10,11));}','42','',7),
 ('unit-call','fn pause()->unit !{task}{task_yield();}fn main()->i64 !{task}{pause();return 42;}','42','',3),
 ('call-heap','fn suffix(x:str)->str !{task}{task_yield();return x+"🧠";}fn main()->str !{task}{return suffix("A\\u0000");}','"A\\u0000🧠"','',3),
 ('recursive','fn sum(n:i64)->i64 !{task}{if n==0{return 0;}task_yield();return n+sum(n-1);}fn main()->i64 !{task}{return sum(6)*2;}','42','',15),
 ('task-reference','fn twice(n:i64)->i64 !{task}{task_yield();return n*2;}fn main()->i64 !{task}{let f:fn(i64)->i64 !{task}=twice;return f(21);}','42','',3),
 ('task-snapshot','fn main()->i64 !{task}{var base:i64=40;let f:fn(i64)->i64 !{task}=fn(x:i64)->i64 !{task}{task_yield();return base+x;};base=99;return f(2);}','42','',3),
 ('task-factory','fn factory(x:i64)->(fn(i64)->i64 !{task}){return fn(y:i64)->i64 !{task}{task_yield();return x+y;};}fn main()->i64 !{task}{let f:fn(i64)->i64 !{task}=factory(40);task_yield();return f(2);}','42','',4),
 ('call-order','fn item(n:i64)->i64 !{task,io}{print(n);task_yield();return n;}fn combine(a:i64,b:i64)->i64 !{task}{task_yield();return a+b;}fn main()->i64 !{task,io}{return combine(item(20),item(22));}','42','20\n22\n',7),
 ('call-short','fn noisy()->bool !{task,io}{print(99);task_yield();return true;}fn main()->bool !{task,io}{return (true||noisy())&&(false&&noisy());}','false','',1),
 ('call-error','fn fail()->result<str> !{task}{task_yield();return err<str>("E_CALL","stop");}fn main()->result<i64> !{task}{let value:str=fail()?;return ok(len(value));}','{"error":{"code":"E_CALL","message":"stop"}}','',3),
 ('call-trap','fn fail()->i64 !{task,io}{print(7);task_yield();return 1/0;}fn main()->i64 !{task,io}{let held:list<str>=["retained🧠"];return fail()+len(held);}','TRAP:E_DIV_ZERO:2','7\n',2),
 ('pure-depth-boundary','fn dive(n:i64)->i64{if n==0{return 42;}return dive(n-1);}fn main()->i64 !{task}{task_yield();return dive(254);}','42','',2),
 ('pure-depth-limit','fn dive(n:i64)->i64{if n==0{return 42;}return dive(n-1);}fn main()->i64 !{task}{task_yield();return dive(300);}','TRAP:E_LIMIT:0','',1),
 ('task-depth-boundary','fn dive(n:i64)->i64 !{task}{if n==0{return 42;}return dive(n-1);}fn main()->i64 !{task}{return dive(254);}','42','',511),
 ('task-depth-limit','fn dive(n:i64)->i64 !{task}{if n==0{return 42;}return dive(n-1);}fn main()->i64 !{task}{return dive(300);}','TRAP:E_LIMIT:2','',255),
 ('mixed-depth-limit','fn pure(n:i64)->i64{if n==0{return 42;}return pure(n-1);}fn dive(n:i64)->i64 !{task}{if n==0{return pure(200);}return dive(n-1);}fn main()->i64 !{task}{return dive(100);}','TRAP:E_LIMIT:0','',101),
 ('mixed-depth-boundary','fn pure(n:i64)->i64{if n==0{return 42;}return pure(n-1);}fn dive(n:i64)->i64 !{task}{if n==0{return pure(153);}return dive(n-1);}fn main()->i64 !{task}{return dive(100);}','42','',203),
 ('cancel-call','fn wait(held:list<str>)->i64 !{task}{while true{task_yield();}return len(held);}fn main()->i64 !{task}{return wait(["retained🧠"]);}','TRAP:E_CANCELLED','',2),
]
@contextlib.contextmanager
def compiled_output():
 tmp=tempfile.mkdtemp(prefix='nex-native-task-')
 try:yield tmp
 except BaseException:
  print('Failed native MLIR/LLVM artifacts retained at '+tmp,file=sys.stderr);raise
 else:shutil.rmtree(tmp)
with compiled_output() as tmp:
 root=Path(tmp);runtime=source/'runtime';objects=[]
 for name in ('runtime.cpp','nex_files.cpp','nex_task_frame.cpp'):
  obj=root/(name+'.o')
  run([clang,'-std=c++20','-O1','-g','-DNEX_PROFILE_ENABLED','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS','-I'+str(runtime),*sanitize,'-c',runtime/name,'-o',obj]);objects.append(obj)
 mirrors=0;typescript_mirrors=0
 for name,body,result,prefix,minimum in cases:
  path=root/(name+'.nex');path.write_text('module native_steps;\n'+body+'\n')
  folder=root/name;metadata=json.loads(run([probe,path,folder,triple,layout,'main']))
  assert metadata['public_source_tasks'] is False
  cpp=folder/'driver.cpp';cpp.write_text(driver.replace('SYMBOL',metadata['symbol']).replace('DESCRIPTOR',metadata['descriptor']).replace('KINDS',','.join(map(str,metadata['slots']))).replace('PARAMETERS',','.join(map(str,metadata['parameters']))).replace('SLOTCOUNT',str(len(metadata['slots']))).replace('PARAMCOUNT',str(len(metadata['parameters']))).replace('MINIMUM',str(minimum)).replace('REPEATS','4' if name in ('parameter','direct','task-snapshot') else '2' if name=='loop' else '1').replace('WORKERS','2' if name in ('parameter','direct','task-snapshot') else '1').replace('CANCEL_CASE','1' if name=='cancel-call' else '0').replace('INPUTARGS','{nexrt::Value(21)}' if name=='parameter' else '{}'))
  for optimize in ('-O0','-O2'):
   executable=folder/('program'+optimize)
   command=[clang,'-std=c++20',optimize,'-g','-DNEX_PROFILE_ENABLED','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS','-I'+str(runtime),*sanitize,folder/'program.ll',cpp,*objects,'-pthread','-o',executable]
   if sys.platform.startswith('linux'):command.insert(1,'-fuse-ld=lld')
   run(command);actual=run([executable]);assert actual==prefix+'RESULT='+result+'\n',(name,optimize,actual)
  if '-depth-' in name or name=='cancel-call':continue
  mirrors+=1
  # With no other concurrent effects, removing yield has the same observable
  # values/output. Execute an independent ordinary AST and TypeScript mirror;
  # this does not claim asynchronous reference/TypeScript scheduling.
  mirror=body.replace('task_yield();','').replace('!{task,io}','!{io}').replace('!{task}','')
  call='main(21)' if name=='parameter' else 'main()'
  observation=call+';print(0);' if name=='unit' else 'print('+call+');'
  mirrored=root/(name+'-mirror.nex');mirrored.write_text('module mirror;\n'+mirror+'\ntest fn observe()->unit !{io}{'+observation+'}\n')
  if result.startswith('TRAP:'):
   reference=subprocess.run([nex,'eval',str(mirrored),'--entry','observe','--json'],capture_output=True,text=True,env=env)
   value=json.loads(reference.stdout);assert reference.returncode==1 and value['code']==result.split(':')[1] and value['stdout']==prefix,(name,value)
  else:
   text=json.loads(result) if result.startswith('"') else result
   reference=json.loads(run([nex,'eval',mirrored,'--entry','observe','--json']))
   assert reference['stdout']==prefix+text+'\n',(name,reference)
   typescript_mirrors+=1
   web=json.loads(run([nex,'test',mirrored,'--symbol','observe','--target','web','--json']))
   assert len(web['tests'])==1 and web['tests'][0]['web'] is True,web
 for body in [
  'fn main()->i64 !{task}{return with_tasks(2,fn(s:task_scope)->i64 !{task}{return 42;});}',
 ]:
  path=root/'rejected.nex';path.write_text('module rejected;'+body)
  rejected=subprocess.run([probe,str(path),str(root/'rejected'),triple,layout,'main'],capture_output=True,text=True,env=env)
  assert rejected.returncode==1 and json.loads(rejected.stdout)['code']=='E_TASK_UNIMPLEMENTED',rejected.stdout+rejected.stderr
 print(json.dumps({'ok':True,'source_scenarios':len(cases),'native_profiles':2,'ordinary_ast_mirrors':mirrors,'ordinary_typescript_mirrors':typescript_mirrors,'mirror_suspension':'yield erased; no asynchronous reference/TypeScript support claimed','compiled_worker_threads':2,'public_source_tasks':False,'native_yield_steps':True,'logical_task_calls':True,'task_closure_descriptors':True,'combined_call_depth':256,'scope_channels':False,'compiled_call_cancellation':True,'sanitizer':args.sanitizer,'sanitizer_scope':'compiled source modules/runtime/driver; ordinary AST/TypeScript mirrors uninstrumented'}))
