#include "nex_tasks.h"
#include "nex_files.h"
#include <array>
#include <chrono>
#include <condition_variable>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <thread>

namespace {
using namespace nexrt;
void require(bool condition,const char *message){if(!condition){std::fprintf(stderr,"external kernel: %s\n",message);std::abort();}}
template<class F>void rejected(const char *code,F action){bool caught=false;try{action();}catch(const DataError &error){require(error.code==code,"wrong host error");caught=true;}catch(const Trap &error){if(error.code!=code)std::fprintf(stderr,"expected %s got %s:%s\n",code,error.code.c_str(),error.what());require(error.code==code,"wrong runtime error");caught=true;}catch(const std::bad_alloc &){require(std::string(code)=="E_MEMORY","wrong allocation error");caught=true;}require(caught,"missing checked error");}
template<class F>void until(F condition){auto end=std::chrono::steady_clock::now()+std::chrono::seconds(5);while(!condition()){require(std::chrono::steady_clock::now()<end,"fixture synchronization timed out");std::this_thread::yield();}}
struct Gate {
  std::mutex mutex;std::condition_variable changed;bool released=false;
  std::atomic<unsigned> started{0},retired{0},destroyed{0};std::thread::id worker;
  void wait(){std::unique_lock lock(mutex);worker=std::this_thread::get_id();++started;changed.notify_all();changed.wait(lock,[&]{return released;});}
  void release(){std::lock_guard lock(mutex);released=true;changed.notify_all();}
};
struct Operation final:TaskExternalOperation {
  std::shared_ptr<Gate> gate;size_t bytes;bool block;
  Operation(std::shared_ptr<Gate> gate,size_t bytes=8,bool block=true):gate(std::move(gate)),bytes(bytes),block(block){}
  ~Operation(){++gate->destroyed;}
  TaskExternalResult run(const TaskExternalControl &control)override{
    struct Finally {Gate &gate;~Finally(){++gate.retired;}}finally{*gate};
    if(block)gate->wait();else{gate->worker=std::this_thread::get_id();++gate->started;}
    control.checkpoint();TaskExternalResult result;result.bytes.assign(bytes,42);return result;
  }
};
struct CapacityOnly final:TaskExternalOperation {
  int field;explicit CapacityOnly(int field):field(field){}
  TaskExternalResult run(const TaskExternalControl &)override{
    TaskExternalResult result;
    if(field==0)result.bytes.reserve(1024);
    else if(field==1)result.errorCode.reserve(1024);
    else result.errorMessage.reserve(8192);
    return result;
  }
};
struct TextFailure final:TaskExternalOperation {
  std::string text;explicit TextFailure(std::string text):text(std::move(text)){}
  TaskExternalResult run(const TaskExternalControl &)override{throw DataError("E_TEXT",text);}
};
struct GatedCapacity final:TaskExternalOperation {
  std::shared_ptr<Gate> gate;int field;
  GatedCapacity(std::shared_ptr<Gate> gate,int field):gate(std::move(gate)),field(field){}
  ~GatedCapacity(){++gate->destroyed;}
  TaskExternalResult run(const TaskExternalControl &control)override{gate->wait();++gate->retired;return CapacityOnly(field).run(control);}
};
struct FaultOperation final:TaskExternalOperation {
  std::shared_ptr<Gate> gate;std::string code;bool payload;
  FaultOperation(std::shared_ptr<Gate> gate,std::string code,bool payload=false):gate(std::move(gate)),code(std::move(code)),payload(payload){}
  ~FaultOperation(){++gate->destroyed;}
  TaskExternalResult run(const TaskExternalControl &)override{
    gate->wait();++gate->retired;
    if(payload){TaskExternalResult result;result.errorCode=code;result.errorMessage="raw host diagnostic";return result;}
    if(code=="E_MEMORY")throw std::bad_alloc();
    throw DataError(code,"raw host failure after cancellation");
  }
};
void cancelledPoolPriority(){
  for(auto code:{"E_MEMORY","E_LIMIT","E_TIMEOUT","E_ITEM","E_CANCELLED"})for(bool payload:{false,true}){
    auto gate=std::make_shared<Gate>();TaskExternalPool pool({1,1,8,8});
    auto ticket=pool.submit(1,std::make_shared<FaultOperation>(gate,code,payload),8);until([&]{return gate->started==1;});
    pool.cancel(ticket);gate->release();until([&]{return pool.ready(ticket);});
    bool fatal=std::string(code)=="E_MEMORY"||std::string(code)=="E_LIMIT"||std::string(code)=="E_TIMEOUT";
    rejected(fatal?code:"E_CANCELLED",[&]{pool.take(ticket);});pool.drain();require(pool.stats().reservedBytes==0,"cancelled failure quota survived");
  }
}
void clean(){require(!inRequestScope(),"request survived");require(liveObjects==0,"source owned value survived");nex_runtime_finish();}
void poolCases(){
  {
    TaskExternalPool textPool;const auto text=std::string("before\0after🌍",16)+std::string(5000,'x');
    auto ticket=textPool.submit(1,std::make_shared<TextFailure>(text),8);until([&]{return textPool.ready(ticket);});bool caught=false;
    try{textPool.take(ticket);}catch(const DataError &e){caught=true;require(e.code=="E_TEXT"&&e.message==text.substr(0,taskExternalErrorMessageCapacity),"IO mailbox lost NUL suffix or exceeded quota");}
    require(caught,"IO failure disappeared");textPool.drain();
  }
  auto gate=std::make_shared<Gate>(),queued=std::make_shared<Gate>();std::atomic<unsigned> published{0};
  TaskExternalPool *inspection=nullptr;
  TaskExternalPool pool({1,2,16,8},[&](const TaskExternalTicket &){(void)inspection->stats();++published;});inspection=&pool;
  auto first=pool.submit(7,std::make_shared<Operation>(gate),8);until([&]{return gate->started==1;});
  auto second=pool.submit(8,std::make_shared<Operation>(queued),8);pool.cancel(second);
  rejected("E_LIMIT",[&]{pool.submit(9,std::make_shared<Operation>(queued),1);});
  rejected("E_TASK_STATE",[&]{(void)pool.take(first);});
  require(pool.stats().tickets==2&&pool.stats().reservedBytes==16,"cancel released quota before physical retirement");
  gate->release();until([&]{return published==2;});
  require(queued->started==0&&queued->destroyed>=1,"queued cancellation started operation or retained lease");
  require(gate->destroyed==1&&gate->retired==1,"operation finally/destructor did not precede notification");
  TaskExternalPool foreign({1,1,8,8});rejected("E_TASK_SCOPE",[&]{foreign.take(first);});
  require(pool.take(first).bytes.size()==8,"lost payload");rejected("E_TASK_STATE",[&]{pool.take(first);});
  rejected("E_CANCELLED",[&]{pool.take(second);});
  auto newer=pool.submit(7,std::make_shared<Operation>(queued,8,false),8);
  rejected("E_TASK_STATE",[&]{pool.cancel(first);});until([&]{return pool.ready(newer);});pool.take(newer);
  require(pool.stats().tickets==0&&pool.stats().reservedBytes==0,"retired quota survived");
  auto oversize=pool.submit(0,std::make_shared<Operation>(queued,9,false),8);
  until([&]{return pool.ready(oversize);});rejected("E_LIMIT",[&]{pool.take(oversize);});
  for(int field=0;field<3;++field){auto ticket=pool.submit(0,std::make_shared<CapacityOnly>(field),8);until([&]{return pool.ready(ticket);});rejected("E_LIMIT",[&]{pool.take(ticket);});}
  pool.drain();foreign.drain();
  auto byteGate=std::make_shared<Gate>();TaskExternalPool bytes({1,2,8,8});
  auto held=bytes.submit(0,std::make_shared<Operation>(byteGate),8);until([&]{return byteGate->started==1;});
  rejected("E_LIMIT",[&]{bytes.submit(0,std::make_shared<Operation>(queued,1,false),1);});byteGate->release();until([&]{return bytes.ready(held);});bytes.take(held);bytes.drain();
}
void overlap(){
  auto left=std::make_shared<Gate>(),right=std::make_shared<Gate>();TaskExternalPool pool;
  auto a=pool.submit(1,std::make_shared<Operation>(left),8),b=pool.submit(2,std::make_shared<Operation>(right),8);
  until([&]{return left->started&&right->started;});require(pool.stats().running==2&&pool.stats().maximumRunning==2,"IO workers did not overlap");
  left->release();right->release();until([&]{return pool.ready(a)&&pool.ready(b);});pool.take(a);pool.take(b);pool.drain();
}
std::shared_ptr<Gate> currentGate;
std::shared_ptr<TaskExternalOperation> prepared;
TaskExternalTicket savedTicket;
std::atomic<unsigned> frameDestroyed{0},progress{0},afterScope{0};
std::atomic<unsigned> ownerLeaving{0};
std::string currentFault;bool currentPayload=false;
TaskGroup *inspectionGroup=nullptr;std::atomic<unsigned> exceptionDestroyed{0},failureOperationDestroyed{0};
struct HostFailure final:DataError {
  HostFailure():DataError("E_ITEM","private host failure"){}
  ~HostFailure()override{if(inspectionGroup)(void)inspectionGroup->externalStats();++exceptionDestroyed;}
};
struct FailedOperation final:TaskExternalOperation {
  ~FailedOperation(){if(inspectionGroup)(void)inspectionGroup->externalStats();++failureOperationDestroyed;}
  TaskExternalResult run(const TaskExternalControl &)override{throw HostFailure();}
};
struct FrameFinally {~FrameFinally(){++frameDestroyed;}};
TaskBody external(TaskGroup &group,Value,Value){
  FrameFinally finally;Value retained(string("retained🧠"));(void)makeHandle(Value(string("temporary🧠")));
  auto operation=prepared?std::exchange(prepared,{}):std::make_shared<Operation>(currentGate);
  savedTicket=group.submitExternal(std::move(operation),1024*1024);
  auto result=co_await group.awaitExternal(savedTicket).at(73);
  require(std::this_thread::get_id()!=currentGate->worker,"IO worker resumed source task");
  require(retained.object->text=="retained🧠","owned value lost during external park");co_return Value(int64_t(result.bytes.size()));
}
TaskBody sibling(TaskGroup &,Value,Value){++progress;co_return Value(42);}
TaskBody crossGroup(TaskGroup &group,Value,Value){
  bool caught=false;try{(void)co_await group.awaitExternal(savedTicket);}catch(const Trap &error){require(error.code=="E_TASK_SCOPE","foreign completion error");caught=true;}
  require(caught,"cross-group external ticket accepted");co_return Value(42);
}
TaskBody immediate(TaskGroup &group,Value,Value){
  auto gate=std::make_shared<Gate>();
  for(unsigned i=0;i<128;++i){
    auto ticket=group.submitExternal(std::make_shared<Operation>(gate,1,false),1);
    if(i%2)co_await group.yield();
    auto result=co_await group.awaitExternal(ticket);require(result.bytes==std::vector<uint8_t>{42},"lost immediate completion");
    bool caught=false;try{(void)co_await group.awaitExternal(ticket);}catch(const Trap &error){require(error.code=="E_TASK_STATE","double completion error");caught=true;}
    require(caught,"external completion accepted twice");
  }
  co_return Value(42);
}
TaskBody checkedFailure(TaskGroup &group,Value input,Value){
  FrameFinally finally;auto ticket=group.submitExternal(std::make_shared<FailedOperation>(),1);
  if(input.scalar)co_return Value(42); // The owner still joins physical failure.
  bool caught=false;
  try{(void)co_await group.awaitExternal(ticket).at(73);}
  catch(const Trap &error){require(error.code=="E_ITEM"&&error.line==73,"external error lost source location");caught=true;}
  require(caught,"external failure disappeared");co_return Value(42);
}
void failureCleanup(){
  RequestScope request;TaskGroup group(1);inspectionGroup=&group;frameDestroyed=exceptionDestroyed=failureOperationDestroyed=0;
  require(group.join(group.spawn(checkedFailure)).scalar==42,"checked external failure did not resume owner");
  rejected("E_ITEM",[&]{group.join(group.spawn(checkedFailure,Value(1)));});group.finish();
  require(frameDestroyed==2&&exceptionDestroyed==2&&failureOperationDestroyed==2,"host finally/exception cleanup survived completion");
  require(group.externalStats().tickets==0,"failed raw mailbox survived");inspectionGroup=nullptr;
}
void progressAndIdentity(){
  RequestScope request;TaskGroup group(1);currentGate=std::make_shared<Gate>();frameDestroyed=progress=0;
  auto task=group.spawn(external);until([&]{return currentGate->started==1;});
  require(group.join(group.spawn(sibling)).scalar==42&&progress==1,"parked IO blocked executor sibling");
  {TaskGroup other(1);require(other.join(other.spawn(crossGroup)).scalar==42,"cross-group probe failed");other.finish();}
  currentGate->release();require(group.join(task).scalar==8,"external result lost");
  require(group.join(group.spawn(immediate)).scalar==42,"immediate completion race failed");group.finish();
  require(group.externalStats().tickets==0&&group.externalStats().reservedBytes==0,"group payload survived finish");
  require(frameDestroyed==1&&currentGate->destroyed==1,"frame or operation survived join");
}
void cancellationDrain(){
  RequestScope request;TaskGroup group(1);currentGate=std::make_shared<Gate>();frameDestroyed=0;
  auto task=group.spawn(external);until([&]{return currentGate->started==1;});require(group.cancel(task),"task cancellation rejected");
  std::thread controller([&]{until([&]{return frameDestroyed==1;});require(currentGate->retired==0,"host operation retired before fixture release");require(group.externalStats().reservedBytes==1024*1024,"inflight cancellation released payload quota");currentGate->release();});
  rejected("E_CANCELLED",[&]{group.join(task);});controller.join();
  require(currentGate->retired==1&&currentGate->destroyed==1,"cancelled future published before physical retirement");group.finish();
}
void scopeDrain(){
  RequestScope request;TaskGroup group(1);currentGate=std::make_shared<Gate>();frameDestroyed=afterScope=0;
  // Let the child enter the host service before requesting lexical cancellation.
  auto root=group.spawn([](TaskGroup &group,Value,Value)->TaskBody{
    auto scope=group.openScope(1);(void)group.spawn(scope,external);
    while(!currentGate->started)co_await group.yield();
    co_await group.leaveScope(scope,true);++afterScope;co_return Value(42);
  });
  std::thread controller([&]{until([&]{return frameDestroyed==1;});require(afterScope==0&&currentGate->retired==0,"scope closed before physical retirement");currentGate->release();});
  require(group.join(root).scalar==42,"scope cancellation failed");controller.join();require(afterScope==1&&currentGate->destroyed==1,"scope did not drain external ownership");group.finish();
}
void awaitedChildDrain(){
  for(unsigned workers:{1u,2u}){
    RequestScope request;TaskGroup group(workers);currentGate=std::make_shared<Gate>();frameDestroyed=0;
    auto root=group.spawn([](TaskGroup &group,Value,Value)->TaskBody{
      auto scope=group.openScope(1);(void)group.spawn(scope,external);
      co_await group.leaveScope(scope);co_return Value(42);
    });
    until([&]{return currentGate->started==1;});currentGate->release();
    require(group.join(root).scalar==42,"parent scope consumed a live child's awaited ticket");group.finish();
    require(frameDestroyed==1&&currentGate->destroyed==1&&group.externalStats().tickets==0,"awaited child scope did not retire ownership");
  }
  clean();
}
TaskBody ownerScope(TaskGroup &group,Value input,Value){
  auto scope=group.openScope(1);
  (void)group.submitExternal(std::make_shared<Operation>(currentGate),1024*1024);
  while(!currentGate->started)co_await group.yield();
  ownerLeaving=1;co_await group.leaveScope(scope,bool(input.scalar));++afterScope;co_return Value(42);
}
TaskBody abandonedNestedScope(TaskGroup &group,Value,Value){
  FrameFinally finally;(void)group.openScope(1);(void)group.openScope(1);
  (void)group.submitExternal(std::make_shared<Operation>(currentGate),1024*1024);
  while(!currentGate->started)co_await group.yield();
  throw Trap("E_ITEM","owner failure before nested scope drain",91);co_return Value();
}
void lexicalOwnerDrain(){
  for(int abort:{0,1}){
    RequestScope request;TaskGroup group(1);currentGate=std::make_shared<Gate>();ownerLeaving=afterScope=progress=0;
    auto owner=group.spawn(ownerScope,Value(abort));until([&]{return ownerLeaving==1;});
    require(group.join(group.spawn(sibling)).scalar==42,"scope drain blocked unrelated task");
    require(afterScope==0&&currentGate->retired==0,"lexical owner scope closed before physical retirement");
    require(group.externalStats().reservedBytes==1024*1024,"lexical scope dropped host reservation");
    currentGate->release();require(group.join(owner).scalar==42,"lexical owner did not resume after drain");group.finish();
    require(afterScope==1&&currentGate->destroyed==1&&group.externalStats().tickets==0,"lexical owner failed physical cleanup");
  }
  clean();
  {
    RequestScope request;TaskGroup group(1);currentGate=std::make_shared<Gate>();frameDestroyed=0;
    auto owner=group.spawn(abandonedNestedScope);
    std::thread controller([&]{until([&]{return frameDestroyed==1;});require(currentGate->retired==0&&group.externalStats().reservedBytes==1024*1024,"ancestor scope failed to retain descendant host operation");currentGate->release();});
    rejected("E_ITEM",[&]{group.join(owner);});controller.join();group.finish();
    require(currentGate->destroyed==1&&group.externalStats().tickets==0,"nested owner scope leaked physical work");
  }
  clean();
}
TaskBody ownerFaultScope(TaskGroup &group,Value,Value){
  auto scope=group.openScope(1);(void)group.submitExternal(std::make_shared<FaultOperation>(currentGate,currentFault,currentPayload),8);
  while(!currentGate->started)co_await group.yield();
  ownerLeaving=1;co_await group.leaveScope(scope,true);++afterScope;co_return Value(42);
}
TaskBody faultWait(TaskGroup &group,Value,Value){
  FrameFinally finally;auto ticket=group.submitExternal(std::make_shared<FaultOperation>(currentGate,currentFault,currentPayload),8);
  (void)co_await group.awaitExternal(ticket);++afterScope;co_return Value(42);
}
void fatalScopePriority(){
  for(auto code:{"E_MEMORY","E_LIMIT","E_TIMEOUT","E_ITEM","E_CANCELLED"})for(bool payload:{false,true}){
    RequestScope request;TaskGroup group(1);currentGate=std::make_shared<Gate>();currentFault=code;currentPayload=payload;ownerLeaving=afterScope=0;
    auto owner=group.spawn(ownerFaultScope);until([&]{return ownerLeaving==1;});group.join(group.spawn(sibling));
    require(afterScope==0&&group.externalStats().reservedBytes==8,"aborted lexical fault scope escaped physical drain");currentGate->release();
    bool fatal=currentFault=="E_MEMORY"||currentFault=="E_LIMIT"||currentFault=="E_TIMEOUT";
    if(fatal)rejected(code,[&]{group.join(owner);});else require(group.join(owner).scalar==42,"ordinary abort failure escaped scope");
    require(afterScope==(fatal?0u:1u)&&currentGate->destroyed==1,"abort failure priority or cleanup differs");group.finish();
  }
  clean();
  for(bool payload:{false,true}){
    RequestScope request;TaskGroup group(1);currentGate=std::make_shared<Gate>();currentFault="E_MEMORY";currentPayload=payload;frameDestroyed=afterScope=0;
    auto owner=group.spawn(faultWait);until([&]{return currentGate->started==1;});
    request.setCancellation([]{return true;});
    std::thread controller([&]{until([&]{return frameDestroyed==1;});currentGate->release();});
    rejected("E_MEMORY",[&]{group.join(owner);});controller.join();require(afterScope==0,"cancelled source resumed for fatal completion");rejected("E_CANCELLED",[&]{group.finish();});
  }
  clean();
}
TaskBody selectedFatal(TaskGroup &group,Value,Value){
  FrameFinally finally;
  (void)group.submitExternal(std::make_shared<FaultOperation>(currentGate,"E_MEMORY"),8);
  while(!currentGate->started)co_await group.yield();
  throw Trap(currentFault,"fatal selected before physical host failure",91);co_return Value();
}
void firstFatalPriority(){
  for(auto code:{"E_LIMIT","E_TIMEOUT"})for(bool finishOnly:{false,true}){
    RequestScope request;TaskGroup group(1);currentGate=std::make_shared<Gate>();currentFault=code;frameDestroyed=0;
    auto root=group.spawn(selectedFatal);
    std::thread controller([&]{until([&]{return frameDestroyed==1;});currentGate->release();});
    rejected(code,[&]{if(finishOnly)group.finish();else group.join(root);});controller.join();
    require(currentGate->retired==1&&currentGate->destroyed==1,"fatal selection escaped physical drain");
    if(!finishOnly)group.finish();
  }
  clean();
}
void cancelledCapacityPriority(){
  for(int field=0;field<3;++field){
    RequestScope request;TaskGroup group(1);currentGate=std::make_shared<Gate>();ownerLeaving=afterScope=0;
    auto root=group.spawn([](TaskGroup &group,Value input,Value)->TaskBody{
      auto scope=group.openScope(1);(void)group.submitExternal(std::make_shared<GatedCapacity>(currentGate,int(input.scalar)),8);
      while(!currentGate->started)co_await group.yield();
      ownerLeaving=1;co_await group.leaveScope(scope,true);++afterScope;co_return Value(42);
    },Value(field));
    until([&]{return ownerLeaving==1;});group.join(group.spawn(sibling));currentGate->release();
    rejected("E_LIMIT",[&]{group.join(root);});group.finish();
    require(afterScope==0&&currentGate->destroyed==1&&group.externalStats().tickets==0,"cancellation masked raw storage limit");
  }
  clean();
}
void deadlineAndDestructor(){
  {
    RequestScope request(1000000,20);TaskGroup group(1);currentGate=std::make_shared<Gate>();frameDestroyed=0;
    auto task=group.spawn(external);until([&]{return currentGate->started==1;});
    std::thread controller([&]{until([&]{return frameDestroyed==1;});require(currentGate->retired==0,"deadline fixture retired early");currentGate->release();});
    rejected("E_TIMEOUT",[&]{group.join(task);});controller.join();require(currentGate->destroyed==1,"deadline escaped physical drain");rejected("E_TIMEOUT",[&]{group.finish();});
  }
  clean();
  {
    RequestScope request;currentGate=std::make_shared<Gate>();frameDestroyed=0;
    std::thread controller;
    {TaskGroup group(1);(void)group.spawn(external);until([&]{return currentGate->started==1;});controller=std::thread([&]{until([&]{return frameDestroyed==1;});currentGate->release();});}
    controller.join();require(currentGate->destroyed==1&&currentGate->retired==1,"group destructor detached host operation");
  }
  clean();
}
#ifndef _WIN32
struct ReadOperation final:TaskExternalOperation {
  FileReadLease lease;explicit ReadOperation(FileReadLease lease):lease(std::move(lease)){}
  TaskExternalResult run(const TaskExternalControl &control)override{control.checkpoint();TaskExternalResult result;result.bytes=lease.read([&]{control.checkpoint();});control.checkpoint();return result;}
};
void realRead(){
  auto path=std::filesystem::temp_directory_path()/("nex-external-read-"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()));
  std::filesystem::create_directory(path);{std::ofstream output(path/"data",std::ios::binary);output<<"real external bytes";}
  {
    TextFiles files(path.string(),false);FileScope grant(files);RequestScope request;TaskGroup group(1);currentGate=std::make_shared<Gate>();
    prepared=std::make_shared<ReadOperation>(captureFileReadLease("data",false));
    require(group.join(group.spawn(external)).scalar==19,"real lease IO result differs");group.finish();
  }
  std::filesystem::remove_all(path);clean();
}
#endif
}
int main(){
  poolCases();cancelledPoolPriority();overlap();clean();progressAndIdentity();clean();failureCleanup();clean();cancellationDrain();clean();scopeDrain();clean();awaitedChildDrain();lexicalOwnerDrain();fatalScopePriority();firstFatalPriority();cancelledCapacityPriority();deadlineAndDestructor();
#ifndef _WIN32
  realRead();
#endif
  std::puts("external native kernel: bounds, tickets, real IO, child ownership, first fatal, cancelled raw payload/capacity, physical drain and owned cleanup passed");
}
