#include "nex_cell_host.h"
#include "nex_task_frame.h"
#include <atomic>
#include <iostream>
#include <stdexcept>
#include <thread>
using namespace nexrt;
namespace {
std::thread::id owner;
int turns=0,retired=0;
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
void onOwner(){require(std::this_thread::get_id()==owner,"source task left its owner thread");++turns;}
int64_t read(const Value &value){auto *handle=makeHandle(value);return nex_cell_read_i64(handle,0,0);}
void write(const Value &value,int64_t next){nex_cell_write_i64(makeHandle(value),next,0,0);}
TaskBody child(TaskGroup &group,Value value,Value){
 onOwner();write(value,41);co_await group.yield();onOwner();write(value,read(value)+1);co_return value;
}
TaskBody root(TaskGroup &group,Value value,Value){
 onOwner();auto scope=group.openScope(3);auto task=group.spawn(scope,child,value);
 auto answer=co_await group.await(task);onOwner();require(answer.value.object==value.object,"future copied cell identity");
 co_await group.leaveScope(scope);onOwner();co_return Value(read(value));
}
TaskBody fault(TaskGroup &group,Value value,Value){
 onOwner();co_await group.yield();onOwner();
 throw NativeSourceException("typed","cell fault","",9,std::make_shared<const SourceErrorPayload>(std::string(64,'a'),value));co_return Value();
}
TaskBody catches(TaskGroup &group,Value value,Value){
 auto scope=group.openScope(2);auto task=group.spawn(scope,fault,value);bool caught=false;
 try{(void)co_await group.await(task);}catch(const NativeSourceException &error){
  onOwner();require(error.payload&&error.payload->value.object==value.object,"source packet lost cell identity");write(value,42);caught=true;
 }
 co_await group.leaveScope(scope);require(caught,"typed cell error disappeared");co_return Value(read(value));
}
TaskBody endless(TaskGroup &group,Value value,Value){
 struct Retire {~Retire(){++retired;}} retire;
 for(;;){onOwner();write(value,read(value)+1);co_await group.yield();}co_return Value();
}
int64_t unused(void*){throw std::runtime_error("mismatched code ran");}
TaskBody mismatched(TaskGroup &group,Value,Value){
 const TaskCodeDescriptor code{unused,nullptr,nullptr,nullptr,nullptr,taskCodeTypedSourceExceptionABI,0,0,0,4,0};
 return executeTaskFrame(group,NativeTaskFrame(code,{},{}));
}
TaskBody ownerDescriptor(TaskGroup &group,Value abi,Value){
 const TaskCodeDescriptor code{unused,nullptr,nullptr,nullptr,nullptr,abi.scalar,0,0,0,4,taskCodeDeclaredState};
 return executeTaskFrame(group,NativeTaskFrame(code,{},{}));
}
template<class F> void trap(const std::string &code,F action){bool failed=false;try{action();}catch(const Trap &error){require(error.code==code,"wrong native owner error");failed=true;}require(failed,"expected native owner error");}
}
int runOwnerTaskRuntime(){try{
 owner=std::this_thread::get_id();int cases=0;
 for(auto body:{root,catches}){
  {RequestScope request(100000,5000);auto value=readHandle(nex_cell_new_i64(1,0,0));
   {TaskGroup group(managedTaskOwnerExecution(),64,{},false,true);require(group.ownerThreadExecution(),"owner mode missing");
    auto task=group.spawn(body,value);require(group.join(task).scalar==42,"owner result differs");group.finish();}
   // Group completion must retain the host/request's still-live heap.
   require(read(value)==42,"joined group closed its enclosing heap");write(value,43);request.poll();
  }require(liveObjects==0,"owner execution leaked source values");++cases;
 }
 {RequestScope request;auto value=readHandle(nex_cell_new_i64(1,0,0));TaskGroup workers(1);
  trap("E_TASK_VALUE",[&]{workers.spawn(child,value);});workers.finish();
  for(auto abi:{taskCodeManagedReferencesABI,taskCodeManagedReferencesDevelopmentABI}){
   TaskGroup otherWorkers(1,64,{},false,true);auto ticket=otherWorkers.spawn(ownerDescriptor,Value(abi));
   trap("E_TASK_STATE",[&]{(void)otherWorkers.join(ticket);});otherWorkers.finish();
  }++cases;}
 {RequestScope request;TaskGroup group(TaskOwnerExecution{},64,{},false,true);
  auto task=group.spawn(mismatched);trap("E_TASK_STATE",[&]{(void)group.join(task);});group.finish();++cases;}
 {RequestScope request;TaskGroup group(TaskOwnerExecution{});std::atomic<bool> rejected=false;
  std::jthread other([&]{try{group.spawn(root);}catch(const Trap &error){rejected=error.code=="E_TASK_SCOPE";}});other.join();
  require(rejected,"foreign thread entered owner coordinator");group.finish();++cases;}
 {RequestScope request(70,5000);auto value=readHandle(nex_cell_new_i64(0,0,0));TaskGroup group(managedTaskOwnerExecution());
  auto task=group.spawn(endless,value);trap("E_LIMIT",[&]{(void)group.join(task);});++cases;}
 require(retired==1&&inRequestScope()==false,"budget cancellation did not retire owned frames");
 {RequestScope request(100000,5000);int polls=0;request.setCancellation([&]{return ++polls>25;});
  auto value=readHandle(nex_cell_new_i64(0,0,0));TaskGroup group(managedTaskOwnerExecution());
  auto task=group.spawn(endless,value);trap("E_CANCELLED",[&]{(void)group.join(task);});++cases;}
 require(retired==2&&!inRequestScope()&&liveObjects==0,"cancelled owner left context/values");
 require(cases==7,"owner scenario count differs");
#ifndef NEX_OWNER_TASK_INLINE
 std::cout<<"{\"ok\":true,\"cases\":"<<cases<<",\"turns\":"<<turns<<"}\n";
#endif
 return 0;
 }catch(const Trap &error){std::cerr<<error.code<<": "<<trapMessage(error)<<'\n';return 1;}
 catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 2;}
}
#ifndef NEX_OWNER_TASK_INLINE
int main(){return runOwnerTaskRuntime();}
#endif
