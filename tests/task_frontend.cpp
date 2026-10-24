#include "nex/task_frontend.h"
#include "nex/backend.h"
#include "nex/web.h"
#include <filesystem>
#include <fstream>
#include <iostream>

using namespace nex;
namespace {
unsigned cases=0;
void require(bool condition,const std::string &message){if(!condition)throw std::runtime_error(message);}
Program checked(const std::string &body){auto p=parseTaskPrototype("module tasks;\n"+body,"tasks.nex");check(p);return p;}
template<class F>void rejects(const char *code,F action){
  try{action();}catch(const Error &error){require(error.code==code,std::string("expected ")+code+", got "+error.code+": "+error.what());++cases;return;}
  throw std::runtime_error(std::string("expected ")+code);
}
void accepts(const std::string &body){checked(body);++cases;}
void rejectsSource(const char *code,const std::string &body){rejects(code,[&]{checked(body);});}
}
int main(int argc,char **argv)try{
  require(argc==2,"fixture path required");
  accepts(R"(
fn main()->i64 !{task}{
  return with_tasks(2,fn(scope:task_scope)->i64 !{task}{
    let queue:channel<i64>=channel_new(scope,0);
    let sender:task<unit>=task_spawn(scope,fn()->unit !{task}{assert(task_send(queue,42));});
    let value:i64=unwrap(task_recv(queue));task_wait(sender);return value;
  });
})");
  accepts(R"(
fn empty<T>()->list<T>{return [];}
fn join<T>(pending:task<T>)->T !{task}{return task_wait(pending);}
fn work(scope:task_scope)->list<i64> !{task}{
  let pending:task<list<i64>>=task_spawn(scope,empty);return join(pending);
}
fn main()->unit !{task}{let values:list<i64>=with_tasks(2,work);assert(len(values)==0);}
)");
  accepts(R"(
fn preserve<F<_>,T>(value:F<T>)->F<T>{return value;}
fn wait(pending:task<i64>)->i64 !{task}{return task_wait(preserve(pending));}
fn pass(queue:channel<str>)->channel<str>{return preserve(queue);}
)");
  accepts(R"(
client fn work(scope:task_scope)->bool !{task}{
 let queue:channel<str>=channel_new<str>(scope,2);
 let pending:task<unit>=task_spawn(scope,client fn()->unit !{task}{task_yield();});
 assert(task_cancel(pending));task_wait(pending);return task_close(queue);
}
client fn main()->unit !{task}{assert(with_tasks(1,work));}
)");
  accepts(R"(
fn recover(pending:task<result<i64>>)->result<i64> !{task}{
 let value:i64=task_wait(pending)?;return ok(value+1);
}
fn receive(queue:channel<i64>)->result<i64> !{task}{let value:i64=task_recv(queue)?;return ok(value);}
fn scope()->task_scope !{task}{return current_task_scope();}
)");
  accepts(R"(
fn outer()->i64 !{task}{return with_tasks(2,fn(parent:task_scope)->i64 !{task}{
 let pending:task<i64>=task_spawn(parent,fn()->i64 !{task}{task_yield();return 40;});
 return with_tasks(1,fn(child:task_scope)->i64 !{task}{return task_wait(pending)+2;});
});}
)");
  accepts("fn async()->i64{return 1;} fn await()->i64{return async();} fn spawn()->i64{return await();}");
  auto p=checked("struct Hidden<T>{value:i64;} struct Box{value:channel<i64>;} fn main()->unit !{task}{task_yield();}");
  auto phantom=Type::record("Hidden");phantom.arguments={Type::TaskScope};phantom=resolveType(p,phantom);
  auto box=resolveType(p,Type::record("Box"));
  for(const auto &type:{Type(Type::TaskScope),Type::task(Type::Unit),Type::channel(Type::I64),phantom,box,Type::function({},Type::TaskScope)}){
    require(type.heap()&&containsTaskAuthority(p,type),"authority traversal must include phantom types and function signatures");
    require(!satisfiesConstraint(p,type,"wire"),"task authority cannot satisfy wire");
    rejects("E_TYPE",[&]{wireSchema(p,type);});
  }
  require(!containsTaskAuthority(p,Type::function({},Type::I64,"shared",{"task"})),"effect alone is not captured authority");++cases;
  rejectsSource("E_EFFECT","fn main()->unit{task_yield();}");
  rejectsSource("E_EFFECT","fn suspend()->unit !{task}{task_yield();} fn main()->unit{suspend();}");
  rejectsSource("E_EFFECT","fn main(callback:fn()->unit !{task})->unit{callback();}");
  rejectsSource("E_EFFECT","fn main(s:task_scope)->unit !{task}{task_spawn(s,fn()->unit !{io}{print(1);});}");
  rejectsSource("E_TASK_TYPE","fn main(s:task_scope)->unit !{task}{task_spawn(s,fn(x:i64)->i64{return x;});}");
  rejectsSource("E_REALM","fn main(s:task_scope)->unit !{task}{task_spawn(s,client fn()->i64{return 1;});}");
  rejectsSource("E_TYPE","fn main(s:task_scope)->unit !{task}{let q:channel<i64>=channel_new(s,1);task_send(q,true);}");
  rejectsSource("E_INFER","fn main(s:task_scope)->unit !{task}{channel_new(s,1);}");
  rejectsSource("E_TYPE","fn main(s:task_scope)->unit !{task}{channel_new<unit>(s,1);}");
  rejectsSource("E_GENERIC_ARITY","fn main(s:task_scope)->unit !{task}{channel_new<i64,bool>(s,1);}");
  rejectsSource("E_ARITY","fn main()->unit !{task}{current_task_scope(1);}");
  rejectsSource("E_TASK_TYPE","fn main()->unit !{task}{task_wait(1);}");
  rejectsSource("E_TASK_TYPE","server fn main(s:task_scope)->unit !{task}{channel_new<file>(s,1);}");
  rejectsSource("E_TASK_TYPE",R"(
server fn main(s:task_scope,f:file)->unit !{task}{
 task_spawn(s,server fn()->i64{let copy:file=f;return 1;});
})");
  rejectsSource("E_PARALLEL_TYPE","fn main(values:list<task<i64>>)->unit{parallel_map(values,fn(p:task<i64>)->i64{return 1;},2);}");
  rejectsSource("E_PARALLEL_TYPE","fn main(s:task_scope)->unit{parallel_map([1],fn(x:i64)->i64{let saved:task_scope=s;return x;},2);}");
  rejectsSource("E_GENERIC_BOUND","fn send<T:wire>(v:T)->T{return v;} fn main(s:task_scope)->unit{send(s);}");
  rejectsSource("E_TASK_TYPE","server extern fn wait(p:task<i64>)->i64 !{ffi}=foreign(\"m\",\"f\",\"0000000000000000000000000000000000000000000000000000000000000000\");");
  rejectsSource("E_TASK_TYPE","server extern fn wait()->i64 !{ffi,task}=foreign(\"m\",\"f\",\"0000000000000000000000000000000000000000000000000000000000000000\");");
  rejectsSource("E_DUPLICATE","fn task_wait()->i64{return 1;}");
  rejectsSource("E_DUPLICATE","struct task_scope{value:i64;}");
  rejectsSource("E_DUPLICATE","fn invalid<channel>(value:channel)->channel{return value;}");
  rejects("E_TASK_UNIMPLEMENTED",[&]{revision(p);});
  rejects("E_TASK_UNIMPLEMENTED",[&]{sourceBundle(p);});
  rejects("E_TASK_UNIMPLEMENTED",[&]{dependencyLock(p);});
  rejects("E_TASK_UNIMPLEMENTED",[&]{evaluate(p,"main",100);});
  rejects("E_TASK_UNIMPLEMENTED",[&]{emitMLIR(p);});
  rejects("E_TASK_UNIMPLEMENTED",[&]{emitWasmMLIR(p,"main",false);});
  rejects("E_TASK_UNIMPLEMENTED",[&]{validateNativeBuildEntry(p,{});});
  rejects("E_TASK_UNIMPLEMENTED",[&]{emitTypeScript(p,{{"main","main"}});});
  auto absent=std::filesystem::temp_directory_path()/"nex-task-prototype-must-not-build";
  require(!std::filesystem::exists(absent),"build guard output already exists");
  rejects("E_TASK_UNIMPLEMENTED",[&]{build(p,absent.string(),{});});
  require(!std::filesystem::exists(absent),"private native build created output before guard");
  auto fixture=llvm::json::parse(readFile(argv[1]));require(bool(fixture),"invalid baseline metadata");
  auto object=fixture->getAsObject();require(object&&object->getString("source"),"baseline source missing");
  auto source=object->getString("source")->str();
  auto legacy=loadVersionedBundle(llvm::json::Object{{"schema","nex.sources/1"},{"entry","main.nex"},{"files",llvm::json::Object{{"main.nex",source}}}},std::filesystem::temp_directory_path().string(),"0.18");
  auto baseline=object->getString("revision");require(baseline&&revision(legacy)==*baseline,"old0.18 canonical revision changed");++cases;
  require(evaluate(legacy,"legacy_task_names::answer",10000).value==llvm::json::Value(int64_t(43)),"legacy names no longer execute");++cases;
  rejects("E_DUPLICATE",[&]{auto incompatible=parseTaskPrototype(source,"legacy.nex");check(incompatible);});
  require(builtinNames(false).count("task_wait")==0&&builtinNames(true).count("task_wait")==1,"legacy and task builtin sets are not distinct");++cases;
  auto directory=std::filesystem::path(createTemporaryDirectory("nex-task-frontend"));
  try{
    writeFile((directory/"worker.nex").string(),"module worker; pub fn compute()->i64 !{task}{task_yield();return 42;}");
    writeFile((directory/"main.nex").string(),"module app; import \"./worker.nex\" as w; fn main()->i64 !{task}{return with_tasks(2,fn(s:task_scope)->i64 !{task}{let p:task<i64>=task_spawn(s,w::compute);return task_wait(p);});}");
    auto loaded=loadTaskPrototype((directory/"main.nex").string(),directory.string());
    require(loaded.taskPrototype&&loaded.functions.size()>=3&&loaded.units.size()==2,"task module assembly lost its mode or imports");
    require(loaded.function("app::main").effects.contains("task"),"task effect lost during module binding");++cases;
    rejects("E_TASK_UNIMPLEMENTED",[&]{sourceBundle(loaded);});
    auto publicProgram=loadProgram((directory/"main.nex").string(),directory.string());
    require(publicProgram.sourceLanguage==currentSourceLanguage&&publicProgram.taskPrototype&&std::string(programLanguage(publicProgram))==languageVersion,"ordinary loader did not select the current public source syntax");++cases;
    require(evaluate(publicProgram,"app::main",10000).value==llvm::json::Value(int64_t(42)),"public020 reference execution lost task module semantics");++cases;
    require(!std::filesystem::exists(directory/".nex"),"private source checking opened a graph store");++cases;
    std::filesystem::remove_all(directory);
  }catch(...){std::filesystem::remove_all(directory);throw;}
  std::cout<<"{\"ok\":true,\"cases\":"<<cases<<",\"public_source_tasks\":true,\"private018_guards\":true}\n";return 0;
}catch(const std::exception &error){std::cerr<<"after "<<cases<<" cases: "<<error.what()<<'\n';return 1;}
