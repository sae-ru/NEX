#include "nex_parallel.h"
#include <algorithm>
#include <atomic>
#include <barrier>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <map>
#include <mutex>
#include <new>
#include <set>
#include <thread>

extern "C" nexrt::Handle *nex_string_new(const char*,int64_t,int64_t);
extern "C" nexrt::Handle *nex_collection_get_heap(nexrt::Handle*,int64_t,int64_t);
extern "C" void *nex_closure_code(nexrt::Handle*);
namespace {
using nexrt::Value;using nexrt::Data;
std::mutex allocationsMutex,threadsMutex;
std::map<const void*,int> allocations;
size_t poolAllocations[2]{},poolFrees[2]{};
thread_local bool failHandleAllocation=false;
thread_local int failAllocationAfter=-1;
std::set<std::thread::id> threads;
std::atomic<unsigned> calls{0},running{0},maximumRunning{0};
std::atomic<bool> higherFailed{false};
std::barrier<> *rendezvous=nullptr;
void require(bool condition,const char *message){
  if(!condition){std::fprintf(stderr,"structured worker probe: %s\n",message);std::abort();}
}
void recordThread(){std::lock_guard lock(threadsMutex);threads.insert(std::this_thread::get_id());}
struct Running {
  Running(){auto count=++running;auto maximum=maximumRunning.load();while(maximum<count&&!maximumRunning.compare_exchange_weak(maximum,count)){};recordThread();}
  ~Running(){--running;}
};
Value list(std::initializer_list<Value> values){auto data=std::make_shared<Data>(Data::List);data->values=values;return Value(std::move(data));}
Value integers(size_t count){auto data=std::make_shared<Data>(Data::List);for(size_t i=0;i<count;++i)data->values.emplace_back(int64_t(i));return Value(std::move(data));}
template<class F> void expect(const char *code,F action){
  bool caught=false;try{action();}catch(const nexrt::Trap &error){require(error.code==code,"wrong checked error");caught=true;}
  require(caught,"checked error was not raised");require(running==0,"callback survived a failed group");
}
void clean(){
  require(running==0,"worker survived its group");require(!nexrt::inRequestScope(),"request context survived its scope");
  require(nexrt::liveObjects==0,"managed object survived its scope");
  {std::lock_guard lock(allocationsMutex);require(allocations.empty(),"profiled allocation survived its scope");}
  nex_runtime_finish();calls=0;maximumRunning=0;higherFailed=false;
  {std::lock_guard lock(threadsMutex);threads.clear();}
}
Value ordered(const Value &item,const Value &environment){
  Running active;++calls;rendezvous->arrive_and_wait();
  auto *temporary=nex_string_new("temporary",9,11);(void)temporary;
  auto text=environment.object->values[0].object->text+std::to_string(item.scalar);
  auto *result=nex_string_new(text.data(),int64_t(text.size()),11);
  return nexrt::readHandle(result); // The job releases this handle before handoff.
}
Value identity(const Value &item,const Value &environment){++calls;recordThread();return Value(item.scalar+environment.scalar);}
const char *zero="0000000000000000000000000000000000000000000000000000000000000000";
const char *one="1111111111111111111111111111111111111111111111111111111111111111";
const nexrt::NativeFunctionSite function{zero,zero,zero};
const nexrt::NativeSite source{&function,one,"worker_failure",1,2};
Value competingFailures(const Value &item,const Value &){
  Running active;++calls;(void)nex_string_new("before failure",14,12);
  if(item.scalar==0){while(!higherFailed)nexrt::pollHostOperation(13);nexrt::runtimeFail("E_FIRST","lowest input index",nexrt::SourceLocation{14,&source});}
  higherFailed=true;throw nexrt::Trap("E_SECOND","higher index finished first",15);
}
Value spin(const Value &,const Value &){Running active;++calls;for(;;)nexrt::pollHostOperation(16);}
Value budgeted(const Value &item,const Value &){
  Running active;++calls;
  for(size_t i=0;i<60;++i)nexrt::pollHostOperation(17);
  return item;
}
Value nested(const Value &item,const Value &){
  Running active;rendezvous->arrive_and_wait();
  return nexrt::parallelValues(list({Value(1),Value(2),Value(3)}),item,16,identity);
}
Value badOutput(const Value &,const Value &){Running active;++calls;return Value(nexrt::diagnosticFile(9));}
Value allocationFailure(const Value &item,const Value &){
  Running active;++calls;(void)nex_string_new("owned before fault",18,18);
  if(item.scalar==1)failHandleAllocation=true;
  (void)nex_string_new("owned after fault",17,19);return item;
}
Value throwingCleanup(const Value &item,const Value &){
  Running active;++calls;(void)nex_string_new("owned on throw",14,20);
  throw std::runtime_error("trusted callback failed");return item;
}
std::atomic<unsigned> cleanups{0};
void cleanup()noexcept{++cleanups;}
Value registeredCleanup(const Value &item,const Value &){
  Running active;++calls;nexrt::registerRuntimeCleanup(cleanup);return item;
}
using K=nexrt::ParallelValueKind;
Value callable(void *code,std::vector<Value> captures={}){
  auto data=std::make_shared<Data>(Data::Closure);data->code=code;data->values=std::move(captures);return Value(std::move(data));
}
nexrt::Handle *capturedTarget(nexrt::Handle *environment,int64_t input){
  Running active;++calls;rendezvous->arrive_and_wait();
  auto *prefix=nex_collection_get_heap(environment,0,31);
  (void)nex_string_new("unnamed temporary",17,31);
  auto text=nexrt::readHandle(prefix).object->text+std::to_string(input);
  return nex_string_new(text.data(),int64_t(text.size()),31);
}
void capturedBridge(nexrt::Handle *environment,int64_t input,nexrt::Handle *heap,void *result){
  require(heap==nullptr,"scalar argument unexpectedly allocated a heap handle");
  auto target=reinterpret_cast<nexrt::Handle*(*)(nexrt::Handle*,int64_t)>(nex_closure_code(environment));
  nex_parallel_return_heap(result,target(environment,input));
}
void floatBridge(nexrt::Handle *,int64_t input,nexrt::Handle *heap,void *result){
  ++calls;require(!heap,"float argument unexpectedly allocated a heap handle");
  nex_parallel_return_i64(result,nexrt::floatBits(nexrt::floatValue(input)+0.5),2);
}
void boolBridge(nexrt::Handle *,int64_t input,nexrt::Handle *heap,void *result){
  ++calls;require(!heap,"boolean argument unexpectedly allocated a heap handle");nex_parallel_return_i64(result,!input,1);
}
void heapAliasBridge(nexrt::Handle *,int64_t input,nexrt::Handle *heap,void *result){
  ++calls;require(input==0&&heap,"heap argument crossed as scalar bits");nex_parallel_return_heap(result,heap);
}
void scalarBridge(nexrt::Handle *,int64_t input,nexrt::Handle *,void *result){++calls;nex_parallel_return_i64(result,input+1,0);}
void nestedCompiledBridge(nexrt::Handle *,int64_t input,nexrt::Handle *,void *result){
  ++calls;auto closure=callable(reinterpret_cast<void*>(scalarBridge));
  auto nested=nexrt::parallelCompiledValues(integers(3),closure,16,scalarBridge,K::I64,K::I64);
  require(nested.object->values[2].scalar==3,"nested compiled result changed");
  nex_parallel_return_i64(result,input+int64_t(nested.object->values.size()),0);
}
void missingBridge(nexrt::Handle *,int64_t,nexrt::Handle *,void *){++calls;}
void duplicateBridge(nexrt::Handle *,int64_t input,nexrt::Handle *,void *result){
  ++calls;nex_parallel_return_i64(result,input,0);nex_parallel_return_i64(result,input+1,0);
}
void unfinishedOwnerBridge(nexrt::Handle *,int64_t input,nexrt::Handle *,void *result){
  ++calls;(void)nex_owned_enter();(void)nex_string_new("nested temporary",16,32);
  if(input==0)throw nexrt::Trap("E_COMPILED","compiled callback failed",32);
  nex_parallel_return_i64(result,input,0);
}
void heapFaultBridge(nexrt::Handle *,int64_t input,nexrt::Handle *,void *result){
  ++calls;(void)nex_string_new("before fault",12,33);if(input==1)failHandleAllocation=true;
  auto *value=nex_string_new("after fault",11,33);nex_parallel_return_heap(result,value);
}
void forbiddenResultBridge(nexrt::Handle *,int64_t,nexrt::Handle *,void *result){
  ++calls;auto *value=nexrt::makeHandle(Value(nexrt::diagnosticFile(17)));nex_parallel_return_heap(result,value);
}
std::atomic<void*> compiledDestination{nullptr};
std::atomic<bool> foreignDestinationRejected{false};
void foreignDestinationBridge(nexrt::Handle *,int64_t input,nexrt::Handle *,void *result){
  ++calls;if(input==0)compiledDestination=result;rendezvous->arrive_and_wait();
  if(input==1){try{nex_parallel_return_i64(compiledDestination.load(),41,0);}
    catch(const nexrt::Trap &error){foreignDestinationRejected=error.code=="E_CONTEXT";}}
  rendezvous->arrive_and_wait();nex_parallel_return_i64(result,input,0);
}
}
// Fail each coordinator allocation in turn, including native thread creation's
// state allocation. Worker-thread allocations are deliberately independent.
void *operator new(size_t size){
  if(failAllocationAfter==0){failAllocationAfter=-1;throw std::bad_alloc();}
  if(failAllocationAfter>0)--failAllocationAfter;
  if(auto *pointer=std::malloc(size?size:1))return pointer;
  throw std::bad_alloc();
}
void operator delete(void *pointer)noexcept{std::free(pointer);}
void operator delete(void *pointer,size_t)noexcept{std::free(pointer);}
// Independent allocation accounting exercises the actual runtime hooks from
// multiple threads, including failed handle construction. No hook simulates a
// managed allocation or supplies a language value/result.
extern "C" void nex_profile_enter(const char*,const char*,int64_t,const char*){}
extern "C" void nex_profile_leave(){}
extern "C" void nex_profile_unwind(){}
extern "C" void nex_profile_allocation(const void *pointer,size_t,int pool){
  if(pool==0&&failHandleAllocation){failHandleAllocation=false;throw std::bad_alloc();}
  std::lock_guard lock(allocationsMutex);require(pool>=0&&pool<2,"unknown memory pool");
  require(allocations.emplace(pointer,pool).second,"allocation was registered twice");++poolAllocations[pool];
}
extern "C" void nex_profile_free(const void *pointer){
  std::lock_guard lock(allocationsMutex);auto found=allocations.find(pointer);require(found!=allocations.end(),"free without completed allocation");
  ++poolFrees[found->second];allocations.erase(found);
}
int main(){
  unsigned cases=0;
  {
    nexrt::RequestScope scope;auto input=integers(16);
    auto capture=std::make_shared<Data>(Data::Closure);capture->values.emplace_back(nexrt::string("Я🧠:"));
    std::barrier barrier(4);rendezvous=&barrier;
    auto *parentHandle=nex_string_new("parent",6,10);
    auto output=nexrt::parallelValues(input,Value(capture),4,ordered);
    require(calls==16&&threads.size()==4&&maximumRunning==4,"four callbacks did not overlap on four real threads");
    require(output.object->values.size()==16&&input.object->values[9].scalar==9,"input/result shape changed");
    for(size_t i=0;i<16;++i)require(output.object->values[i].object->text=="Я🧠:"+std::to_string(i),"input order or Unicode capture changed");
    scope.poll();require(nexrt::readHandle(parentHandle).object->text=="parent","worker cleanup revoked the caller's handles");
    nex_release(parentHandle);
  }clean();++cases;
  {
    nexrt::RequestScope scope;bool caught=false;
    try{(void)nexrt::parallelValues(integers(2),Value(),2,competingFailures);}
    catch(const nexrt::LocatedTrap &error){require(error.code=="E_FIRST"&&error.line==14&&error.source.find(one)!=std::string::npos,"lowest-index source diagnostic was lost");caught=true;}
    require(caught&&calls==2&&running==0,"failed workers were not joined");scope.poll();
  }clean();++cases;
  {
    nexrt::RequestScope scope;auto coordinator=std::this_thread::get_id();unsigned checks=0;
    scope.setCancellation([&]{require(std::this_thread::get_id()==coordinator,"host cancellation callback ran on a worker");++checks;return running.load()!=0;});
    expect("E_CANCELLED",[&]{(void)nexrt::parallelValues(integers(4),Value(),4,spin);});
    require(checks>=2&&calls>0,"waiting coordinator did not observe cancellation");
  }clean();++cases;
  {
    nexrt::RequestScope scope;
    scope.setCancellation([]{if(running.load())throw std::runtime_error("cancellation monitor failed");return false;});
    expect("E_RUNTIME",[&]{(void)nexrt::parallelValues(integers(4),Value(),4,spin);});
    require(calls>0,"monitor failure fixture never entered a worker");scope.setCancellation({});scope.poll();
  }clean();++cases;
  {
    nexrt::RequestScope scope(std::numeric_limits<uint64_t>::max(),100);
    expect("E_TIMEOUT",[&]{(void)nexrt::parallelValues(integers(4),Value(),4,spin);});
    require(calls>0,"deadline fixture never entered a worker");
  }clean();++cases;
  {
    nexrt::RequestScope scope(100);scope.poll();
    expect("E_LIMIT",[&]{(void)nexrt::parallelValues(integers(2),Value(),2,budgeted);});
    require(calls==2,"execution budget was renewed separately for each worker");
    expect("E_LIMIT",[&]{scope.poll();});
  }clean();++cases;
  {
    nexrt::RequestScope scope(2);
    auto result=nexrt::parallelValues(integers(1),Value(9),1,identity);
    require(result.object->values[0].scalar==9,"coordinator waiting consumed execution steps");
    expect("E_LIMIT",[&]{scope.poll();});
  }clean();++cases;
  {
    nexrt::RequestScope scope;std::barrier barrier(4);rendezvous=&barrier;
    auto output=nexrt::parallelValues(integers(4),Value(),4,nested);
    require(threads.size()==4&&calls==12,"nested group created extra operating-system threads");
    for(size_t i=0;i<4;++i)for(size_t j=0;j<3;++j)require(output.object->values[i].object->values[j].scalar==int64_t(i+j+1),"nested result differs");
    scope.poll();
  }clean();++cases;
  {
    nexrt::RequestScope scope;auto file=Value(nexrt::diagnosticFile(5));
    auto capture=std::make_shared<Data>(Data::Closure);capture->values.push_back(list({file}));
    expect("E_PARALLEL_VALUE",[&]{(void)nexrt::parallelValues(integers(2),Value(capture),2,identity);});
    expect("E_PARALLEL_VALUE",[&]{(void)nexrt::parallelValues(list({list({file})}),Value(),2,identity);});
    require(calls==0,"resource-bearing input reached a worker");scope.poll();
  }clean();++cases;
  {
    nexrt::RequestScope scope;expect("E_PARALLEL_VALUE",[&]{(void)nexrt::parallelValues(integers(2),Value(),2,badOutput);});
    require(calls==2,"output failure did not join all callbacks");scope.poll();
  }clean();++cases;
  {
    nexrt::RequestScope scope;expect("E_MEMORY",[&]{(void)nexrt::parallelValues(integers(4),Value(),2,allocationFailure);});
    require(calls==4,"allocation failure escaped worker ownership cleanup");scope.poll();
  }clean();++cases;
  {
    nexrt::RequestScope scope;expect("E_RUNTIME",[&]{(void)nexrt::parallelValues(integers(4),Value(),2,throwingCleanup);});scope.poll();
  }clean();++cases;
  {
    nexrt::RequestScope scope;cleanups=0;
    auto output=nexrt::parallelValues(integers(4),Value(),2,registeredCleanup);
    require(output.object->values.size()==4&&cleanups==4,"worker-local registered cleanup did not run exactly once per job");
    nexrt::cleanupRuntimeResources();require(cleanups==4,"worker cleanup leaked into the coordinator");scope.poll();
  }clean();++cases;
  {
    nexrt::RequestScope scope;auto empty=integers(0);
    require(nexrt::parallelValues(empty,Value(),16,identity).object->values.empty(),"empty group changed its value");
    expect("E_RANGE",[&]{(void)nexrt::parallelValues(empty,Value(),0,identity);});
    expect("E_RANGE",[&]{(void)nexrt::parallelValues(empty,Value(),17,identity);});
    expect("E_TYPE",[&]{(void)nexrt::parallelValues(Value(1),Value(),1,identity);});
    expect("E_CONTEXT",[&]{(void)nexrt::parallelValues(empty,Value(),1,nullptr);});
    expect("E_LIMIT",[&]{(void)nexrt::parallelValues(integers(65537),Value(),1,identity);});
    require(calls==0,"preflight failure started a callback");
  }clean();++cases;
  {
    nexrt::RequestScope scope;auto data=std::make_shared<Data>(Data::List);data->values.resize(nexrt::parallelMaximumNodes);
    expect("E_LIMIT",[&]{(void)nexrt::parallelValues(integers(1),Value(data),1,identity);});require(calls==0,"oversized value graph reached a worker");
  }clean();++cases;
  {
    expect("E_CONTEXT",[&]{(void)nexrt::parallelValues(integers(1),Value(),1,identity);});require(calls==0,"unscoped worker was started");
  }clean();++cases;
  {
    std::barrier start(2);std::atomic<bool> exhausted{false},completed{false},failed{false};
    std::thread limited([&]{
      try{
        nexrt::RequestScope scope(1);start.arrive_and_wait();
        try{(void)nexrt::parallelValues(integers(2),Value(),2,identity);}
        catch(const nexrt::Trap &error){exhausted=error.code=="E_LIMIT";}
      }catch(...){failed=true;}
    });
    std::thread ordinary([&]{
      try{
        nexrt::RequestScope scope;start.arrive_and_wait();
        auto result=nexrt::parallelValues(integers(16),Value(7),4,identity);
        completed=result.object->values.size()==16&&result.object->values[15].scalar==22;
        for(int i=0;i<20;++i)scope.poll();
      }catch(...){failed=true;}
    });
    limited.join();ordinary.join();require(!failed&&exhausted&&completed,"independent request groups shared execution or ownership state");
  }clean();++cases;
  {
    unsigned failed=0,completed=0;
    for(int allocation=0;allocation<96;++allocation){
      {
        nexrt::RequestScope scope;auto input=integers(8);
        failAllocationAfter=allocation;
        try{
          auto result=nexrt::parallelValues(input,Value(),4,identity);failAllocationAfter=-1;
          require(result.object->values.size()==8,"allocation sweep changed the result");++completed;
        }catch(const nexrt::Trap &error){failAllocationAfter=-1;require(error.code=="E_MEMORY","allocation sweep changed its failure");++failed;}
        require(failAllocationAfter<0,"allocation fault escaped the coordinator");scope.poll();
      }
      clean();
    }
    require(failed>=8&&completed>0,"allocation sweep did not cover failure and success");
  }clean();++cases;
  {
    nexrt::RequestScope scope;std::barrier barrier(4);rendezvous=&barrier;
    auto environment=callable(reinterpret_cast<void*>(capturedTarget),{Value(nexrt::string("Я🧠:"))});
    auto *parent=nex_string_new("parent",6,30);
    auto output=nexrt::parallelCompiledValues(integers(16),environment,4,capturedBridge,K::I64,K::Heap);
    require(calls==16&&threads.size()==4&&maximumRunning==4,"compiled bridge did not execute on four overlapping workers");
    for(size_t i=0;i<16;++i)require(output.object->values[i].object->text=="Я🧠:"+std::to_string(i),"compiled result retained freed storage or changed order");
    require(nexrt::readHandle(parent).object->text=="parent","compiled worker cleanup revoked coordinator handles");
    nex_release(parent);scope.poll();
  }clean();++cases;
  {
    nexrt::RequestScope scope;auto environment=callable(reinterpret_cast<void*>(floatBridge));
    auto output=nexrt::parallelCompiledValues(list({Value::floating(-1.25),Value::floating(0.0)}),environment,2,floatBridge,K::F64,K::F64);
    require(output.object->values[0].floating()==-0.75&&output.object->values[1].floating()==0.5,"f64 bridge confused raw bits with i64");
    auto booleans=nexrt::parallelCompiledValues(list({Value(0,true),Value(1,true)}),environment,2,boolBridge,K::Bool,K::Bool);
    require(booleans.object->values[0].tag==Value::Boolean&&booleans.object->values[0].scalar==1&&booleans.object->values[1].scalar==0,"boolean bridge changed tags or values");
  }clean();++cases;
  {
    nexrt::RequestScope scope;auto original=nexrt::string("borrowed Я🧠");auto environment=callable(reinterpret_cast<void*>(heapAliasBridge));
    auto output=nexrt::parallelCompiledValues(list({Value(original),Value(original)}),environment,2,heapAliasBridge,K::Heap,K::Heap);
    require(output.object->values[0].object==original&&output.object->values[1].object==original,"returning a borrowed input lost immutable identity");
  }clean();++cases;
  {
    nexrt::RequestScope scope;auto environment=callable(reinterpret_cast<void*>(nestedCompiledBridge));
    auto output=nexrt::parallelCompiledValues(integers(4),environment,2,nestedCompiledBridge,K::I64,K::I64);
    require(calls==16&&output.object->values[3].scalar==6,"nested compiled result destination or ownership scope leaked");
    expect("E_CONTEXT",[&]{nex_parallel_return_i64(reinterpret_cast<void*>(1),1,0);});
  }clean();++cases;
  {
    nexrt::RequestScope scope;auto environment=callable(reinterpret_cast<void*>(scalarBridge));
    expect("E_PARALLEL_VALUE",[&]{(void)nexrt::parallelCompiledValues(list({Value(0,true)}),environment,2,scalarBridge,K::I64,K::I64);});
    expect("E_CONTEXT",[&]{(void)nexrt::parallelCompiledValues(integers(1),environment,2,nullptr,K::I64,K::I64);});
    expect("E_CONTEXT",[&]{(void)nexrt::parallelCompiledValues(integers(1),environment,2,scalarBridge,K(9),K::I64);});
    expect("E_FUNCTION",[&]{(void)nexrt::parallelCompiledValues(integers(1),Value(0),2,scalarBridge,K::I64,K::I64);});
    auto invalid=callable(reinterpret_cast<void*>(scalarBridge),{Value(nexrt::diagnosticFile(8))});
    expect("E_PARALLEL_VALUE",[&]{(void)nexrt::parallelCompiledValues(integers(1),invalid,2,scalarBridge,K::I64,K::I64);});
    require(calls==0,"invalid compiled ABI/capture reached a callback");
  }clean();++cases;
  {
    nexrt::RequestScope scope;auto environment=callable(reinterpret_cast<void*>(scalarBridge));
    expect("E_PARALLEL_RESULT",[&]{(void)nexrt::parallelCompiledValues(integers(4),environment,2,missingBridge,K::I64,K::I64);});
    expect("E_PARALLEL_RESULT",[&]{(void)nexrt::parallelCompiledValues(integers(4),environment,2,duplicateBridge,K::I64,K::I64);});
    expect("E_PARALLEL_VALUE",[&]{(void)nexrt::parallelCompiledValues(integers(4),environment,2,scalarBridge,K::I64,K::Heap);});
    auto valid=nexrt::parallelCompiledValues(integers(4),environment,2,scalarBridge,K::I64,K::I64);
    require(valid.object->values[3].scalar==4,"failed compiled result poisoned later calls");
  }clean();++cases;
  {
    nexrt::RequestScope scope;auto environment=callable(reinterpret_cast<void*>(unfinishedOwnerBridge));
    expect("E_COMPILED",[&]{(void)nexrt::parallelCompiledValues(integers(4),environment,2,unfinishedOwnerBridge,K::I64,K::I64);});
    expect("E_MEMORY",[&]{(void)nexrt::parallelCompiledValues(integers(4),environment,2,heapFaultBridge,K::I64,K::Heap);});
    expect("E_PARALLEL_VALUE",[&]{(void)nexrt::parallelCompiledValues(integers(4),environment,2,forbiddenResultBridge,K::I64,K::Heap);});
    scope.poll();
  }clean();++cases;
  {
    nexrt::RequestScope scope;std::barrier barrier(2);rendezvous=&barrier;
    auto environment=callable(reinterpret_cast<void*>(foreignDestinationBridge));
    auto output=nexrt::parallelCompiledValues(integers(2),environment,2,foreignDestinationBridge,K::I64,K::I64);
    require(foreignDestinationRejected&&output.object->values[0].scalar==0&&output.object->values[1].scalar==1,"foreign-thread result destination was accepted or corrupted");
  }clean();++cases;
  require(poolAllocations[0]>0&&poolAllocations[1]>0,"ownership instrumentation did not observe both pools");
  require(poolAllocations[0]==poolFrees[0]&&poolAllocations[1]==poolFrees[1],"managed allocations were not balanced");
  std::printf("{\"ok\":true,\"cases\":%u,\"verified_simultaneous_workers\":4,\"handle_allocations\":%zu,\"object_allocations\":%zu,\"live_handles\":0,\"live_objects\":0}\n",cases,poolAllocations[0],poolAllocations[1]);
}
