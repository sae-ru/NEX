#include "nex/task_reference.h"
#include "nex/task_frontend.h"
#include <chrono>
#include <iostream>
#include <thread>

using namespace nex;
namespace {
size_t cases=0;
void require(bool value,const std::string &message){if(!value)throw std::runtime_error(message);}
Program source(const std::string &body){auto p=parse("module reference_limits;\n"+body,"reference_limits.nex");check(p);return p;}
template<class F>Error rejected(const std::string &code,F run){
  auto before=nexrt::liveObjects.load();
  try{run();}catch(const Error &error){
    require(error.code==code,"expected "+code+", got "+error.code+": "+error.what());
    require(nexrt::liveObjects.load()==before,"reference limit failure retained owned values");
    ++cases;return error;
  }
  throw std::runtime_error("expected "+code);
}
const std::string finite=R"(
fn main()->i64 !{task,throw}{return with_tasks(2,fn(scope:task_scope)->i64 !{task,throw}{
 let queue:channel<str>=channel_new<str>(scope,0);
 let held:list<str>=["owned","🧠"];
 let child:task<i64>=task_spawn(scope,fn()->i64 !{task}{task_yield();assert(task_send(queue,held[1]));return 40;});
 assert(unwrap(task_recv(queue))=="🧠");assert(task_close(queue));return task_wait(child)+2;
});}
)";
void selfTest(){
  nexrt::TaskExecutionLimits limits{1000000,5000,3};
  auto p=source(finite);auto before=nexrt::liveObjects.load();
  {
    // The explicit configuration overrides the old numeric API argument.
    auto result=evaluateTaskReference(p,"main",{},1,{},&limits);
    require(result.value.scalar==42&&result.steps>1,"explicit reference steps did not override numeric argument");
    require(result.limits==limits&&result.executionWorkers==1,"reference worker/control metadata is not honest");
    require(result.tasks==2&&result.scopes==1&&result.channels==1,"finite structured program did not execute");
  }
  require(nexrt::liveObjects.load()==before,"finite reference retained owned values");++cases;
  auto evaluated=evaluate(p,"main",1,&limits);
  require(evaluated.value.getAsInteger()==42,"public evaluate did not forward task limits");++cases;
  rejected("E_LIMIT",[&]{evaluateTaskReference(p,"main",{},0);});
  rejected("E_LIMIT",[&]{evaluateTaskReference(p,"main",{},1);});
  auto small=limits;small.steps=1;
  rejected("E_LIMIT",[&]{evaluateTaskReference(p,"main",{},1000000,{},&small);});
  for(auto bad:{nexrt::TaskExecutionLimits{0,1,1},nexrt::TaskExecutionLimits{1,0,1},
                nexrt::TaskExecutionLimits{1,1,0},nexrt::TaskExecutionLimits{1,1,17},
                nexrt::TaskExecutionLimits{1,3600001,1},
                nexrt::TaskExecutionLimits{nexrt::maximumTaskExecutionSteps+1,1,1}})
    rejected("E_OPTION",[&]{evaluateTaskReference(p,"main",{},1000000,{},&bad);});
  auto pure=source("fn main()->i64{return 42;}fn unused()->unit !{task}{task_yield();}");
  rejected("E_OPTION",[&]{evaluate(pure,"main",limits.steps,&limits);});
  // A reachable task callable selects task execution even if this outer entry
  // is pure. Unreachable task declarations above do not authorize controls.
  auto factory=source("fn main()->i64{let unused:fn()->unit !{task}=fn()->unit !{task}{task_yield();};return 42;}");
  require(evaluate(factory,"main",limits.steps,&limits).value.getAsInteger()==42,"reachable callable did not select reference task control");++cases;

  auto timed=nexrt::TaskExecutionLimits{nexrt::maximumTaskExecutionSteps,10,1};
  auto looping=source(R"(
fn spin()->i64{let held:list<str>=["owned","🧠"];var n:i64=0;while true{assert(len(held)==2);n=n+1;}return n;}
fn main()->i64 !{io,task}{print("before");return spin();}
)");
  auto start=std::chrono::steady_clock::now();
  auto timeout=rejected("E_TIMEOUT",[&]{evaluate(looping,"main",timed.steps,&timed);});
  require(timeout.output=="before\n","deadline discarded source output produced before the pure helper");
  require(timeout.span.file=="reference_limits.nex"&&timeout.span.line>0,"pure-helper timeout has no source location");
  require(std::chrono::steady_clock::now()-start<std::chrono::seconds(3),"pure helper escaped the root deadline");

  auto atomLoop=source("fn spin(seed:i64)->i64{var n:i64=seed;while true{n=n+1;}return n;}fn main()->i64 !{task}{let values:list<i64>=parallel_map([1],spin,1);return values[0];}");
  rejected("E_TIMEOUT",[&]{evaluateTaskReference(atomLoop,"main",{},timed.steps,{},&timed);});

  auto nested=source("fn main()->i64 !{task,throw}{return with_tasks(1,fn(outer:task_scope)->i64 !{task,throw}{return with_tasks(1,fn(inner:task_scope)->i64{return 42;});});}");
  auto shared=nexrt::TaskExecutionLimits{nexrt::maximumTaskExecutionSteps,200,1};unsigned scopes=0;
  rejected("E_TIMEOUT",[&]{evaluateTaskReference(nested,"main",{},shared.steps,[&](size_t,const TaskTransition &request){
    if(request.operation=="with_tasks"){++scopes;std::this_thread::sleep_for(std::chrono::milliseconds(125));}
  },&shared);});
  require(scopes==2,"nested scope deadline fixture did not reach its inner request");

  auto priority=source(R"(
fn main()->i64 !{task,throw}{return with_tasks(2,fn(scope:task_scope)->i64 !{task}{
 let failed:task<i64>=task_spawn(scope,fn()->i64{return 1/0;});
 let pending:task<str>=task_spawn(scope,fn()->str !{task}{let held:list<str>=["owned","🧠"];while true{task_yield();}return held[0];});
 return 42;
});}
)");
  rejected("E_TIMEOUT",[&]{evaluateTaskReference(priority,"main",{},timed.steps,{},&timed);});

  auto errorResult=source("fn main()->result<i64> !{task,throw}{return with_tasks(1,fn(scope:task_scope)->result<i64> !{task}{let pending:task<unit>=task_spawn(scope,fn()->unit !{task}{while true{task_yield();}});return err<i64>(\"E_EXPECTED\",\"expected\");});}");
  bool observed=false;auto resultLimit=nexrt::TaskExecutionLimits{nexrt::maximumTaskExecutionSteps,50,1};
  rejected("E_TIMEOUT",[&]{evaluateTaskReference(errorResult,"main",{},resultLimit.steps,[&](size_t,const TaskTransition &request){
    if(request.kind==TaskTransition::Done&&!observed){observed=true;std::this_thread::sleep_for(std::chrono::milliseconds(75));}
  },&resultLimit);});
  require(observed,"result-return deadline fixture did not observe a callback return");

  {auto recovered=evaluateTaskReference(p,"main",{},limits.steps,{},&limits);require(recovered.value.scalar==42,"control failure leaked into a later reference invocation");}
  require(nexrt::liveObjects.load()==0,"reference limit tests left owned values");++cases;
}
}
int main()try{
  selfTest();
  std::cout<<json(llvm::json::Object{{"ok",true},{"cases",int64_t(cases)},
    {"pure_helpers_and_atoms_deadline",true},{"nested_absolute_deadline",true},
    {"resource_priority_and_cleanup",true},{"reference_execution_workers",1},
    {"step_threshold_backend_parity_claim",false}})<<'\n';return 0;
}catch(const std::exception &error){std::cerr<<"after "<<cases<<" checks: "<<error.what()<<'\n';return 1;}
