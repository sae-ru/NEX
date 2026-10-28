#include "resource_regions_reference_helpers.h"
#include <functional>
#include <stop_token>

// Only this separately compiled reference adapter enables the idle hook.
// The production compiler and normal frontend contain no hook or host ABI.
namespace { std::function<void()> beforeIdle; }
namespace nex { void referenceRetirementBeforeIdleCheck(){if(beforeIdle)beforeIdle();} }

int main(){try{
 size_t cases=0;
 for(const auto &body:std::array<std::string,3>{once,scoped,R"(
  fn main()->i64 !{task}{return with_tasks(1,fn(s:task_scope)->i64 !{task}{
   let child:task<i64>=task_spawn(s,fn()->i64 !{task}{task_yield();return 42;});
   return task_wait(child);});})"}){
  Host host;host.executor=std::make_shared<ResourceExecutor>();auto gate=std::make_shared<Gate>();size_t boundaries=0;
  host.action=[&](size_t,const auto &authority)->std::optional<TaskReferenceExternalRequest>{host.aliases.push_back(host.make(authority,gate));return {};};
  beforeIdle=[&]{if(boundaries++)return;require(gate->wait(),"finalizer did not reach its physical gate");
   require(*host.destroyed==0&&host.physical.used()==1,"fence was already physically complete before the idle check");
   gate->open();host.executor->finish();require(*host.destroyed==1&&*host.pins==1&&host.physical.used()==0,"controlled physical completion did not settle");};
  try{require(evaluate(source(body),host).value.scalar==42,"idle transition changed source result");}
  catch(...){gate->open();beforeIdle={};throw;}
  beforeIdle={};require(boundaries>=1&&host.taskRetirements>=1,"controlled idle boundary was not exercised");host.empty();++cases;
 }
 {
  Host host;host.executor=std::make_shared<ResourceExecutor>();auto gate=std::make_shared<Gate>();std::stop_source cancel;host.cancellation=cancel.get_token();size_t boundaries=0;
  host.action=[&](size_t,const auto &authority)->std::optional<TaskReferenceExternalRequest>{host.aliases.push_back(host.make(authority,gate));return {};};
  beforeIdle=[&]{if(boundaries++)return;require(gate->wait(),"cancel cleanup never entered its gate");gate->open();host.executor->finish();require(*host.destroyed==1&&host.physical.used()==0,"cancel fence did not settle");};
  try{sourceRejected("E_CANCELLED",[&]{evaluate(source("fn main()->i64 !{task}{task_yield();task_yield();return 42;}"),host,
   [&](size_t,const TaskTransition &transition){if(!host.aliases.empty()&&transition.operation=="task_yield")cancel.request_stop();});});}
  catch(...){gate->open();beforeIdle={};throw;}
  beforeIdle={};require(boundaries>=1&&*host.pins==1,"cancel idle handoff was not exercised");host.empty();++cases;
 }
 std::cout<<"controlled reference retirement handoffs="<<cases<<"\n";return 0;
}catch(const std::exception &error){beforeIdle={};std::cerr<<error.what()<<"\n";return 1;}}
