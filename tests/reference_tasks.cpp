#include "nex/task_reference.h"
#include "nex/managed_references.h"
#include "nex_files.h"
#include "host_file_observers.h"
#include <chrono>
#include <filesystem>
#include <fstream>
#include <fcntl.h>
#include <unordered_set>
#include <iostream>
#include <stdexcept>
using namespace nex;
int runOwnerTaskRuntime();
int runNativeTaskSessionKernel();
namespace {
unsigned cases=0;
namespace fs=std::filesystem;
fs::path corpusDirectory;
llvm::json::Array corpus;
size_t files(){
#ifdef _WIN32
 return nex_test::files().size();
#else
 size_t count=0;for(int fd=0;fd<4096;++fd)if(::fcntl(fd,F_GETFD)>=0)++count;return count;
#endif
}
void require(bool value,const std::string &message){if(!value)throw std::runtime_error(message);}
Program source(const std::string &body){
  auto p=parseVersioned("module reference_tasks;\n"+body,"reference_tasks.nex",SourceLanguage::References030);check(p);return p;
}
void runs(const std::string &body,const std::string &expected,const fs::path &root={}){
  auto p=source(body);const auto identity=revision(p);auto baseline=nexrt::liveObjects.load();auto descriptors=files();
  {
    std::unique_ptr<nexrt::TextFiles> text;std::unique_ptr<nexrt::FileScope> scope;
    if(!root.empty()){text=std::make_unique<nexrt::TextFiles>(root.string(),true);scope=std::make_unique<nexrt::FileScope>(*text);}
    auto result=evaluateManagedTaskReferencePrototype(p);
    require(result.task.output==expected,"managed task output differs: "+result.task.output);
    require(result.task.executionWorkers==1,"reference task prototype claimed CPU workers");
    require(result.afterClose.cells==0&&result.afterClose.nodes==0,"managed task heap did not close");
    require(revision(p)==identity,"managed task evaluation changed source identity");
    auto ordinary=evaluate(p);require(ordinary.output==expected,"ordinary managed task output differs");
  }
  require(nexrt::liveObjects.load()==baseline,"managed task execution leaked values");
  require(files()==descriptors,"managed task execution leaked file descriptors");
  if(!corpusDirectory.empty()){
    auto file="case-"+std::to_string(cases)+".nex";
    writeFile((corpusDirectory/file).string(),p.source);
    corpus.push_back(llvm::json::Object{{"file",file},{"revision",identity},{"stdout",expected},{"files",!root.empty()}});
  }
  ++cases;
}
void fails(const std::string &body,const std::string &code,uint64_t limit=1000000,nexrt::CellHeapLimits bounds={},const fs::path &root={}){
  auto baseline=nexrt::liveObjects.load();auto descriptors=files();bool failed=false;std::string message,output;
  {
    std::unique_ptr<nexrt::TextFiles> text;std::unique_ptr<nexrt::FileScope> scope;
    if(!root.empty()){text=std::make_unique<nexrt::TextFiles>(root.string(),true);scope=std::make_unique<nexrt::FileScope>(*text);}
    try{auto p=source(body);(void)evaluateManagedTaskReferencePrototype(p,"main",limit,bounds);}
    catch(const Error &error){require(error.code==code,"expected "+code+", got "+error.code+": "+error.message);message=error.message;output=error.output;failed=true;}
  }
  require(failed,"expected managed task failure "+code);
  require(nexrt::liveObjects.load()==baseline,"failed managed task retained values");
  require(files()==descriptors,"failed managed task retained descriptors");
  if(!corpusDirectory.empty()&&(code=="E_LIMIT"||code=="E_SOURCE_EXCEPTION"||code=="E_RESOURCE_SCOPE"||code=="E_ASSERT")){
    auto p=source(body);auto file="case-"+std::to_string(cases)+".nex";
    writeFile((corpusDirectory/file).string(),p.source);
    corpus.push_back(llvm::json::Object{{"file",file},{"revision",revision(p)},{"stdout",output},{"files",!root.empty()},
      {"error",code},{"message",message},{"steps",int64_t(limit)}});
  }
  ++cases;
}
struct Fixture {
 fs::path root=fs::temp_directory_path()/("nex-reference-tasks-"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
 Fixture(){require(fs::create_directory(root),"cannot create unique reference task fixture");std::ofstream(root/"input",std::ios::binary)<<"abcdef";}
 ~Fixture(){std::error_code error;fs::remove_all(root,error);}
};
void observesCleanup(bool cancel){
 auto p=source(R"nex(
fn main()->unit!{state,task,throw}{
 let value:cell<i64>=cell_new(42);
 let n:i64=with_tasks(1,fn(s:task_scope)->i64!{state,task}{task_yield();return cell_read(value);});
}
)nex");
 const auto baseline=nexrt::liveObjects.load();const auto descriptors=files();bool observed=false,failed=false;nexrt::Value retained;
 struct Host final:TaskReferenceExternalHost {std::optional<TaskReferenceExternalRequest> prepare(size_t,Span)override{return {};}};
 std::stop_source stop;Host host;host.cancellation=stop.get_token();
 TaskReferenceObserver observer=[&](size_t,const TaskTransition &transition){
  std::vector<nexrt::Value> work=transition.arguments;std::unordered_set<const nexrt::Data*> seen;
  while(!work.empty()){
   auto value=std::move(work.back());work.pop_back();if(value.tag!=nexrt::Value::Object||!value.object||!seen.insert(value.object.get()).second)continue;
   if(value.object->kind==nexrt::Data::Cell){
    retained=value;observed=true;
    if(cancel)stop.request_stop();else throw std::runtime_error("observer-stop");
    break;
   }
   work.insert(work.end(),value.object->values.begin(),value.object->values.end());
  }
 };
 try{(void)evaluateManagedTaskReferencePrototype(p,"main",1000000,{},nullptr,observer,cancel?&host:nullptr);}
 catch(const Error &error){require(cancel&&error.code=="E_CANCELLED","unexpected observer control error: "+error.code);failed=true;}
 catch(const std::runtime_error &error){require(!cancel&&std::string(error.what())=="observer-stop","unexpected observer exception");failed=true;}
 require(observed&&failed,"observer did not interrupt a live managed task");
 require(retained.object->values.empty(),"ended task context retained its live cell payload");retained={};
 require(nexrt::liveObjects.load()==baseline,"observer/control failure leaked source values");
 require(files()==descriptors,"observer/control failure leaked files");++cases;
}
}
int main(int argc,char **argv){try{
  if(argc==7&&std::string(argv[1])=="reference"){
    auto path=fs::absolute(argv[2]);auto p=parseVersioned(readFile(path.string()),path.string(),SourceLanguage::References030);check(p);
    const auto baseline=nexrt::liveObjects.load();llvm::json::Object report;
    try{
      auto result=evaluateManagedTaskReferencePrototype(p,"main",std::stoull(argv[3]),{std::stoull(argv[4]),std::stoull(argv[5]),std::stoull(argv[6])});
      report=llvm::json::Object{{"kind","return"},{"stdout",result.task.output},
        {"value_json",p.function("main").result==Type::Unit?"null":nexrt::representation(result.task.value)},
        {"after_close_cells",int64_t(result.afterClose.cells)},{"after_close_nodes",int64_t(result.afterClose.nodes)}};
    }catch(const Error &error){report=llvm::json::Object{{"kind","trap"},{"stdout",error.output},{"code",error.code},{"message",error.message},{"line",int64_t(error.span.line)}};}
    require(nexrt::liveObjects.load()==baseline,"single reference task evaluation leaked values");
    report["revision"]=revision(p);report["live_delta"]=int64_t(0);
    std::cout<<json(std::move(report),false)<<'\n';return 0;
  }
  require(argc==1||argc==2,"expected optional new corpus directory");
  if(argc==2){corpusDirectory=fs::absolute(argv[1]);require(fs::create_directory(corpusDirectory),"corpus directory must be new");}
  runs(R"nex(
fn main()->unit!{state,task,throw,io}{
 let value:cell<i64>=cell_new(1);
 let count:i64=with_tasks(1,fn(s:task_scope)->i64!{state,task,throw}{
  let child:task<i64>=task_spawn(s,fn()->i64!{state,task}{
   task_yield();cell_write(value,42);cell_collect();return cell_read(value);
  });
  cell_collect();let output:i64=task_wait(child);assert(cell_read(value)==output);return output;
 });print(count);print(cell_read(value));
}
)nex","42\n42\n");
  runs(R"nex(
fn main()->unit!{state,task,throw,io}{
 let returned:cell<i64>=with_tasks(2,fn(s:task_scope)->cell<i64>!{state,task,throw}{
  let q:channel<cell<i64>>=channel_new<cell<i64>>(s,1);
  let job:task<cell<i64>>=task_spawn(s,fn()->cell<i64>!{state,task}{
   let value:cell<i64>=cell_new(42);assert(task_send(q,value));task_yield();return value;
  });
  let from_queue:cell<i64>=unwrap(task_recv(q));let from_task:cell<i64>=task_wait(job);
  assert(from_queue==from_task);return from_queue;
 });cell_collect();print(cell_read(returned));
}
)nex","42\n");
  runs(R"nex(
struct Failure{value:cell<i64>;}
fn main()->unit!{state,task,throw,io}{
 let value:cell<i64>=cell_new(1);
 let result:i64=with_tasks(1,fn(s:task_scope)->i64!{state,task,throw}{
  let job:task<i64>=task_spawn(s,fn()->i64!{state,task,throw}{
   task_yield();cell_write(value,7);throw(Failure(value));
  });
  try{let ignored:i64=task_wait(job);assert(false);}
  catch(error:Failure){assert(error.value==value);assert(cell_read(error.value)==7);}
  finally{task_yield();cell_write(value,cell_read(value)+1);}
  return cell_read(value);
 });print(result);
}
)nex","8\n");
  runs(R"nex(
struct Node{value:i64;next:list<cell<Node>>;}
fn main()->unit!{state,task,throw,io}{
 let node:cell<Node>=cell_new(Node(1,[]));cell_write(node,Node(1,[node]));let old:Node=cell_read(node);
 let answer:i64=with_tasks(2,fn(s:task_scope)->i64!{state,task,throw}{
  let child:task<i64>=task_spawn(s,fn()->i64!{state,task}{
   cell_collect();task_yield();let current:Node=cell_read(node);assert(current.next[0]==node);
   cell_write(node,Node(42,[node]));cell_collect();return cell_read(node).value;
  });task_yield();cell_collect();return task_wait(child);
 });assert(old.value==1&&old.next[0]==node);print(answer);
}
)nex","42\n");
  runs(R"nex(
fn main()->unit!{state,task,throw,io}{
 let value:cell<i64>=cell_new(1);let captured:fn()->i64!{state}=fn()->i64!{state}{return cell_read(value);};
 let output:i64=with_tasks(2,fn(s:task_scope)->i64!{state,task,throw}{
  let q:channel<fn()->i64!{state}>=channel_new<fn()->i64!{state}>(s,1);
  let child:task<i64>=task_spawn(s,fn()->i64!{state,task}{
   assert(task_send(q,captured));task_yield();cell_write(value,42);return 42;
  });let read:fn()->i64!{state}=unwrap(task_recv(q));let done:i64=task_wait(child);cell_collect();return read();
 });print(output);
}
)nex","42\n");
  runs(R"nex(
fn main()->unit!{state,task,throw,io}{
 let value:cell<i64>=cell_new(0);
 let ignored:i64=with_tasks(1,fn(s:task_scope)->i64!{state,task,throw}{
  let child:task<i64>=task_spawn(s,fn()->i64!{state,task}{
   try{while true{cell_write(value,cell_read(value)+1);task_yield();}}
   finally{cell_write(value,999);}return 0;
  });task_yield();assert(task_cancel(child));return 0;
 });assert(cell_read(value)>0&&cell_read(value)<999);cell_collect();print("cancelled");
}
)nex","cancelled\n");
  fails(R"nex(
fn main()->unit!{state,task,throw}{
 let value:cell<i64>=cell_new(0);
 let ignored:i64=with_tasks(1,fn(s:task_scope)->i64!{state,task,throw}{
  let child:task<i64>=task_spawn(s,fn()->i64!{state,task}{while true{cell_write(value,cell_read(value)+1);task_yield();}return 0;});
  return task_wait(child);
 });
}
)nex","E_LIMIT",180);
  fails(R"nex(
fn main()->unit!{state,task}{let first:cell<i64>=cell_new(1);let second:cell<i64>=cell_new(2);assert(cell_read(first)+cell_read(second)==3);}
)nex","E_CELL_LIMIT",1000000,{1,32,64});
  fails(R"nex(
struct Fault{value:cell<i64>;}
fn main()->unit!{state,task,throw}{let value:cell<i64>=cell_new(42);throw(Fault(value));}
)nex","E_SOURCE_EXCEPTION");
  fails(R"nex(
fn main()->cell<i64>!{state,task}{return cell_new(42);}
)nex","E_CELL_ENTRY");
  fails(R"nex(
fn main()->unit!{task,throw}{let result:i64=with_tasks(1,fn(s:task_scope)->i64!{state}{return cell_read(cell_new(42));});}
)nex","E_EFFECT");
  fails(R"nex(
fn main()->unit!{state,task,throw}{let x:cell<i64>=cell_new(1);let result:i64=with_tasks(1,fn(s:task_scope)->i64!{state,task}{let q:channel<cell<i64>>=channel_new<cell<i64>>(s,0);let v:cell<i64>=unwrap(task_recv(q));return cell_read(v);});}
)nex","E_TASK_DEADLOCK");
  runs(R"nex(
fn relay(value:cell<i64>)->cell<i64>!{task}
 ensures(answer=>answer==value){task_yield();return value;}
fn main()->unit!{state,task,throw,io}{
 let value:cell<i64>=cell_new(42);
 let result:cell<i64>=with_tasks(1,fn(s:task_scope)->cell<i64>!{task,throw}{
  let child:task<cell<i64>>=task_spawn(s,fn()->cell<i64>!{task}{return relay(value);});return task_wait(child);
 });assert(result==value);print(cell_read(result));
}
)nex","42\n");
  observesCleanup(false);observesCleanup(true);
  {
   auto p=parseVersioned("module previous;fn main()->unit!{task}{}","previous.nex",SourceLanguage::Contracts029);check(p);bool rejected=false;
   try{(void)evaluateManagedTaskReferencePrototype(p);}catch(const Error &error){require(error.code=="E_LANGUAGE_VERSION","previous language gate changed");rejected=true;}
   require(rejected,"managed task prototype accepted source029");++cases;
  }
  {
   auto p=parseVersioned("module unchecked;fn main()->unit!{state,task}{}","unchecked.nex",SourceLanguage::References030);bool rejected=false;
   try{(void)evaluateManagedTaskReferencePrototype(p);}catch(const Error &error){require(error.code=="E_CELL_STATE","unchecked program gate changed");rejected=true;}
   require(rejected,"managed task prototype accepted unchecked source");++cases;
  }
  {
   Fixture fixture;
   runs(R"nex(
server fn main()->unit!{state,task,fs,throw,io}{
 let f:file=unwrap(file_open_read("input"));let value:cell<file>=cell_new(f);
 let result:i64=with_tasks(1,server fn(s:task_scope)->i64!{state,task,fs,throw}{
  let child:task<i64>=task_spawn(s,server fn()->i64!{state,task,fs}{task_yield();cell_collect();return len(unwrap(file_read(cell_read(value),2)));});
  return task_wait(child);
 });assert(file_is_open(f));assert(file_close(f));print(result);
}
)nex","2\n",fixture.root);
   runs(R"nex(
server fn main()->unit!{state,task,fs,throw,io}{
 let value:cell<file>=with_tasks(1,server fn(s:task_scope)->cell<file>!{state,task,fs,throw}{
  let child:task<cell<file>>=task_spawn(s,server fn()->cell<file>!{state,task,fs}{
   let stored:cell<file>=cell_new(unwrap(file_open_read("input")));task_yield();cell_collect();return stored;
  });return task_wait(child);
 });cell_collect();print(len(unwrap(file_read(cell_read(value),6))));assert(file_close(cell_read(value)));
}
)nex","6\n",fixture.root);
   fails(R"nex(
server fn main()->unit!{state,task,fs,throw,io}{
 let value:cell<list<file>>=cell_new<list<file>>([]);
 let ignored:i64=with_tasks(1,server fn(s:task_scope)->i64!{state,task,fs,throw}{
  let child:task<i64>=task_spawn(s,server fn()->i64!{state,task,fs}{
   let f:file=unwrap(file_open_read("input"));cell_write(value,[f]);task_yield();return 0;
  });return task_wait(child);
 });print(file_is_open(cell_read(value)[0]));
}
)nex","E_RESOURCE_SCOPE",1000000,{},fixture.root);
   fails(R"nex(
struct Node{file:file;next:list<cell<Node>>;}
server fn main()->unit!{state,task,fs,throw}{
 let ignored:i64=with_tasks(1,server fn(s:task_scope)->i64!{state,task,fs,throw}{
  let child:task<i64>=task_spawn(s,server fn()->i64!{state,task,fs}{
   let f:file=unwrap(file_open_read("input"));let value:cell<Node>=cell_new(Node(f,[]));cell_write(value,Node(f,[value]));
   try{task_yield();cell_collect();assert(false);}finally{let written:bool=unwrap(file_write_text("wrong","finalizer"));}return 0;
  });return task_wait(child);
 });
}
)nex","E_ASSERT",1000000,{},fixture.root);
   require(!fs::exists(fixture.root/"wrong"),"fatal task ran user finally");
  }
  if(!corpusDirectory.empty()){
    writeFile((corpusDirectory/"input").string(),"abcdef");
    writeFile((corpusDirectory/"cases.json").string(),json(llvm::json::Object{{"schema","nex.reference-task-corpus/1"},{"cases",std::move(corpus)}},true));
  }
  require(runOwnerTaskRuntime()==0,"native owner-thread runtime probe failed");
  require(runNativeTaskSessionKernel()==0,"native persistent session runtime probe failed");
  std::cout<<"{\"ok\":true,\"cases\":"<<cases<<",\"owner_cases\":7,\"native_session_cases\":14}\n";
}catch(const Error &error){std::cerr<<"case "<<cases<<": "<<error.code<<": "<<error.message<<" at "<<error.span.line<<'\n';return 1;}
catch(const std::exception &error){std::cerr<<"case "<<cases<<": "<<error.what()<<'\n';return 1;}}
