#include "nex/task_reference.h"
#include "nex/task_frontend.h"
#include "nex_task_values.h"
#include <filesystem>
#include <iostream>

using namespace nex;
namespace {
size_t cases=0;
nexrt::Value nativeCapture;
nexrt::TaskBody captureNative(nexrt::TaskGroup &group,nexrt::Value,nexrt::Value){
  auto scope=group.openScope(1);nativeCapture=nexrt::taskScopeValue(group,scope);
  co_await group.leaveScope(scope);co_return nexrt::Value(42);
}
void require(bool value,const std::string &message){if(!value)throw std::runtime_error(message);}
template<class F>void rejects(const std::string &code,F action){
  try{action();}catch(const Error &e){require(e.code==code,"expected "+code+", got "+e.code+": "+e.what());++cases;return;}
  catch(const nexrt::DataError &e){require(e.code==code,"expected "+code+", got "+e.code);++cases;return;}
  throw std::runtime_error("expected "+code);
}
Program source(const std::string &body){auto p=parseTaskPrototype("module reference;\n"+body,"reference.nex");check(p);return p;}
void check(const std::string &body,const std::string &expected,const std::string &output=""){
  auto p=source(body);auto before=nexrt::liveObjects.load();
  {auto result=evaluateTaskReference(p);require(nexrt::representation(result.value)==expected,"reference value differs");require(result.output==output,"reference output differs");require(result.steps>0,"unaccounted reference work");}
  require(nexrt::liveObjects.load()==before,"reference execution leaked owned values");++cases;
}
void selfTest(){
  const std::string descend="fn descend(s:task_scope,n:i64)->i64 !{task}{if n==0{return 42;}let next:task<i64>=task_spawn(s,fn()->i64 !{task}{return descend(s,n-1);});return task_wait(next);}";
  check(descend+"fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{return descend(s,255);});}","42");
  rejects("E_LIMIT",[&]{evaluateTaskReference(source(descend+"fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{return descend(s,256);});}"));});
  check("fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let t:task<i64>=task_spawn(s,fn()->i64 !{task}{task_yield();return 42;});return task_wait(t);});}","42");
  for(int n:{0,1,7})check("fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let q:channel<i64>=channel_new<i64>(s,"+std::to_string(n)+");let writer:task<i64>=task_spawn(s,fn()->i64 !{task}{var n:i64=0;while n<20{assert(task_send(q,n));n=n+1;}assert(task_close(q));return n;});var total:i64=0;var open:bool=true;while open{let r:result<i64>=task_recv(q);if is_ok(r){total=total+unwrap(r);}else{open=false;}}assert(task_wait(writer)==20);assert(!task_close(q));return total;});}","190");
  check("fn main()->result<i64> !{task}{return with_tasks(1,fn(s:task_scope)->result<i64> !{task}{let t:task<unit>=task_spawn(s,fn()->unit !{task}{while true{task_yield();}});task_yield();return err<i64>(\"E_STOP\",\"stop\");});}","{\"error\":{\"code\":\"E_STOP\",\"message\":\"stop\"}}");
  check("fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let q:channel<i64>=channel_new<i64>(s,0);let a:task<unit>=task_spawn(s,fn()->unit !{task}{assert(!task_send(q,1));});task_yield();assert(task_close(q));task_wait(a);return 42;});}","42");
  check("fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let t:task<i64>=task_spawn(s,fn()->i64 !{task}{while true{task_yield();}return 0;});assert(task_cancel(t));return 42;});}","42");
  rejects("E_TASK_SCOPE",[&]{evaluateTaskReference(source("struct Box{scopes:list<task_scope>;}fn main()->result<Box> !{task}{return with_tasks(1,fn(s:task_scope)->result<Box> !{task}{return ok(Box([s]));});}"));});
  rejects("E_DIV_ZERO",[&]{evaluateTaskReference(source("fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let t:task<i64>=task_spawn(s,fn()->i64 !{task}{task_yield();return 1/0;});return 42;});}"));});
  rejects("E_LIMIT",[&]{evaluateTaskReference(source("fn main()->unit !{task}{while true{task_yield();}}"),"main",{},100);});
  rejects("E_LIMIT",[&]{evaluateTaskReference(source("fn work()->unit !{task}{var i:i64=0;while i<25{task_yield();i=i+1;}}fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{task_spawn(s,work);task_spawn(s,work);task_spawn(s,work);task_spawn(s,work);return 42;});}"),"main",{},700);});
  {
    std::string wide="fn nested(n:i64)->i64 !{task}{if n==0{return 42;}let answer:i64=with_tasks(1,fn(s:task_scope)->i64 !{task}{return nested(n-1);});";
    for(size_t i=0;i<8192;++i)wide+="task_yield();";
    wide+="return answer;}fn main()->i64 !{task}{return nested(40);}";
    rejects("E_LIMIT",[&]{evaluateTaskReference(source(wide));});
  }
  rejects("E_TASK_DEADLOCK",[&]{evaluateTaskReference(source("fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let q:channel<i64>=channel_new<i64>(s,0);return unwrap(task_recv(q));});}"));});
  check("fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let q:channel<i64>=channel_new<i64>(s,0);let a:task<unit>=task_spawn(s,fn()->unit !{task}{assert(task_send(q,20));});let b:task<unit>=task_spawn(s,fn()->unit !{task}{assert(task_send(q,22));});task_yield();let x:i64=unwrap(task_recv(q));let y:i64=unwrap(task_recv(q));task_wait(a);task_wait(b);assert(x==20&&y==22);return x+y;});}","42");
  check("fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let q:channel<str>=channel_new<str>(s,0);let a:task<unit>=task_spawn(s,fn()->unit !{task}{task_send(q,\"owned pending send\");});task_yield();assert(task_cancel(a));assert(task_close(q));assert(!is_ok(task_recv(q)));return 42;});}","42");
  check("fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let q:channel<str>=channel_new<str>(s,0);let a:task<str>=task_spawn(s,fn()->str !{task}{return unwrap(task_recv(q));});task_yield();assert(task_cancel(a));let b:task<str>=task_spawn(s,fn()->str !{task}{return unwrap(task_recv(q));});assert(task_send(q,\"live receiver\"));assert(task_wait(b)==\"live receiver\");return 42;});}","42");
  rejects("E_DIV_ZERO",[&]{evaluateTaskReference(source("fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let a:task<unit>=task_spawn(s,fn()->unit !{task}{task_yield();let b:task<i64>=task_spawn(s,fn()->i64{return 1/0;});});return 42;});}"));});
  check("fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let a:task<unit>=task_spawn(s,fn()->unit !{task}{let b:task<unit>=task_spawn(s,fn()->unit !{task}{while true{task_yield();}});while true{task_yield();}});task_yield();task_yield();assert(task_cancel(a));return 42;});}","42");
  check("fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let q:channel<i64>=channel_new<i64>(s,2);assert(task_send(q,20));assert(task_send(q,22));assert(task_close(q));let x:i64=unwrap(task_recv(q));let y:i64=unwrap(task_recv(q));assert(!is_ok(task_recv(q)));assert(!task_send(q,0));return x+y;});}","42");
  rejects("E_TASK_CYCLE",[&]{evaluateTaskReference(source("fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let q:channel<task<i64>>=channel_new<task<i64>>(s,1);let a:task<i64>=task_spawn(s,fn()->i64 !{task}{return with_tasks(1,fn(inner:task_scope)->i64 !{task}{let b:task<i64>=task_spawn(inner,fn()->i64 !{task}{return task_wait(unwrap(task_recv(q)));});return 42;});});task_send(q,a);return task_wait(a);});}"));});
  rejects("E_LIMIT",[&]{evaluateTaskReference(source("fn main()->unit !{task}{var i:i64=0;while i<1025{with_tasks(1,fn(s:task_scope)->unit{});i=i+1;}}"));});
  rejects("E_LIMIT",[&]{evaluateTaskReference(source("fn main()->unit !{task}{with_tasks(1,fn(s:task_scope)->unit !{task}{var i:i64=0;while i<1025{channel_new<i64>(s,0);i=i+1;}});}"));});
  rejects("E_LIMIT",[&]{evaluateTaskReference(source("fn main()->unit !{task}{with_tasks(1,fn(s:task_scope)->unit !{task}{channel_new<i64>(s,65536);channel_new<i64>(s,1);});}"));});
  rejects("E_LIMIT",[&]{evaluateTaskReference(source("fn main()->unit !{task}{with_tasks(1,fn(s:task_scope)->unit !{task}{var i:i64=0;while i<4096{task_spawn(s,fn()->unit{});i=i+1;}});}"));});
  rejects("E_TASK_VALUE",[&]{auto file=nexrt::Value(nexrt::diagnosticFile(1));evaluateTaskReference(source("server fn main(f:file)->unit{}"),"main",{file});});
  auto forged=std::make_shared<nexrt::Data>(nexrt::Data::Record);forged->kind=nexrt::Data::TaskScope;
  rejects("E_TASK_VALUE",[&]{nexrt::taskData(nexrt::Value(forged),nexrt::Data::TaskScope);});
  rejects("E_TASK_VALUE",[&]{evaluateTaskReference(source("fn main(s:task_scope)->unit{}"),"main",{nexrt::Value(forged)});});forged.reset();
  {nexrt::RequestScope request;nexrt::TaskGroup group(1);require(group.join(group.spawn(captureNative)).scalar==42,"native family fixture failed");group.finish();}
  require(nativeCapture.object->taskOwnerFamily()==nexrt::Data::TaskOwnerFamily::Native,"native family missing");
  rejects("E_TASK_VALUE",[&]{evaluateTaskReference(source("fn main(s:task_scope)->unit{}"),"main",{nativeCapture});});nativeCapture={};
  // Capture a genuine reference payload while its scope is live. Native code
  // must reject it before its final native TaskData cast. It remains revoked
  // after reference teardown, including when hidden inside another aggregate.
  nexrt::Value captured;
  auto p=source("fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{let t:task<i64>=task_spawn(s,fn()->i64{return 42;});return task_wait(t);});}");
  evaluateTaskReference(p,"main",{},1000000,[&](size_t,const TaskTransition &r){if(r.operation=="task_spawn"){
    captured=r.arguments[0];require(captured.object->taskOwnerFamily()==nexrt::Data::TaskOwnerFamily::Reference,"reference owner family missing");
    rejects("E_TASK_VALUE",[&]{nexrt::taskData(captured,nexrt::Data::TaskScope);});
    rejects("E_RUNTIME",[&]{auto sliced=std::make_shared<nexrt::Data>(*captured.object);(void)sliced;});
    rejects("E_TASK_SCOPE",[&]{evaluateTaskReference(source("fn main(s:task_scope)->unit{}"),"main",{captured});});
  }});
  rejects("E_TASK_SCOPE",[&]{evaluateTaskReference(source("fn main(s:task_scope)->i64 !{task}{return 42;}"),"main",{captured});});
  auto box=std::make_shared<nexrt::Data>(nexrt::Data::List);box->values.push_back(captured);
  rejects("E_TASK_SCOPE",[&]{evaluateTaskReference(source("fn main(s:list<task_scope>)->i64 !{task}{return 42;}"),"main",{nexrt::Value(box)});});
  box.reset();captured={};
  require(nexrt::liveObjects.load()==0,"self-tests left owned reference/native payloads");
}
}
int main(int argc,char **argv)try{
  if(argc==1){selfTest();std::cout<<json(llvm::json::Object{{"ok",true},{"cases",int64_t(cases)},{"independent_ast_scheduler",true},{"reference_dispatch_uses_native_scheduler",false},{"native_family_fixture",true},{"public_source_tasks",false}})<<'\n';return 0;}
  auto path=std::filesystem::absolute(argv[1]);
  // Public backend agreement must use the ordinary checked loader. Private
  // prototype fixtures retain their independent parser and self-tests.
  const bool ordinary=argc>2&&std::string(argv[2])=="ordinary";
  auto p=ordinary?loadProgram(path.string(),path.parent_path().string(),false):loadTaskPrototype(path.string(),path.parent_path().string());
  std::vector<nexrt::Value> arguments;if(argc>2&&std::string(argv[2])=="parameter")arguments.emplace_back(21);
  TaskReferenceObserver observer;
  if(argc>2&&std::string(argv[2])=="cancel")observer=[](size_t job,const TaskTransition &r){if(job==0&&r.operation=="task_yield"&&r.callDepth>1)throw Error("E_CANCELLED","host canceled reference job before resume",r.span);};
  std::string representation,output;uint64_t steps=0;
  {auto result=evaluateTaskReference(p,"main",arguments,1000000,std::move(observer));representation=nexrt::representation(result.value);output=result.output;steps=result.steps;}
  require(nexrt::liveObjects.load()==0,"reference source run leaked owned values");
  std::cout<<json(llvm::json::Object{{"ok",true},{"representation",representation},{"stdout",output},{"steps",int64_t(steps)}})<<'\n';return 0;
}catch(const Error &e){
  if(nexrt::liveObjects.load()!=0){std::cerr<<"reference trap leaked owned values\n";return 2;}
  std::cout<<json(llvm::json::Object{{"ok",false},{"code",e.code},{"line",int64_t(e.span.line)},{"message",e.what()},{"stdout",e.output}})<<'\n';return argc==1?1:0;
}catch(const std::exception &e){std::cerr<<"after "<<cases<<" checks: "<<e.what()<<'\n';return 2;}
