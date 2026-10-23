#include "nex_task_profile.h"
#include <algorithm>
#include <array>
#include <atomic>
#include <barrier>
#include <cstdint>
#include <exception>
#include <iostream>
#include <limits>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <thread>
#include <type_traits>
#include <utility>
#include <vector>

namespace {
std::atomic<size_t> assertions{0};
std::vector<std::string> passed;
std::string currentCase;
void require(bool condition,const char *expression,int line){
  ++assertions;
  if(!condition)throw std::runtime_error(currentCase+":"+std::to_string(line)+": "+expression);
}
#define REQUIRE(expression) require(bool(expression),#expression,__LINE__)
template<class F>void test(const char *name,F action){
  currentCase=name;action();passed.emplace_back(name);
}
// Clock injection and cases below exercise only the private collector API.
// No generated source, scheduler, RequestScope or legacy profiler is involved.
using namespace nexrt;
const std::array<TaskProfileSite,3> sites{{
  {"root","collector.nex","root-content",1},
  {"helper","collector.nex","helper-content",2},
  {"child","collector.nex","child-content",3}
}};
thread_local TaskProfileClockSample point{1,1,1,true,true};
TaskProfileClockSample sample(void *)noexcept{return point;}
TaskProfileClock clock(){return {sample,nullptr};}
void at(uint64_t wall,uint64_t cpu,uint64_t thread=1,bool wallAvailable=true,bool cpuAvailable=true){
  point={wall,cpu,thread,wallAvailable,cpuAvailable};
}
const TaskProfileTaskRecord &taskRecord(const TaskProfileSnapshot &snapshot,uint64_t id){
  auto found=std::find_if(snapshot.tasks.begin(),snapshot.tasks.end(),[&](const auto &record){return record.id==id;});
  REQUIRE(found!=snapshot.tasks.end());return *found;
}
const TaskProfileInvocationRecord &callRecord(const TaskProfileSnapshot &snapshot,uint64_t id){
  auto found=std::find_if(snapshot.invocations.begin(),snapshot.invocations.end(),[&](const auto &record){return record.id==id;});
  REQUIRE(found!=snapshot.invocations.end());return *found;
}
void balanced(const TaskProfileSnapshot &snapshot,bool clean=true){
  REQUIRE(snapshot.enabled);
  if(clean){
    REQUIRE(!snapshot.drops.incomplete);
    REQUIRE(snapshot.drops.tasks==0&&snapshot.drops.invocations==0&&snapshot.drops.events==0&&snapshot.drops.guards==0&&snapshot.drops.suppressedHooks==0);
    REQUIRE(snapshot.drops.clockFailures==0&&snapshot.drops.invalidTransitions==0&&snapshot.drops.counterOverflows==0);
  }
  std::set<uint64_t> tasks,invocations;
  for(const auto &record:snapshot.tasks){
    REQUIRE(record.id!=0&&tasks.insert(record.id).second);
    REQUIRE(record.terminal&&record.activeInvocations==0);
  }
  for(const auto &record:snapshot.invocations){
    REQUIRE(record.id!=0&&invocations.insert(record.id).second);
    REQUIRE(tasks.count(record.taskId)==1);
    REQUIRE(record.site<snapshot.functions.size());
    REQUIRE(record.outcome!=TaskProfileInvocationOutcome::Active);
    REQUIRE(record.inclusiveCpuNs>=record.selfCpuNs);
    REQUIRE(record.activeElapsedNs>=record.selfActiveElapsedNs);
  }
  for(const auto &record:snapshot.invocations){
    if(record.parentId){
      const auto &parent=callRecord(snapshot,record.parentId);
      REQUIRE(parent.taskId==record.taskId);
      std::set<uint64_t> chain{record.id};auto next=record.parentId;
      while(next){REQUIRE(chain.insert(next).second);next=callRecord(snapshot,next).parentId;}
    }
  }
  for(const auto &record:snapshot.tasks)if(record.spawningInvocationId)
    REQUIRE(invocations.count(record.spawningInvocationId)==1);
  for(const auto &record:snapshot.segments){
    REQUIRE(tasks.count(record.taskId)==1);
    REQUIRE(invocations.count(record.invocationId)==1);
    REQUIRE(record.threadId!=0);
  }
  for(const auto &record:snapshot.functions){
    REQUIRE(record.calls==record.completed+record.aborted);
    REQUIRE(record.inclusiveCpuNs>=record.selfCpuNs);
  }
  REQUIRE(currentTaskProfileTask()==0&&currentTaskProfileInvocation()==0);
}
void manySegments(){
  at(100,1000);TaskProfileCollector collector({},sites,clock());auto task=collector.task();
  TaskProfileInvocation invocation;uint64_t invocationId=0;
  for(uint64_t i=0;i<37;++i){
    at(100+i*100,1000+i*10000);
    auto attached=collector.resume(task);REQUIRE(attached.active());
    if(i==0){invocation=collector.invocation(0);invocationId=invocation.id();}
    REQUIRE(currentTaskProfileTask()==task.id());
    REQUIRE(currentTaskProfileInvocation()==invocationId);
    {auto segment=collector.source(invocation);REQUIRE(segment.active());at(107+i*100,1003+i*10000);}
  }
  at(10000,900000);invocation.complete();invocation.complete();invocation.abort();
  collector.terminal(task,TaskProfileTaskOutcome::Completed);
  auto snapshot=collector.snapshot();balanced(snapshot);
  const auto &record=callRecord(snapshot,invocationId);
  REQUIRE(snapshot.functions[0].calls==1&&snapshot.functions[0].completed==1);
  REQUIRE(record.inclusiveCpuNs==111&&record.selfCpuNs==111);
  REQUIRE(record.activeElapsedNs==259&&record.lifetimeNs==9900);
  REQUIRE(snapshot.functions[0].lifetimeNs==9900&&snapshot.functions[0].maxLifetimeNs==9900);
  REQUIRE(snapshot.segments.size()==37);
  REQUIRE(taskRecord(snapshot,task.id()).resumes==37);
  REQUIRE(taskRecord(snapshot,task.id()).sourceCpuNs==111);
}
void realThreadMigration(){
  at(1,0,99);TaskProfileCollector collector({},sites,clock());
  auto task=collector.task(),other=collector.task();TaskProfileInvocation invocation;
  uint64_t invocationId=0;std::barrier phases(2);std::exception_ptr firstError,secondError;
  std::thread::id firstThread,secondThread;
  std::thread first([&]{
    firstThread=std::this_thread::get_id();
    try{
      at(10,1000,101);
      {auto attached=collector.resume(task);invocation=collector.invocation(0);invocationId=invocation.id();
        auto segment=collector.source(invocation);at(20,1010,101);}
    }catch(...){firstError=std::current_exception();}
    phases.arrive_and_wait();
    try{
      at(30,5000,101);
      {auto attached=collector.resume(other);auto helper=collector.invocation(1);
        {auto segment=collector.source(helper);at(35,5005,101);}helper.complete();}
      collector.terminal(other,TaskProfileTaskOutcome::Completed);
    }catch(...){firstError=std::current_exception();}
    phases.arrive_and_wait();phases.arrive_and_wait();
  });
  std::thread second([&]{
    secondThread=std::this_thread::get_id();phases.arrive_and_wait();phases.arrive_and_wait();
    try{
      at(100,1000000,202);
      {auto attached=collector.resume(task);REQUIRE(attached.active());
        REQUIRE(currentTaskProfileInvocation()==invocationId);
        auto segment=collector.source(invocation);at(109,1000007,202);}
    }catch(...){secondError=std::current_exception();}
    phases.arrive_and_wait();
  });
  first.join();second.join();if(firstError)std::rethrow_exception(firstError);if(secondError)std::rethrow_exception(secondError);
  REQUIRE(firstThread!=secondThread);
  at(200,0,99);invocation.complete();collector.terminal(task,TaskProfileTaskOutcome::Completed);
  auto snapshot=collector.snapshot();balanced(snapshot);
  REQUIRE(snapshot.functions[0].calls==1&&snapshot.functions[0].inclusiveCpuNs==17);
  REQUIRE(snapshot.functions[0].activeElapsedNs==19);
  REQUIRE(snapshot.functions[1].calls==1&&snapshot.functions[1].inclusiveCpuNs==5);
  const auto &record=taskRecord(snapshot,task.id());
  REQUIRE(record.resumes==2&&record.migrations==1&&record.lastThreadId==202);
  REQUIRE(record.sourceCpuNs==17);
  REQUIRE(snapshot.segments.size()==3);
}
void nestedHelper(){
  at(1,0);TaskProfileCollector collector({},sites,clock());auto task=collector.task();uint64_t parentId=0,childId=0;
  {auto attached=collector.resume(task);auto parent=collector.invocation(0);parentId=parent.id();
    {auto outer=collector.source(parent);at(11,10);
      auto child=collector.invocation(1);childId=child.id();
      {auto inner=collector.source(child);REQUIRE(currentTaskProfileInvocation()==childId);at(31,30);}
      child.complete();REQUIRE(currentTaskProfileInvocation()==parentId);at(41,40);
    }parent.complete();
  }
  collector.terminal(task,TaskProfileTaskOutcome::Completed);auto snapshot=collector.snapshot();balanced(snapshot);
  REQUIRE(callRecord(snapshot,childId).parentId==parentId);
  REQUIRE(snapshot.functions[0].inclusiveCpuNs==40&&snapshot.functions[0].selfCpuNs==20);
  REQUIRE(snapshot.functions[1].inclusiveCpuNs==20&&snapshot.functions[1].selfCpuNs==20);
  REQUIRE(snapshot.functions[0].activeElapsedNs==40&&snapshot.functions[0].selfActiveElapsedNs==20);
  REQUIRE(taskRecord(snapshot,task.id()).sourceCpuNs==40);
}
void nestedTaskTLS(){
  at(1,0);TaskProfileCollector collector({},sites,clock());auto parent=collector.task(),child=collector.task();
  uint64_t parentId=0,childId=0;
  {auto parentResume=collector.resume(parent);auto parentCall=collector.invocation(0);parentId=parentCall.id();
    {auto parentSegment=collector.source(parentCall);at(11,10);
      {auto childResume=collector.resume(child);auto childCall=collector.invocation(2);childId=childCall.id();
        REQUIRE(currentTaskProfileTask()==child.id());
        {auto childSegment=collector.source(childCall);at(31,30);}childCall.complete();
      }
      REQUIRE(currentTaskProfileTask()==parent.id()&&currentTaskProfileInvocation()==parentId);at(41,40);
    }parentCall.complete();
  }
  collector.terminal(parent,TaskProfileTaskOutcome::Completed);collector.terminal(child,TaskProfileTaskOutcome::Completed);
  auto snapshot=collector.snapshot();balanced(snapshot);
  REQUIRE(callRecord(snapshot,childId).parentId==0);
  REQUIRE(snapshot.functions[0].inclusiveCpuNs==20&&snapshot.functions[0].selfCpuNs==20);
  REQUIRE(snapshot.functions[2].inclusiveCpuNs==20&&snapshot.functions[2].selfCpuNs==20);
  REQUIRE(taskRecord(snapshot,parent.id()).sourceCpuNs==20&&taskRecord(snapshot,child.id()).sourceCpuNs==20);
}
void spawnAndDormantParent(){
  at(1,0);TaskProfileCollector collector({},sites,clock());auto parent=collector.task();TaskProfileTask child;
  TaskProfileInvocation parentCall;uint64_t parentId=0,childId=0;
  {auto attached=collector.resume(parent);parentCall=collector.invocation(0);parentId=parentCall.id();
    {auto source=collector.source(parentCall);at(11,10);}child=collector.task(parentCall);
  }
  at(1000,50000);
  {auto attached=collector.resume(child);auto call=collector.invocation(2);childId=call.id();
    {auto source=collector.source(call);at(1006,50006);}call.complete();
  }
  collector.terminal(child,TaskProfileTaskOutcome::Completed);at(2000,80000);
  {auto attached=collector.resume(parent);{auto source=collector.source(parentCall);at(2005,80005);}parentCall.complete();}
  collector.terminal(parent,TaskProfileTaskOutcome::Completed);auto snapshot=collector.snapshot();balanced(snapshot);
  REQUIRE(taskRecord(snapshot,child.id()).spawningInvocationId==parentId);
  REQUIRE(callRecord(snapshot,childId).parentId==0&&callRecord(snapshot,childId).taskId==child.id());
  REQUIRE(snapshot.functions[0].inclusiveCpuNs==15&&snapshot.functions[0].activeElapsedNs==15);
  REQUIRE(snapshot.functions[0].lifetimeNs==2004&&snapshot.functions[2].inclusiveCpuNs==6);
}
void childAfterParentCompletion(){
  at(1,0);TaskProfileCollector collector({},sites,clock());auto parent=collector.task();TaskProfileTask child;uint64_t parentId=0;
  {auto attached=collector.resume(parent);auto call=collector.invocation(0);parentId=call.id();
    {auto source=collector.source(call);at(6,5);}child=collector.task(call);call.complete();}
  collector.terminal(parent,TaskProfileTaskOutcome::Completed);at(100,1000);
  {auto attached=collector.resume(child);auto call=collector.invocation(2);{auto source=collector.source(call);at(107,1007);}call.complete();}
  collector.terminal(child,TaskProfileTaskOutcome::Completed);auto snapshot=collector.snapshot();balanced(snapshot);
  REQUIRE(taskRecord(snapshot,child.id()).spawningInvocationId==parentId);
  REQUIRE(snapshot.functions[0].inclusiveCpuNs==5&&snapshot.functions[2].inclusiveCpuNs==7);
}
void dormantUnwind(){
  at(1,0);TaskProfileCollector collector({},sites,clock());auto task=collector.task();uint64_t id=0;
  {TaskProfileInvocation retained;
    try{auto attached=collector.resume(task);retained=collector.invocation(0);id=retained.id();
      auto source=collector.source(retained);at(8,7);throw std::runtime_error("transient-request-unwind");
    }catch(const std::runtime_error &error){REQUIRE(std::string(error.what())=="transient-request-unwind");}
    REQUIRE(currentTaskProfileTask()==0&&currentTaskProfileInvocation()==0);
    auto dormant=collector.snapshot();REQUIRE(callRecord(dormant,id).outcome==TaskProfileInvocationOutcome::Active);
    REQUIRE(dormant.functions[0].aborted==0&&taskRecord(dormant,task.id()).activeInvocations==1);
    at(100,10000);{auto attached=collector.resume(task);auto source=collector.source(retained);at(105,10005);}
    // Dormant token destruction aborts once; attachment unwind above did not.
  }
  collector.terminal(task,TaskProfileTaskOutcome::Aborted);auto snapshot=collector.snapshot();balanced(snapshot);
  REQUIRE(snapshot.functions[0].calls==1&&snapshot.functions[0].aborted==1);
  REQUIRE(snapshot.functions[0].inclusiveCpuNs==12);
}
void exceptionUnwind(){
  at(1,0);TaskProfileCollector collector({},sites,clock());auto task=collector.task();int marker=42;
  try{auto attached=collector.resume(task);auto call=collector.invocation(0);auto source=collector.source(call);at(9,8);throw &marker;}
  catch(int *caught){REQUIRE(caught==&marker&&*caught==42);}
  collector.terminal(task,TaskProfileTaskOutcome::Aborted);auto snapshot=collector.snapshot();balanced(snapshot);
  REQUIRE(snapshot.functions[0].calls==1&&snapshot.functions[0].aborted==1&&snapshot.functions[0].inclusiveCpuNs==8);
}
void invocationMoves(){
  at(1,0);TaskProfileCollector collector({},sites,clock());auto task=collector.task();uint64_t firstId=0,secondId=0;
  {auto attached=collector.resume(task);auto first=collector.invocation(0);firstId=first.id();
    TaskProfileInvocation moved(std::move(first));REQUIRE(!first&&moved.id()==firstId);
    auto second=collector.invocation(1);secondId=second.id();second=std::move(moved);
    REQUIRE(!moved&&second.id()==firstId&&second.taskId()==task.id());
    {auto source=collector.source(second);at(5,4);}second.complete();second.complete();second.abort();
  }
  collector.terminal(task,TaskProfileTaskOutcome::Completed);auto snapshot=collector.snapshot();balanced(snapshot);
  REQUIRE(callRecord(snapshot,firstId).outcome==TaskProfileInvocationOutcome::Completed);
  REQUIRE(callRecord(snapshot,secondId).outcome==TaskProfileInvocationOutcome::Aborted);
  REQUIRE(snapshot.functions[0].calls==1&&snapshot.functions[0].completed==1);
  REQUIRE(snapshot.functions[1].calls==1&&snapshot.functions[1].aborted==1);
}
void vectorMoves(){
  at(1,0);TaskProfileCollector collector({},sites,clock());auto task=collector.task();
  {auto attached=collector.resume(task);std::vector<TaskProfileInvocation> calls;calls.reserve(1);
    for(size_t i=0;i<65;++i){calls.push_back(collector.invocation(0));REQUIRE(bool(calls.back()));}
    for(auto it=calls.rbegin();it!=calls.rend();++it)it->complete();
  }
  collector.terminal(task,TaskProfileTaskOutcome::Completed);auto snapshot=collector.snapshot();balanced(snapshot);
  REQUIRE(snapshot.functions[0].calls==65&&snapshot.functions[0].completed==65&&snapshot.functions[0].aborted==0);
}
void collectorTLSIsolation(){
  at(1,0);TaskProfileCollector first({},sites,clock()),second({},sites,clock());auto a=first.task(),b=second.task();
  {auto outer=first.resume(a);auto outerCall=first.invocation(0);auto id=outerCall.id();
    {auto source=first.source(outerCall);at(6,5);
      try{auto inner=second.resume(b);auto call=second.invocation(1);auto segment=second.source(call);at(15,14);throw 42;}
      catch(int value){REQUIRE(value==42);}
      REQUIRE(currentTaskProfileTask()==a.id()&&currentTaskProfileInvocation()==id);at(19,18);
    }outerCall.complete();
  }
  first.terminal(a,TaskProfileTaskOutcome::Completed);second.terminal(b,TaskProfileTaskOutcome::Aborted);
  auto sa=first.snapshot(),sb=second.snapshot();balanced(sa);balanced(sb);
  REQUIRE(sa.functions[0].inclusiveCpuNs==9&&sb.functions[1].inclusiveCpuNs==9);
  REQUIRE(sb.invocations.size()==1&&sb.invocations[0].parentId==0);
}
void wrongCollectorRejected(){
  at(1,0);TaskProfileCollector first({},sites,clock()),second({},sites,clock());auto a=first.task(),b=second.task();
  TaskProfileInvocation own;
  {auto attached=second.resume(b);own=second.invocation(0);}
  {auto outer=first.resume(a);auto call=first.invocation(0);auto id=call.id();
    REQUIRE(a.id()==b.id()&&call.id()==own.id());
    {auto wrongResume=second.resume(a);REQUIRE(!wrongResume.active());
      REQUIRE(currentTaskProfileTask()==0&&currentTaskProfileInvocation()==0);
      auto wrongSource=second.source(call);REQUIRE(!wrongSource.active());
      auto wrongSpawn=second.task(call);REQUIRE(!wrongSpawn);
    }
    REQUIRE(currentTaskProfileTask()==a.id()&&currentTaskProfileInvocation()==id);call.complete();
  }
  first.terminal(a,TaskProfileTaskOutcome::Completed);own.complete();second.terminal(b,TaskProfileTaskOutcome::Completed);
  auto sa=first.snapshot(),sb=second.snapshot();balanced(sa);balanced(sb,false);
  REQUIRE(sb.drops.invalidTransitions>=3&&sb.drops.incomplete);
}
void disabledCollector(){
  TaskProfileOptions options;options.enabled=false;TaskProfileCollector collector(options,sites,clock());
  REQUIRE(!collector.enabled());auto task=collector.task();REQUIRE(!task);
  auto attached=collector.resume(task);REQUIRE(!attached.active());auto call=collector.invocation(0);REQUIRE(!call);
  auto source=collector.source(call);REQUIRE(!source.active());call.complete();call.abort();
  collector.cancelBeforeStart(task);collector.terminal(task,TaskProfileTaskOutcome::Cancelled);
  auto snapshot=collector.snapshot();REQUIRE(!snapshot.enabled&&snapshot.tasks.empty()&&snapshot.invocations.empty());
  REQUIRE(currentTaskProfileTask()==0&&currentTaskProfileInvocation()==0);
}
void cancelBeforeStart(){
  at(1,0);TaskProfileCollector collector({},sites,clock());auto task=collector.task();collector.cancelBeforeStart(task);
  auto pending=collector.snapshot();REQUIRE(!taskRecord(pending,task.id()).terminal);
  collector.terminal(task,TaskProfileTaskOutcome::Cancelled);
  auto snapshot=collector.snapshot();balanced(snapshot);const auto &record=taskRecord(snapshot,task.id());
  REQUIRE(record.cancelledBeforeStart&&!record.started&&record.resumes==0);
  REQUIRE(record.outcome==TaskProfileTaskOutcome::Cancelled&&snapshot.functions[0].calls==0);
}
void eventCapKeepsAggregates(){
  TaskProfileOptions options;options.limits.events=2;at(1,0);TaskProfileCollector collector(options,sites,clock());auto task=collector.task();
  for(uint64_t i=0;i<100;++i){at(i*10+1,i*100+1);auto attached=collector.resume(task);auto call=collector.invocation(0);
    {auto source=collector.source(call);at(i*10+3,i*100+2);}call.complete();}
  collector.terminal(task,TaskProfileTaskOutcome::Completed);auto snapshot=collector.snapshot();
  REQUIRE(snapshot.functions[0].calls==100&&snapshot.functions[0].completed==100&&snapshot.functions[0].aborted==0);
  REQUIRE(snapshot.functions[0].inclusiveCpuNs==100&&snapshot.functions[0].activeElapsedNs==200);
  REQUIRE(snapshot.segments.size()+snapshot.invocations.size()<=2);
  REQUIRE(snapshot.drops.events>0&&snapshot.drops.incomplete);
  REQUIRE(taskRecord(snapshot,task.id()).activeInvocations==0&&currentTaskProfileTask()==0);
}
void zeroEventsRetainsActive(){
  TaskProfileOptions options;options.limits.events=0;at(1,0);TaskProfileCollector collector(options,sites,clock());auto task=collector.task();
  TaskProfileInvocation call;uint64_t id=0;
  {auto attached=collector.resume(task);call=collector.invocation(0);id=call.id();{auto source=collector.source(call);at(10,9);}}
  auto active=collector.snapshot();REQUIRE(active.invocations.size()==1&&callRecord(active,id).outcome==TaskProfileInvocationOutcome::Active);
  REQUIRE(active.segments.empty()&&active.functions[0].calls==1&&active.functions[0].aborted==0);
  call.complete();collector.terminal(task,TaskProfileTaskOutcome::Completed);auto finished=collector.snapshot();
  REQUIRE(finished.invocations.empty()&&finished.segments.empty());
  REQUIRE(finished.functions[0].calls==1&&finished.functions[0].completed==1&&finished.functions[0].inclusiveCpuNs==9);
  REQUIRE(finished.drops.events>0&&finished.drops.incomplete&&taskRecord(finished,task.id()).activeInvocations==0);
}
void taskAndInvocationCaps(){
  TaskProfileOptions options;options.limits={1,1,100};at(1,0);TaskProfileCollector collector(options,sites,clock());
  auto task=collector.task(),droppedTask=collector.task();REQUIRE(task&&!droppedTask);int result=0;
  {auto attached=collector.resume(task);auto kept=collector.invocation(0);auto dropped=collector.invocation(1);
    REQUIRE(kept&&!dropped);{auto source=collector.source(dropped);REQUIRE(!source.active());result=40+2;}
    kept.complete();auto reused=collector.invocation(0);REQUIRE(bool(reused));reused.complete();
  }
  REQUIRE(result==42);collector.terminal(task,TaskProfileTaskOutcome::Completed);auto snapshot=collector.snapshot();
  REQUIRE(snapshot.tasks.size()==1&&snapshot.invocations.size()<=2);
  REQUIRE(snapshot.functions[0].completed==2&&snapshot.drops.tasks>0&&snapshot.drops.invocations>0&&snapshot.drops.incomplete);
  REQUIRE(taskRecord(snapshot,task.id()).activeInvocations==0&&currentTaskProfileTask()==0);
}
void zeroCapacityPreservesException(){
  TaskProfileOptions options;options.limits={0,0,0};at(1,0);TaskProfileCollector collector(options,sites,clock());int marker=42;
  try{auto task=collector.task();auto attached=collector.resume(task);auto call=collector.invocation(0);auto source=collector.source(call);throw &marker;}
  catch(int *caught){REQUIRE(caught==&marker&&*caught==42);}
  auto snapshot=collector.snapshot();REQUIRE(snapshot.tasks.empty()&&snapshot.invocations.empty()&&snapshot.segments.empty());
  REQUIRE(snapshot.drops.tasks>0&&snapshot.drops.incomplete&&currentTaskProfileTask()==0&&currentTaskProfileInvocation()==0);
}
void clockFailure(bool wallFailure){
  at(1,0,1,!wallFailure,wallFailure);TaskProfileCollector collector({},sites,clock());auto task=collector.task();
  int result=0;
  {auto attached=collector.resume(task);auto call=collector.invocation(0);{auto source=collector.source(call);result=42;at(12,9,1,!wallFailure,wallFailure);}call.complete();}
  collector.terminal(task,TaskProfileTaskOutcome::Completed);auto snapshot=collector.snapshot();balanced(snapshot,false);
  REQUIRE(result==42&&snapshot.drops.clockFailures>0&&snapshot.drops.incomplete);
  const auto &record=snapshot.functions[0];REQUIRE(record.calls==1&&record.completed==1);
  if(wallFailure){REQUIRE(!record.elapsedAvailable&&!record.lifetimeAvailable);REQUIRE(record.cpuAvailable&&record.inclusiveCpuNs==9);}
  else{REQUIRE(!record.cpuAvailable);REQUIRE(record.elapsedAvailable&&record.activeElapsedNs==11);}
}
void regressingClocks(){
  at(100,100);TaskProfileCollector collector({},sites,clock());auto task=collector.task();
  {auto attached=collector.resume(task);auto call=collector.invocation(0);{auto source=collector.source(call);at(90,50);}call.complete();}
  collector.terminal(task,TaskProfileTaskOutcome::Completed);auto snapshot=collector.snapshot();balanced(snapshot,false);
  REQUIRE(snapshot.drops.clockFailures>0&&snapshot.drops.incomplete);
  REQUIRE(snapshot.functions[0].inclusiveCpuNs==0&&snapshot.functions[0].activeElapsedNs==0&&snapshot.functions[0].lifetimeNs==0);
  REQUIRE(!snapshot.functions[0].cpuAvailable&&!snapshot.functions[0].elapsedAvailable&&!snapshot.functions[0].lifetimeAvailable);
}
void changedClockThread(){
  at(1,100,1);TaskProfileCollector collector({},sites,clock());auto task=collector.task();
  {auto attached=collector.resume(task);auto call=collector.invocation(0);{auto source=collector.source(call);at(11,1000000,2);}call.complete();}
  collector.terminal(task,TaskProfileTaskOutcome::Completed);auto snapshot=collector.snapshot();balanced(snapshot,false);
  REQUIRE(snapshot.drops.clockFailures>0&&snapshot.drops.incomplete);
  REQUIRE(!snapshot.functions[0].cpuAvailable&&snapshot.functions[0].inclusiveCpuNs==0);
}
void counterSaturation(){
  const auto maximum=std::numeric_limits<uint64_t>::max();at(1,0);TaskProfileCollector collector({},sites,clock());auto task=collector.task();
  TaskProfileInvocation call;
  for(uint64_t i=0;i<2;++i){at(1+i*2,0);auto attached=collector.resume(task);if(i==0)call=collector.invocation(0);
    auto source=collector.source(call);at(2+i*2,maximum);}
  at(5,maximum);call.complete();collector.terminal(task,TaskProfileTaskOutcome::Completed);auto snapshot=collector.snapshot();balanced(snapshot,false);
  REQUIRE(snapshot.functions[0].inclusiveCpuNs==maximum&&snapshot.functions[0].selfCpuNs==maximum);
  REQUIRE(snapshot.drops.counterOverflows>0&&snapshot.drops.incomplete);
}
void prematureParentCompletion(){
  at(1,0);TaskProfileCollector collector({},sites,clock());auto task=collector.task();uint64_t parentId=0,childId=0;
  {auto attached=collector.resume(task);auto parent=collector.invocation(0);parentId=parent.id();
    auto child=collector.invocation(1);childId=child.id();parent.complete();REQUIRE(!parent);
    {auto source=collector.source(child);at(10,9);}child.complete();
  }
  collector.terminal(task,TaskProfileTaskOutcome::Aborted);auto snapshot=collector.snapshot();balanced(snapshot,false);
  REQUIRE(snapshot.drops.invalidTransitions>0&&snapshot.drops.incomplete);
  REQUIRE(callRecord(snapshot,parentId).outcome==TaskProfileInvocationOutcome::Aborted);
  REQUIRE(callRecord(snapshot,childId).outcome==TaskProfileInvocationOutcome::Completed);
}
void completionDuringSourceSegment(){
  at(1,0);TaskProfileCollector collector({},sites,clock());auto task=collector.task();uint64_t id=0;
  {auto attached=collector.resume(task);auto call=collector.invocation(0);id=call.id();
    {auto source=collector.source(call);at(6,5);call.complete();REQUIRE(!call);at(10,9);}
  }
  collector.terminal(task,TaskProfileTaskOutcome::Aborted);auto snapshot=collector.snapshot();balanced(snapshot,false);
  REQUIRE(snapshot.drops.invalidTransitions>0&&snapshot.drops.incomplete);
  REQUIRE(callRecord(snapshot,id).outcome==TaskProfileInvocationOutcome::Aborted);
}
void cancelledTaskCannotReattach(){
  at(1,0);TaskProfileCollector collector({},sites,clock());auto task=collector.task();collector.cancelBeforeStart(task);
  {auto attached=collector.resume(task);REQUIRE(!attached.active());}
  REQUIRE(currentTaskProfileTask()==0&&currentTaskProfileInvocation()==0);
  collector.terminal(task,TaskProfileTaskOutcome::Cancelled);auto snapshot=collector.snapshot();balanced(snapshot,false);
  REQUIRE(snapshot.drops.invalidTransitions>0&&snapshot.drops.incomplete);
  REQUIRE(taskRecord(snapshot,task.id()).resumes==0&&snapshot.functions[0].calls==0);
}
void snapshotOverflowIsObservational(){
  auto maximum=std::numeric_limits<uint64_t>::max();at(1,0);TaskProfileCollector collector({},sites,clock());auto task=collector.task();
  TaskProfileInvocation parent;uint64_t parentId=0;
  {auto attached=collector.resume(task);parent=collector.invocation(0);parentId=parent.id();
    auto source=collector.source(parent);at(2,maximum-10);}
  at(3,0);
  {auto attached=collector.resume(task);auto child=collector.invocation(1);
    {auto source=collector.source(child);at(4,20);}child.complete();}
  auto first=collector.snapshot(),second=collector.snapshot();
  REQUIRE(callRecord(first,parentId).outcome==TaskProfileInvocationOutcome::Active);
  REQUIRE(callRecord(first,parentId).inclusiveCpuNs==maximum&&callRecord(second,parentId).inclusiveCpuNs==maximum);
  REQUIRE(first.drops.counterOverflows>0&&first.drops.counterOverflows==second.drops.counterOverflows);
  REQUIRE(first.drops.incomplete&&second.drops.incomplete);
  at(5,20);parent.complete();collector.terminal(task,TaskProfileTaskOutcome::Completed);
  auto finished=collector.snapshot();balanced(finished,false);
  REQUIRE(finished.drops.counterOverflows==first.drops.counterOverflows);
}
struct ReentrantClock {
  TaskProfileCollector *collector=nullptr;size_t observations=0;bool failed=false;
};
TaskProfileClockSample observingClock(void *context)noexcept{
  auto &observer=*static_cast<ReentrantClock*>(context);
  if(observer.collector){
    try{auto snapshot=observer.collector->snapshot();if(!snapshot.enabled)observer.failed=true;++observer.observations;}
    catch(...){observer.failed=true;}
  }
  return point;
}
void clocksAreOutsideCollectorLock(){
  ReentrantClock observer;TaskProfileOptions options;options.limits={2,4,16};at(1,0);
  TaskProfileCollector collector(options,sites,{observingClock,&observer});observer.collector=&collector;
  auto task=collector.task();
  {auto attached=collector.resume(task);auto call=collector.invocation(0);{auto source=collector.source(call);at(8,7);}call.complete();}
  collector.terminal(task,TaskProfileTaskOutcome::Completed);auto snapshot=collector.snapshot();balanced(snapshot);
  REQUIRE(!observer.failed&&observer.observations>=6&&snapshot.functions[0].inclusiveCpuNs==7);
}
void simultaneousResumeRejected(){
  at(1,0);TaskProfileCollector collector({},sites,clock());auto task=collector.task();std::barrier phases(2);std::exception_ptr failure;
  {
    auto attached=collector.resume(task);auto call=collector.invocation(0);auto source=collector.source(call);
    std::thread contender([&]{
      at(2,1000000,2);phases.arrive_and_wait();
      try{auto rejected=collector.resume(task);REQUIRE(!rejected.active());REQUIRE(currentTaskProfileTask()==0&&currentTaskProfileInvocation()==0);}
      catch(...){failure=std::current_exception();}
      phases.arrive_and_wait();
    });
    phases.arrive_and_wait();phases.arrive_and_wait();contender.join();
    if(failure)std::rethrow_exception(failure);
    REQUIRE(currentTaskProfileTask()==task.id()&&currentTaskProfileInvocation()==call.id());at(5,4);
    // Complete after source retirement, through the normal lexical destruction.
  }
  collector.terminal(task,TaskProfileTaskOutcome::Aborted);auto snapshot=collector.snapshot();balanced(snapshot,false);
  REQUIRE(snapshot.drops.invalidTransitions>0&&snapshot.drops.incomplete);
  REQUIRE(taskRecord(snapshot,task.id()).resumes==1&&taskRecord(snapshot,task.id()).migrations==0);
  REQUIRE(snapshot.functions[0].calls==1&&snapshot.functions[0].aborted==1&&snapshot.functions[0].inclusiveCpuNs==4);
}
void nonLifoSourceSegments(){
  at(1,0);TaskProfileCollector collector({},sites,clock());auto task=collector.task();
  {
    auto attached=collector.resume(task);auto parent=collector.invocation(0);
    auto *outer=new TaskProfileSourceSegment(collector.source(parent));at(11,10);
    auto helper=collector.invocation(1);auto *inner=new TaskProfileSourceSegment(collector.source(helper));at(21,20);
    delete outer;at(31,30);delete inner;helper.complete();parent.complete();
  }
  collector.terminal(task,TaskProfileTaskOutcome::Completed);auto snapshot=collector.snapshot();balanced(snapshot,false);
  REQUIRE(snapshot.drops.invalidTransitions>0&&snapshot.drops.incomplete);
  REQUIRE(snapshot.functions[0].inclusiveCpuNs==30&&snapshot.functions[0].selfCpuNs==10);
  REQUIRE(snapshot.functions[1].inclusiveCpuNs==20&&taskRecord(snapshot,task.id()).sourceCpuNs==30);
}
void nonLifoResumeAndPausedSegment(){
  at(1,0);TaskProfileCollector collector({},sites,clock());auto a=collector.task(),b=collector.task();
  auto *outer=new TaskProfileResumeGuard(collector.resume(a));auto parent=collector.invocation(0);
  auto *paused=new TaskProfileSourceSegment(collector.source(parent));at(11,10);
  auto *inner=new TaskProfileResumeGuard(collector.resume(b));auto child=collector.invocation(2);
  auto *active=new TaskProfileSourceSegment(collector.source(child));at(21,20);
  delete outer;delete paused;at(31,30);delete active;child.complete();delete inner;parent.abort();
  REQUIRE(currentTaskProfileTask()==0&&currentTaskProfileInvocation()==0);
  collector.terminal(a,TaskProfileTaskOutcome::Aborted);collector.terminal(b,TaskProfileTaskOutcome::Completed);
  auto snapshot=collector.snapshot();balanced(snapshot,false);
  REQUIRE(snapshot.drops.invalidTransitions>0&&snapshot.drops.incomplete);
  REQUIRE(snapshot.functions[0].inclusiveCpuNs==10&&snapshot.functions[2].inclusiveCpuNs==20);
}
void concurrentTasksAndSnapshots(){
  TaskProfileOptions options;options.limits={2,8,200};at(1,0);TaskProfileCollector collector(options,sites,clock());
  auto a=collector.task(),b=collector.task();std::barrier phases(3);std::exception_ptr failure;
  auto worker=[&](TaskProfileTask task,uint64_t thread){
    for(uint64_t i=0;i<32;++i){
      at(10+i*10,1000*thread+i*100,thread);
      {auto attached=collector.resume(task);auto call=collector.invocation(0);
        {auto source=collector.source(call);at(15+i*10,1000*thread+i*100+7,thread);
          phases.arrive_and_wait();phases.arrive_and_wait();}
        call.complete();
      }
      phases.arrive_and_wait();
    }
  };
  std::thread first(worker,a,11),second(worker,b,22);
  for(uint64_t i=0;i<32;++i){
    phases.arrive_and_wait();
    try{auto snapshot=collector.snapshot();
      REQUIRE(snapshot.functions[0].calls==2*i+2&&snapshot.functions[0].completed==2*i);
      size_t active=0;for(const auto &call:snapshot.invocations)if(call.outcome==TaskProfileInvocationOutcome::Active)++active;
      REQUIRE(active==2);
      REQUIRE(taskRecord(snapshot,a.id()).activeInvocations==1&&taskRecord(snapshot,b.id()).activeInvocations==1);
    }catch(...){if(!failure)failure=std::current_exception();}
    phases.arrive_and_wait();
    try{auto during=collector.snapshot();REQUIRE(during.functions[0].completed<=during.functions[0].calls);}
    catch(...){if(!failure)failure=std::current_exception();}
    phases.arrive_and_wait();
  }
  first.join();second.join();if(failure)std::rethrow_exception(failure);
  at(1000,0);collector.terminal(a,TaskProfileTaskOutcome::Completed);collector.terminal(b,TaskProfileTaskOutcome::Completed);
  auto snapshot=collector.snapshot();balanced(snapshot);
  REQUIRE(snapshot.functions[0].calls==64&&snapshot.functions[0].completed==64&&snapshot.functions[0].aborted==0);
  REQUIRE(snapshot.functions[0].inclusiveCpuNs==448&&snapshot.functions[0].activeElapsedNs==320);
  REQUIRE(taskRecord(snapshot,a.id()).sourceCpuNs==224&&taskRecord(snapshot,b.id()).sourceCpuNs==224);
}
void finishedTokensRejected(){
  at(1,0);TaskProfileCollector collector({},sites,clock());auto task=collector.task();
  {auto attached=collector.resume(task);auto call=collector.invocation(0);call.complete();
    auto rejected=collector.source(call);REQUIRE(!rejected.active());REQUIRE(currentTaskProfileInvocation()==0);}
  collector.terminal(task,TaskProfileTaskOutcome::Completed);
  {auto rejected=collector.resume(task);REQUIRE(!rejected.active());}
  auto snapshot=collector.snapshot();balanced(snapshot,false);
  REQUIRE(snapshot.drops.invalidTransitions>=2&&snapshot.drops.incomplete);
  REQUIRE(taskRecord(snapshot,task.id()).resumes==1&&snapshot.functions[0].calls==1&&snapshot.functions[0].completed==1);
}
void parentAbortDefersCleanly(){
  at(1,0);TaskProfileCollector collector({},sites,clock());auto task=collector.task();uint64_t parentId=0,childId=0;
  {auto attached=collector.resume(task);auto parent=collector.invocation(0);parentId=parent.id();
    auto child=collector.invocation(1);childId=child.id();parent.abort();REQUIRE(!parent);
    {auto source=collector.source(child);at(9,8);}child.complete();
  }
  collector.terminal(task,TaskProfileTaskOutcome::Aborted);auto snapshot=collector.snapshot();balanced(snapshot);
  REQUIRE(callRecord(snapshot,parentId).outcome==TaskProfileInvocationOutcome::Aborted);
  REQUIRE(callRecord(snapshot,childId).outcome==TaskProfileInvocationOutcome::Completed);
  REQUIRE(snapshot.functions[0].aborted==1&&snapshot.functions[1].completed==1);
  REQUIRE(snapshot.functions[0].inclusiveCpuNs==8&&snapshot.functions[0].selfCpuNs==0);
}
void deletePausedSegmentWithoutInnerSource(){
  at(1,0);TaskProfileCollector collector({},sites,clock());auto a=collector.task(),b=collector.task();
  {auto attached=collector.resume(a);auto call=collector.invocation(0);auto id=call.id();
    auto *paused=new TaskProfileSourceSegment(collector.source(call));at(11,10);
    auto *inner=new TaskProfileResumeGuard(collector.resume(b));delete paused;at(21,20);delete inner;
    REQUIRE(currentTaskProfileTask()==a.id()&&currentTaskProfileInvocation()==id);call.complete();
  }
  collector.terminal(a,TaskProfileTaskOutcome::Completed);collector.terminal(b,TaskProfileTaskOutcome::Completed);
  auto snapshot=collector.snapshot();balanced(snapshot,false);
  REQUIRE(snapshot.drops.invalidTransitions>0&&snapshot.drops.incomplete);
  REQUIRE(snapshot.functions[0].inclusiveCpuNs==10&&taskRecord(snapshot,a.id()).sourceCpuNs==10);
}
void middleResumeReparentsToOuter(){
  at(1,0);TaskProfileCollector collector({},sites,clock());auto a=collector.task(),b=collector.task(),c=collector.task();
  {auto outer=collector.resume(a);auto root=collector.invocation(0);auto rootId=root.id();
    auto *rootSource=new TaskProfileSourceSegment(collector.source(root));at(11,10);
    auto *middle=new TaskProfileResumeGuard(collector.resume(b));auto helper=collector.invocation(1);
    auto *helperSource=new TaskProfileSourceSegment(collector.source(helper));at(21,20);
    auto *inner=new TaskProfileResumeGuard(collector.resume(c));auto child=collector.invocation(2);
    auto *childSource=new TaskProfileSourceSegment(collector.source(child));at(31,30);
    delete middle;delete helperSource;at(41,40);delete childSource;child.complete();delete inner;
    REQUIRE(currentTaskProfileTask()==a.id()&&currentTaskProfileInvocation()==rootId);
    at(51,50);delete rootSource;root.complete();helper.abort();
  }
  collector.terminal(a,TaskProfileTaskOutcome::Completed);collector.terminal(b,TaskProfileTaskOutcome::Aborted);collector.terminal(c,TaskProfileTaskOutcome::Completed);
  auto snapshot=collector.snapshot();balanced(snapshot,false);
  REQUIRE(snapshot.drops.invalidTransitions>0&&snapshot.drops.incomplete);
  REQUIRE(snapshot.functions[0].inclusiveCpuNs==20&&snapshot.functions[1].inclusiveCpuNs==10&&snapshot.functions[2].inclusiveCpuNs==20);
}
void sourceGuardDepthCap(){
  TaskProfileOptions options;options.limits={2,2,2*maximumTaskProfileGuardDepth+16};at(1,0);
  TaskProfileCollector collector(options,sites,clock());auto task=collector.task();int result=0;
  {
    auto attached=collector.resume(task);auto call=collector.invocation(0);auto id=call.id();
    std::vector<std::unique_ptr<TaskProfileSourceSegment>> segments;segments.reserve(maximumTaskProfileGuardDepth-1);
    for(size_t i=1;i<maximumTaskProfileGuardDepth;++i){
      segments.emplace_back(new TaskProfileSourceSegment(collector.source(call)));REQUIRE(segments.back()->active());
    }
    {auto overflow=collector.source(call);REQUIRE(!overflow.active());result=40+2;}
    REQUIRE(currentTaskProfileTask()==task.id()&&currentTaskProfileInvocation()==id);
    at(8,7);while(!segments.empty())segments.pop_back();
    {auto restarted=collector.source(call);REQUIRE(restarted.active());at(10,9);}
    call.complete();
  }
  collector.terminal(task,TaskProfileTaskOutcome::Completed);auto snapshot=collector.snapshot();balanced(snapshot,false);
  REQUIRE(result==42&&snapshot.drops.guards==1&&snapshot.drops.incomplete);
  REQUIRE(snapshot.drops.invalidTransitions==0&&snapshot.drops.clockFailures==0&&snapshot.drops.events==0);
  REQUIRE(snapshot.drops.tasks==0&&snapshot.drops.invocations==0&&snapshot.drops.counterOverflows==0);
  REQUIRE(snapshot.functions[0].calls==1&&snapshot.functions[0].completed==1&&snapshot.functions[0].inclusiveCpuNs==9);
}
void crossCollectorResumeDepthCap(){
  TaskProfileOptions options;options.limits={maximumTaskProfileGuardDepth+2,2,16};at(1,0);
  TaskProfileCollector first(options,sites,clock()),second(options,sites,clock());
  std::vector<TaskProfileTask> tasks;tasks.reserve(maximumTaskProfileGuardDepth);
  std::vector<std::unique_ptr<TaskProfileResumeGuard>> guards;guards.reserve(maximumTaskProfileGuardDepth);
  for(size_t i=0;i<maximumTaskProfileGuardDepth;++i){
    auto &collector=i%2?second:first;tasks.push_back(collector.task());
    guards.emplace_back(new TaskProfileResumeGuard(collector.resume(tasks.back())));REQUIRE(guards.back()->active());
  }
  auto extra=first.task();int result=0;
  {auto overflow=first.resume(extra);REQUIRE(!overflow.active());result=40+2;}
  REQUIRE(currentTaskProfileTask()==tasks.back().id());
  while(!guards.empty()){
    auto index=guards.size()-1;guards.pop_back();
    (index%2?second:first).terminal(tasks[index],TaskProfileTaskOutcome::Completed);
  }
  REQUIRE(currentTaskProfileTask()==0&&currentTaskProfileInvocation()==0);
  {auto restarted=first.resume(extra);REQUIRE(restarted.active());auto call=first.invocation(0);
    {auto source=first.source(call);REQUIRE(source.active());at(8,7);}call.complete();}
  first.terminal(extra,TaskProfileTaskOutcome::Completed);
  auto a=first.snapshot(),b=second.snapshot();balanced(a,false);balanced(b);
  REQUIRE(result==42&&a.drops.guards==1&&a.drops.incomplete);
  REQUIRE(a.drops.invalidTransitions==0&&a.drops.clockFailures==0&&a.drops.events==0);
  REQUIRE(a.drops.tasks==0&&a.drops.invocations==0&&a.drops.counterOverflows==0);
  REQUIRE(a.functions[0].calls==1&&a.functions[0].completed==1&&a.functions[0].inclusiveCpuNs==7);
  REQUIRE(b.functions[0].calls==0&&a.tasks.size()+b.tasks.size()==maximumTaskProfileGuardDepth+1);
}
void duplicateResumeSuppressesUnconditionalHooks(){
  at(1,0);TaskProfileCollector collector({},sites,clock());auto task=collector.task();int result=0;
  {auto attached=collector.resume(task);auto parent=collector.invocation(0);auto id=parent.id();
    {auto source=collector.source(parent);at(11,10);
      {auto failed=collector.resume(task); // Deliberately record without checking active().
        REQUIRE(currentTaskProfileTask()==0&&currentTaskProfileInvocation()==0);
        auto unexpected=collector.invocation(1);auto ignored=collector.source(unexpected);auto unrecorded=collector.task();
        REQUIRE(!unexpected&&!ignored.active()&&!unrecorded);result=40+2;at(21,1000);
      }
      REQUIRE(currentTaskProfileTask()==task.id()&&currentTaskProfileInvocation()==id);at(28,1007);
    }parent.complete();
  }
  collector.terminal(task,TaskProfileTaskOutcome::Completed);auto snapshot=collector.snapshot();balanced(snapshot,false);
  REQUIRE(result==42&&snapshot.functions[0].calls==1&&snapshot.functions[0].inclusiveCpuNs==17);
  REQUIRE(snapshot.functions[1].calls==0&&snapshot.tasks.size()==1);
  REQUIRE(snapshot.drops.invalidTransitions==1&&snapshot.drops.suppressedHooks==3&&snapshot.drops.guards==0);
}
void cappedResumeSuppressesUnconditionalHooks(){
  TaskProfileOptions options;options.limits={2,2,2*maximumTaskProfileGuardDepth+32};at(1,0);
  TaskProfileCollector first(options,sites,clock()),second(options,sites,clock());auto a=first.task(),b=second.task();int result=0;
  {auto attached=first.resume(a);auto parent=first.invocation(0);auto id=parent.id();
    std::vector<std::unique_ptr<TaskProfileSourceSegment>> segments;segments.reserve(maximumTaskProfileGuardDepth-1);
    for(size_t i=1;i<maximumTaskProfileGuardDepth;++i)
      segments.emplace_back(new TaskProfileSourceSegment(first.source(parent)));
    REQUIRE(segments.back()->active());at(11,10);
    {auto failed=second.resume(b); // Cap rejection must not inherit A attribution.
      REQUIRE(currentTaskProfileTask()==0&&currentTaskProfileInvocation()==0);
      auto wrongA=first.invocation(1),wrongB=second.invocation(1);
      auto sourceA=first.source(parent),sourceB=second.source(wrongB);
      auto taskA=first.task(),taskB=second.task();
      REQUIRE(!wrongA&&!wrongB&&!sourceA.active()&&!sourceB.active()&&!taskA&&!taskB);
      result=40+2;at(21,1000);
    }
    REQUIRE(currentTaskProfileTask()==a.id()&&currentTaskProfileInvocation()==id);at(28,1007);
    while(!segments.empty())segments.pop_back();parent.complete();
  }
  first.terminal(a,TaskProfileTaskOutcome::Completed);second.terminal(b,TaskProfileTaskOutcome::Completed);
  auto sa=first.snapshot(),sb=second.snapshot();balanced(sa,false);balanced(sb,false);
  REQUIRE(result==42&&sa.functions[0].calls==1&&sa.functions[0].inclusiveCpuNs==17);
  REQUIRE(sa.functions[1].calls==0&&sb.functions[0].calls==0&&sb.functions[1].calls==0);
  REQUIRE(sa.drops.suppressedHooks==3&&sb.drops.suppressedHooks==3&&sb.drops.guards==1);
  REQUIRE(sa.drops.invalidTransitions==0&&sb.drops.invalidTransitions==0&&sa.drops.events==0&&sb.drops.events==0);
}
void failedGuardNonLifoWithRetiredParent(){
  at(1,0);TaskProfileCollector first({},sites,clock()),second({},sites,clock());auto a=first.task(),b=second.task();
  auto *attached=new TaskProfileResumeGuard(first.resume(a));auto parent=first.invocation(0);
  auto *source=new TaskProfileSourceSegment(first.source(parent));at(11,10);
  auto *outerFailure=new TaskProfileResumeGuard(first.resume(a));
  auto *innerFailure=new TaskProfileResumeGuard(second.resume(b));
  REQUIRE(currentTaskProfileTask()==0&&currentTaskProfileInvocation()==0);at(21,1000);
  delete outerFailure;REQUIRE(currentTaskProfileTask()==0&&currentTaskProfileInvocation()==0);
  delete source;parent.complete();delete attached;delete innerFailure;
  REQUIRE(currentTaskProfileTask()==0&&currentTaskProfileInvocation()==0);at(31,2000);
  {auto restarted=second.resume(b);REQUIRE(restarted.active());auto call=second.invocation(2);
    {auto active=second.source(call);at(38,2007);}call.complete();}
  first.terminal(a,TaskProfileTaskOutcome::Completed);second.terminal(b,TaskProfileTaskOutcome::Completed);
  auto sa=first.snapshot(),sb=second.snapshot();balanced(sa,false);balanced(sb,false);
  REQUIRE(sa.functions[0].calls==1&&sa.functions[0].inclusiveCpuNs==10);
  REQUIRE(sb.functions[2].calls==1&&sb.functions[2].inclusiveCpuNs==7);
  REQUIRE(sa.drops.invalidTransitions==1&&sb.drops.invalidTransitions==0&&sb.drops.guards==1);
}
void actualPlatformClockMigration(){
  TaskProfileOptions options;options.limits={2,2,16};TaskProfileCollector collector(options,sites,TaskProfileClock{});
  auto task=collector.task();TaskProfileInvocation call;uint64_t id=0;std::atomic<uint64_t> work{1};std::exception_ptr failure;
  auto compute=[&]{for(uint64_t i=1;i<=100000;++i)work.fetch_add(i,std::memory_order_relaxed);};
  std::thread first([&]{try{auto attached=collector.resume(task);call=collector.invocation(0);id=call.id();
    auto source=collector.source(call);compute();}catch(...){failure=std::current_exception();}});
  first.join();if(failure)std::rethrow_exception(failure);
  std::thread second([&]{try{auto attached=collector.resume(task);auto source=collector.source(call);compute();}
    catch(...){failure=std::current_exception();}});
  second.join();if(failure)std::rethrow_exception(failure);
  call.complete();collector.terminal(task,TaskProfileTaskOutcome::Completed);auto snapshot=collector.snapshot();balanced(snapshot);
  REQUIRE(work.load()==10000100001ULL&&snapshot.functions[0].calls==1&&snapshot.functions[0].completed==1);
  REQUIRE(taskRecord(snapshot,task.id()).resumes==2&&taskRecord(snapshot,task.id()).migrations==1);
  REQUIRE(snapshot.segments.size()==2&&snapshot.segments[0].threadId!=snapshot.segments[1].threadId);
  const auto &record=callRecord(snapshot,id);
  REQUIRE(record.cpuAvailable&&record.elapsedAvailable&&record.lifetimeAvailable);
  REQUIRE(record.inclusiveCpuNs>0&&record.activeElapsedNs>0&&record.lifetimeNs>=record.activeElapsedNs);
  REQUIRE(record.inclusiveCpuNs==snapshot.segments[0].cpuNs+snapshot.segments[1].cpuNs);
  REQUIRE(record.activeElapsedNs==snapshot.segments[0].elapsedNs+snapshot.segments[1].elapsedNs);
  REQUIRE(record.selfCpuNs==record.inclusiveCpuNs&&snapshot.functions[0].inclusiveCpuNs==record.inclusiveCpuNs);
}
static_assert(maximumTaskProfileGuardDepth==4096);
static_assert(!std::is_copy_constructible_v<TaskProfileInvocation>);
static_assert(std::is_nothrow_move_constructible_v<TaskProfileInvocation>);
static_assert(std::is_nothrow_move_assignable_v<TaskProfileInvocation>);
static_assert(std::is_nothrow_destructible_v<TaskProfileInvocation>);
static_assert(std::is_nothrow_destructible_v<TaskProfileResumeGuard>);
static_assert(std::is_nothrow_destructible_v<TaskProfileSourceSegment>);
static_assert(noexcept(std::declval<TaskProfileCollector&>().task()));
static_assert(noexcept(std::declval<TaskProfileCollector&>().resume(std::declval<const TaskProfileTask&>())));
static_assert(noexcept(std::declval<TaskProfileCollector&>().invocation(0)));
static_assert(noexcept(std::declval<TaskProfileCollector&>().source(std::declval<const TaskProfileInvocation&>())));
static_assert(noexcept(std::declval<TaskProfileInvocation&>().complete()));
static_assert(noexcept(std::declval<TaskProfileInvocation&>().abort()));
}
int main()try{
  test("one-call-many-segments",manySegments);
  test("real-two-thread-migration-and-interleaving",realThreadMigration);
  test("same-task-helper-inclusive-self",nestedHelper);
  test("nested-task-tls-and-cpu-isolation",nestedTaskTLS);
  test("spawn-ancestry-dormant-parent-wall",spawnAndDormantParent);
  test("child-after-parent-completion",childAfterParentCompletion);
  test("transient-api-unwind-retains-logical-call",dormantUnwind);
  test("source-exception-identity-and-abort",exceptionUnwind);
  test("invocation-move-and-idempotent-close",invocationMoves);
  test("retained-token-vector-relocation",vectorMoves);
  test("nested-collectors-tls-unwind",collectorTLSIsolation);
  test("wrong-collector-rejection",wrongCollectorRejected);
  test("disabled-no-recording",disabledCollector);
  test("cancel-before-first-resume",cancelBeforeStart);
  test("event-cap-keeps-exact-aggregates",eventCapKeepsAggregates);
  test("zero-events-retain-active-logical-call",zeroEventsRetainsActive);
  test("task-and-invocation-cap-source-result",taskAndInvocationCaps);
  test("zero-cap-source-exception",zeroCapacityPreservesException);
  test("wall-clock-unavailable",[]{clockFailure(true);});
  test("cpu-clock-unavailable",[]{clockFailure(false);});
  test("regressing-clocks-no-wrap",regressingClocks);
  test("cpu-thread-change-no-cross-base-subtraction",changedClockThread);
  test("counter-overflow-saturates",counterSaturation);
  test("parent-close-defers-until-child-retired",prematureParentCompletion);
  test("close-defers-until-source-segment-retired",completionDuringSourceSegment);
  test("cancelled-before-start-cannot-reattach",cancelledTaskCannotReattach);
  test("snapshot-overflow-does-not-mutate-recording",snapshotOverflowIsObservational);
  test("clock-callback-outside-collector-lock",clocksAreOutsideCollectorLock);
  test("simultaneous-same-context-resume-rejected",simultaneousResumeRejected);
  test("non-lifo-source-segments-retire-without-dangling-link",nonLifoSourceSegments);
  test("non-lifo-resume-paused-segment-retire",nonLifoResumeAndPausedSegment);
  test("concurrent-independent-tasks-and-snapshots",concurrentTasksAndSnapshots);
  test("finished-token-and-terminal-task-rejected",finishedTokensRejected);
  test("parent-abort-defers-cleanly-until-child-retirement",parentAbortDefersCleanly);
  test("delete-paused-segment-from-inner-resume-only-context",deletePausedSegmentWithoutInnerSource);
  test("remove-middle-resume-restores-outer-context",middleResumeReparentsToOuter);
  test("source-guard-depth-cap-preserves-call-and-restarts",sourceGuardDepthCap);
  test("crosscollector-resume-depth-cap-shared-tls-restarts",crossCollectorResumeDepthCap);
  test("duplicate-resume-suppresses-unconditional-attribution",duplicateResumeSuppressesUnconditionalHooks);
  test("capped-resume-suppresses-unconditional-attribution",cappedResumeSuppressesUnconditionalHooks);
  test("failed-guards-non-lifo-retired-parent-no-stale-restore",failedGuardNonLifoWithRetiredParent);
  test("actual-platform-clocks-two-thread-retained-call",actualPlatformClockMigration);
  std::cout<<"{\"schema\":\"nex.private-task-profile-collector-test/1\",\"ok\":true,\"cases\":"<<passed.size()
    <<",\"assertions\":"<<assertions.load()<<",\"actual_threads\":2,\"deterministic_clocks\":true,\"actual_platform_clock_smoke\":true"
    <<",\"public_profiling_claim\":false,\"scheduler_integration_claim\":false,\"request_scope_integration_claim\":false,\"passed\":[";
  for(size_t i=0;i<passed.size();++i){if(i)std::cout<<',';std::cout<<'"'<<passed[i]<<'"';}
  std::cout<<"]}\n";return 0;
}catch(const std::exception &error){
  std::cerr<<"after "<<passed.size()<<" cases / "<<assertions.load()<<" assertions: "<<error.what()<<'\n';return 1;
}
