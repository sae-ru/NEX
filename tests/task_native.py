"""Execute real MLIR/LLVM compiled continuation steps through the OS scheduler."""
import contextlib,json,os,re,shutil,subprocess,sys,tempfile
from pathlib import Path

nex,probe=map(lambda s:str(Path(s).resolve()),sys.argv[1:3])
source=Path(__file__).resolve().parents[1]
env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
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
static std::mutex mutex;
static std::map<const void*,std::pair<int,std::thread::id>> objects;
static std::atomic<int> resumes{0};
static std::atomic<bool> ready{false};
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
 auto transition=SYMBOL(frame);++resumes;
 std::lock_guard lock(mutex);for(auto [p,record]:objects)require(record.first!=0||record.second!=std::this_thread::get_id());
 return transition;
}
static const std::array<int64_t,SLOTCOUNT> kinds{KINDS};
static const std::array<uint32_t,PARAMCOUNT> parameters{PARAMETERS};
static nexrt::TaskBody task(nexrt::TaskGroup &group,nexrt::Value,nexrt::Value){
 return nexrt::executeTaskFrame(group,nexrt::NativeTaskFrame({step,kinds,parameters},INPUTARGS));
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
 std::string result;
 {nexrt::RequestScope request(1000000,30000);nexrt::TaskGroup group(WORKERS);
  std::vector<nexrt::TaskGroup::Ticket> tickets;
  for(int i=0;i<REPEATS;++i)tickets.push_back(group.spawn(task));
  ready=true;
  for(auto ticket:tickets){std::string current;
   try{current=nexrt::representation(group.join(ticket));}
   catch(const nexrt::Trap &e){current="TRAP:"+e.code+":"+std::to_string(e.line);}
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
  run([clang,'-std=c++20','-O1','-g','-DNEX_PROFILE_ENABLED','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS','-I'+str(runtime),'-c',runtime/name,'-o',obj]);objects.append(obj)
 for name,body,result,prefix,minimum in cases:
  path=root/(name+'.nex');path.write_text('module native_steps;\n'+body+'\n')
  folder=root/name;metadata=json.loads(run([probe,path,folder,triple,layout,'main']))
  assert metadata['public_source_tasks'] is False
  cpp=folder/'driver.cpp';cpp.write_text(driver.replace('SYMBOL',metadata['symbol']).replace('KINDS',','.join(map(str,metadata['slots']))).replace('PARAMETERS',','.join(map(str,metadata['parameters']))).replace('SLOTCOUNT',str(len(metadata['slots']))).replace('PARAMCOUNT',str(len(metadata['parameters']))).replace('MINIMUM',str(minimum)).replace('REPEATS','4' if name=='parameter' else '2' if name=='loop' else '1').replace('WORKERS','2' if name=='parameter' else '1').replace('INPUTARGS','{nexrt::Value(21)}' if name=='parameter' else '{}'))
  for optimize in ('-O0','-O2'):
   executable=folder/('program'+optimize)
   command=[clang,'-std=c++20',optimize,'-g','-DNEX_PROFILE_ENABLED','-DNEX_STRUCTURED_WORKERS','-DNEX_ASYNC_TASKS','-I'+str(runtime),folder/'program.ll',cpp,*objects,'-pthread','-o',executable]
   if sys.platform.startswith('linux'):command.insert(1,'-fuse-ld=lld')
   run(command);actual=run([executable]);assert actual==prefix+'RESULT='+result+'\n',(name,optimize,actual)
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
   web=json.loads(run([nex,'test',mirrored,'--symbol','observe','--target','web','--json']))
   assert len(web['tests'])==1 and web['tests'][0]['web'] is True,web
 for body in [
  'fn other()->i64 !{task}{task_yield();return 42;}fn main()->i64 !{task}{return other();}',
  'fn main()->i64 !{task}{return with_tasks(2,fn(s:task_scope)->i64 !{task}{return 42;});}',
 ]:
  path=root/'rejected.nex';path.write_text('module rejected;'+body)
  rejected=subprocess.run([probe,str(path),str(root/'rejected'),triple,layout,'main'],capture_output=True,text=True,env=env)
  assert rejected.returncode==1 and json.loads(rejected.stdout)['code']=='E_TASK_UNIMPLEMENTED',rejected.stdout+rejected.stderr
 print(json.dumps({'ok':True,'source_scenarios':len(cases),'native_profiles':2,'ordinary_ast_mirrors':len(cases),'ordinary_typescript_mirrors':len(cases)-2,'mirror_suspension':'yield erased; no asynchronous reference/TypeScript support claimed','compiled_worker_threads':2,'public_source_tasks':False,'native_yield_steps':True,'general_task_calls_channels':False}))
