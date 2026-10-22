#include "nex/task_reference.h"
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <iostream>
#include <mutex>
#include <thread>

using namespace nex;
using namespace std::chrono_literals;
namespace {
size_t cases=0;
void require(bool value,const std::string &message){if(!value)throw std::runtime_error(message);}
template<class F>void eventually(F predicate,const std::string &message){
  auto until=std::chrono::steady_clock::now()+2s;
  while(!predicate()){if(std::chrono::steady_clock::now()>=until)throw std::runtime_error(message);std::this_thread::sleep_for(1ms);}
}
template<class F>void dataRejected(const std::string &code,F run){
  try{run();}catch(const nexrt::DataError &error){require(error.code==code,"expected "+code+", got "+error.code);++cases;return;}
  throw std::runtime_error("expected "+code);
}
template<class F>Error sourceRejected(const std::string &code,F run){
  auto before=nexrt::liveObjects.load();
  try{run();}catch(const Error &error){
    require(error.code==code,"expected "+code+", got "+error.code+": "+error.what());
    require(nexrt::liveObjects.load()==before,"external reference failure leaked owned source values");++cases;return error;
  }
  throw std::runtime_error("expected "+code);
}
struct Gate {
  std::mutex mutex;
  std::condition_variable changed;
  bool released=false;
  std::atomic<unsigned> started{0},retired{0},cancelSeen{0};
  void release(){std::lock_guard lock(mutex);released=true;changed.notify_all();}
};
struct ReleaseOnExit {
  std::vector<std::shared_ptr<Gate>> gates;
  ~ReleaseOnExit(){for(auto &gate:gates)gate->release();}
};
struct Operation: nexrt::TaskExternalOperation {
  std::shared_ptr<Gate> gate;
  bool cooperative=true,holdOnCancel=false,badAllocation=false;
  nexrt::TaskExternalResult result;
  std::string thrown;
  explicit Operation(std::shared_ptr<Gate> state,bool cooperate=true,bool hold=false)
      :gate(std::move(state)),cooperative(cooperate),holdOnCancel(hold){}
  ~Operation()override{++gate->retired;gate->changed.notify_all();}
  nexrt::TaskExternalResult run(const nexrt::TaskExternalControl &control)override{
    ++gate->started;gate->changed.notify_all();
    try{
      std::unique_lock lock(gate->mutex);
      while(!gate->released){lock.unlock();if(cooperative)control.checkpoint();lock.lock();gate->changed.wait_for(lock,1ms);}
      lock.unlock();if(cooperative)control.checkpoint();
    }catch(const nexrt::DataError &error){
      if(error.code=="E_CANCELLED")++gate->cancelSeen;
      if(holdOnCancel){std::unique_lock lock(gate->mutex);gate->changed.wait(lock,[&]{return gate->released;});}
      throw;
    }
    if(badAllocation)throw std::bad_alloc();
    if(!thrown.empty())throw nexrt::DataError(thrown,"controlled raw host failure");
    return std::move(result);
  }
};
std::shared_ptr<Operation> immediate(std::shared_ptr<Gate> gate){gate->release();return std::make_shared<Operation>(std::move(gate));}
void ready(TaskReferenceExternalMailbox &mailbox){eventually([&]{return bool(mailbox.ready());},"physical operation failed to retire");}
void empty(const TaskReferenceExternalMailbox &mailbox){auto s=mailbox.stats();require(!s.pending&&!s.reservedBytes&&!s.running&&!s.ready,"mailbox retained pending ticket/bytes/worker/result");}
void mailboxTests(){
  auto deadline=std::chrono::steady_clock::now()+10s;
  for(auto limits:{nexrt::TaskExternalLimits{0,1,1,1},nexrt::TaskExternalLimits{3,1,1,1},
      nexrt::TaskExternalLimits{1,65,1,1},nexrt::TaskExternalLimits{1,1,8388609,1},
      nexrt::TaskExternalLimits{1,1,1,1048577}})
    dataRejected("E_OPTION",[&]{TaskReferenceExternalMailbox box(deadline,{},limits);});
  TaskReferenceExternalMailbox box(deadline,{},nexrt::TaskExternalLimits{1,1,8,8});
  auto gate=std::make_shared<Gate>();
  auto ticket=box.submit(7,std::make_shared<Operation>(gate),8);
  eventually([&]{return gate->started.load()==1;},"worker did not start");
  dataRejected("E_TASK_STATE",[&]{box.take(ticket);});
  for(unsigned field=0;field<4;++field){
    auto corrupt=ticket;
    if(field==0)++corrupt.scheduler;if(field==1)++corrupt.generation;
    if(field==2)++corrupt.owner;if(field==3)corrupt.slot=64;
    dataRejected("E_TASK_STATE",[&]{box.cancel(corrupt);});
  }
  dataRejected("E_TASK_STATE",[&]{box.take({});});
  dataRejected("E_LIMIT",[&]{box.submit(8,immediate(std::make_shared<Gate>()),1);});
  require(box.cancel(ticket)&&!box.cancel(ticket),"cancellation was not single request");
  // Cooperative cancellation can retire quickly. Its quota remains occupied
  // until the creating coordinator consumes the physically retired result.
  ready(box);require(box.stats().pending==1&&box.stats().reservedBytes==8,"cancel released quota before coordinator consumption");
  require(box.take(ticket).errorCode=="E_CANCELLED"&&gate->retired==1,"cancel completed before operation/lease destruction");empty(box);++cases;
  dataRejected("E_TASK_STATE",[&]{box.take(ticket);});
  auto replacement=box.submit(7,immediate(std::make_shared<Gate>()),0);
  require(replacement.slot==ticket.slot&&replacement.generation!=ticket.generation,"slot reuse did not advance generation");
  dataRejected("E_TASK_STATE",[&]{box.take(ticket);});
  TaskReferenceExternalMailbox other(deadline);
  dataRejected("E_TASK_STATE",[&]{other.cancel(replacement);});
  std::atomic<bool> rejectedThread=false;
  std::thread foreign([&]{try{box.take(replacement);}catch(const nexrt::DataError &error){rejectedThread=error.code=="E_TASK_STATE";}});foreign.join();
  require(rejectedThread,"foreign thread accepted a completion");++cases;
  ready(box);require(box.take(replacement).errorCode.empty(),"replacement did not complete");empty(box);++cases;

  auto largeGate=std::make_shared<Gate>();auto large=immediate(largeGate);large->result.bytes.resize(9);
  auto tooLarge=box.submit(9,std::move(large),8);ready(box);
  require(box.take(tooLarge).errorCode=="E_LIMIT"&&largeGate->retired==1,"oversized raw result escaped its reservation");empty(box);++cases;
  dataRejected("E_LIMIT",[&]{box.submit(1,immediate(std::make_shared<Gate>()),9);});
  auto diagnostic=immediate(std::make_shared<Gate>());diagnostic->result.errorMessage.resize(4097);
  auto badDiagnostic=box.submit(1,std::move(diagnostic),0);ready(box);
  require(box.take(badDiagnostic).errorCode=="E_LIMIT","raw diagnostic bound was not enforced");++cases;
  auto reserved=immediate(std::make_shared<Gate>());reserved->result.bytes.reserve(4096);
  auto reservedTicket=box.submit(1,std::move(reserved),8);ready(box);
  auto reservedFailure=box.take(reservedTicket);
  require(reservedFailure.errorCode=="E_LIMIT"&&reservedFailure.bytes.capacity()==0,"empty reserved vector escaped byte quota or retained rejected storage: code="+
    reservedFailure.errorCode+", capacity="+std::to_string(reservedFailure.bytes.capacity()));++cases;
  for(bool code:{false,true}){
    auto diagnosticCapacity=immediate(std::make_shared<Gate>());
    if(code)diagnosticCapacity->result.errorCode.reserve(8192);else diagnosticCapacity->result.errorMessage.reserve(8192);
    auto diagnosticTicket=box.submit(1,std::move(diagnosticCapacity),0);ready(box);
    auto failure=box.take(diagnosticTicket);
    require(failure.errorCode=="E_LIMIT"&&failure.errorCode.capacity()<=128&&failure.errorMessage.capacity()<=4096,
      "empty reserved diagnostic escaped fixed quota or retained rejected storage");++cases;
  }
  TaskReferenceExternalMailbox smallResult(deadline,{},nexrt::TaskExternalLimits{1,1,16,8});
  auto maximum=immediate(std::make_shared<Gate>());maximum->result.bytes.reserve(9);
  auto maximumTicket=smallResult.submit(1,std::move(maximum),16);ready(smallResult);
  require(smallResult.take(maximumTicket).errorCode=="E_LIMIT","retained vector capacity escaped per-result maximum");empty(smallResult);++cases;

  // A noncooperative operation is not reported clean on logical cancellation.
  auto held=std::make_shared<Gate>();ReleaseOnExit heldRelease{{held}};
  auto pending=box.submit(2,std::make_shared<Operation>(held,false),8);
  eventually([&]{return held->started.load()==1;},"held operation did not start");box.close();
  require(box.stats().pending==1&&box.stats().reservedBytes==8&&!box.ready(),"close falsely retired an active operation");
  dataRejected("E_CANCELLED",[&]{box.submit(2,immediate(std::make_shared<Gate>()),0);});
  dataRejected("E_TASK_STATE",[&]{box.take(pending);});
  std::jthread retire([held]{std::this_thread::sleep_for(25ms);held->release();});
  auto start=std::chrono::steady_clock::now();box.drain();
  require(std::chrono::steady_clock::now()-start>=20ms&&held->retired==1,"drain did not fence physical lease retirement");empty(box);++cases;

  std::stop_source cancellation;
  TaskReferenceExternalMailbox stopped(deadline,cancellation.get_token());auto waiting=std::make_shared<Gate>();ReleaseOnExit waitingRelease{{waiting}};
  stopped.submit(1,std::make_shared<Operation>(waiting,false),1);
  std::jthread stop([&]{eventually([&]{return waiting->started.load()==1;},"stop fixture did not start");std::this_thread::sleep_for(10ms);cancellation.request_stop();});
  start=std::chrono::steady_clock::now();stopped.wait();
  require(cancellation.stop_requested()&&std::chrono::steady_clock::now()-start<1s,"root cancellation failed to wake parked coordinator");
  require(stopped.stats().pending==1&&!stopped.ready(),"cancellation wake falsely delivered a raw completion");
  waiting->release();stopped.drain();empty(stopped);++cases;

  TaskReferenceExternalMailbox parallel(deadline,{},nexrt::TaskExternalLimits{2,3,3,1});
  auto a=std::make_shared<Gate>(),b=std::make_shared<Gate>(),c=std::make_shared<Gate>();
  ReleaseOnExit parallelRelease{{a,b,c}};
  parallel.submit(1,std::make_shared<Operation>(a,false),1);
  parallel.submit(2,std::make_shared<Operation>(b,false),1);
  parallel.submit(3,std::make_shared<Operation>(c,false),1);
  eventually([&]{return a->started.load()+b->started.load()+c->started.load()==2;},"bounded pair of workers did not start");
  require(parallel.stats().running==2&&parallel.stats().maximumRunning==2,"external physical concurrency exceeded its independent two-worker pool");
  a->release();b->release();c->release();parallel.drain();empty(parallel);++cases;
}

Program source(const std::string &body){auto p=parse("module reference_external;\n"+body,"reference_external.nex");check(p);return p;}
struct Host:TaskReferenceExternalHost {
  std::shared_ptr<Gate> gate=std::make_shared<Gate>();
  bool cooperative=true,holdOnCancel=false,badAllocation=false,skip=false,throwPrepare=false,throwAdmit=false;
  nexrt::TaskExternalResult raw;
  std::string thrown;
  size_t prepared=0,admitted=0;
  std::atomic<size_t> scopesRetired{0};
  std::thread::id coordinator=std::this_thread::get_id();
  std::optional<TaskReferenceExternalRequest> prepare(size_t,Span)override{
    require(std::this_thread::get_id()==coordinator,"host preparation escaped coordinator");++prepared;
    if(throwPrepare)throw std::runtime_error("controlled prepare failure");
    if(skip)return {};
    auto op=std::make_shared<Operation>(gate,cooperative,holdOnCancel);op->result=raw;op->thrown=thrown;op->badAllocation=badAllocation;
    return TaskReferenceExternalRequest{std::move(op),16};
  }
  void admit(size_t,const nexrt::TaskExternalResult &)override{
    require(std::this_thread::get_id()==coordinator,"host admission escaped coordinator");
    require(gate->retired.load()>0,"host admitted before physical lease retirement");++admitted;
    if(throwAdmit)throw std::runtime_error("controlled admission failure");
  }
  void scopeRetired(size_t)noexcept override{++scopesRetired;}
};
const std::string simple="fn main()->i64 !{task}{let owned:list<str>=[\"held\",\"🧠\"];task_yield();return 40+len(owned);}";
const std::string spinning=R"(
fn spin()->i64{let owned:list<str>=["held","🧠"];var n:i64=0;while true{assert(len(owned)==2);n=n+1;}return n;}
fn main()->i64 !{io,task}{print("before");return with_tasks(2,fn(scope:task_scope)->i64 !{task}{
 let external:task<unit>=task_spawn(scope,fn()->unit !{task}{let held:list<str>=["lease","value"];task_yield();assert(len(held)==2);});
 return spin();
});}
)";
void schedulerTests(){
  auto p=source(simple);auto before=nexrt::liveObjects.load();
  {Host host;std::jthread release([&]{eventually([&]{return host.gate->started.load()==1;},"scheduler operation did not start");std::this_thread::sleep_for(10ms);host.gate->release();});
    auto result=evaluateTaskReference(p,"main",{},1000000,{},nullptr,&host);
    require(result.value.scalar==42&&host.prepared==1&&host.admitted==1,"empty-ready external completion did not resume unit continuation");
    auto s=result.external;require(!s.pending&&!s.reservedBytes&&!s.ready&&!s.running&&s.submitted==1&&s.retired==1&&s.consumed==1,"successful root retained external resources");
    require(result.executionWorkers==1,"independent AST execution stopped being serial");++cases;
  }
  require(nexrt::liveObjects.load()==before,"external success retained owned values");
  {Host host;host.skip=true;auto result=evaluateTaskReference(p,"main",{},1000000,{},nullptr,&host);
    require(result.value.scalar==42&&result.external.submitted==0&&host.admitted==0,"host nullopt changed ordinary yield");++cases;}
  {Host host;host.gate->release();
    auto immediateLoop=source("fn main()->i64 !{task}{var n:i64=0;while n<64{task_yield();n=n+1;}return 42;}");
    auto result=evaluateTaskReference(immediateLoop,"main",{},1000000,{},nullptr,&host);
    require(result.value.scalar==42&&host.admitted==64&&result.external.submitted==64&&result.external.retired==64&&!result.external.pending,
      "immediate completions lost a wake, reused a ticket or leaked a slot");++cases;
  }
  auto progress=source(R"(
fn main()->i64 !{task}{return with_tasks(2,fn(scope:task_scope)->i64 !{task}{
 let pending:task<i64>=task_spawn(scope,fn()->i64 !{task}{task_yield();return 40;});
 let other:task<i64>=task_spawn(scope,fn()->i64{return 2;});
 return task_wait(pending)+task_wait(other);
});}
)");
  {Host host;bool progressed=false;
    auto result=evaluateTaskReference(progress,"main",{},1000000,[&](size_t owner,const TaskTransition &transition){
      if(owner==2&&transition.kind==TaskTransition::Done){
        eventually([&]{return host.gate->started.load()==1;},"other-job fixture did not start external operation");
        require(host.gate->retired==0,"other AST job progressed only after external retirement");progressed=true;host.gate->release();
      }
    },nullptr,&host);
    require(result.value.scalar==42&&progressed,"parked external task blocked independent AST work");++cases;
  }
  auto cancelled=source(R"(
fn main()->i64 !{task}{return with_tasks(2,fn(scope:task_scope)->i64 !{task}{
 let pending:task<i64>=task_spawn(scope,fn()->i64 !{task}{let held:list<str>=["held"];task_yield();assert(false);return len(held);});
 assert(task_cancel(pending));return 42;
});}
)");
  {Host host;host.holdOnCancel=true;std::atomic<bool> returned=false,premature=false;
    std::jthread release([&]{
      eventually([&]{return host.gate->cancelSeen.load()==1;},"task cancellation was not propagated to host control");
      std::this_thread::sleep_for(25ms);premature=returned.load()||host.gate->retired.load()!=0;host.gate->release();
    });
    auto result=evaluateTaskReference(cancelled,"main",{},1000000,[&](size_t,const TaskTransition &transition){
      if(transition.operation=="task_cancel")eventually([&]{return host.gate->started.load()==1;},"cancel fixture did not start its physical operation");
    },nullptr,&host);returned=true;
    require(result.value.scalar==42&&!premature&&host.gate->retired==1&&host.admitted==0,"cancelled scope/future completed before physical retirement or resumed source");
    require(result.external.cancelRequests==1&&!result.external.pending,"logical cancellation leaked its external slot");++cases;
  }
  // Completion can be queued before task_cancel, but only the coordinator
  // accepts it and a cancelled source frame must never be resumed.
  {Host host;host.gate->release();
    auto result=evaluateTaskReference(cancelled,"main",{},1000000,[&](size_t,const TaskTransition &transition){
      if(transition.operation=="task_cancel")eventually([&]{return host.gate->retired.load()==1;},"queued completion race did not retire");
    },nullptr,&host);
    require(result.value.scalar==42&&host.gate->retired==1,"completion/cancel race resumed a cancelled continuation");++cases;
  }
  // An external stop wakes the parked coordinator immediately, while an
  // intentionally noncooperative physical operation still delays completion.
  {Host host;host.cooperative=false;host.thrown="E_IO";std::stop_source stop;host.cancellation=stop.get_token();std::atomic<bool> returned=false,premature=false;
    std::jthread release([&]{eventually([&]{return host.gate->started.load()==1;},"root cancel fixture did not start");stop.request_stop();
      std::this_thread::sleep_for(25ms);premature=returned.load()||host.gate->retired.load()!=0;host.gate->release();});
    sourceRejected("E_CANCELLED",[&]{evaluateTaskReference(p,"main",{},1000000,{},nullptr,&host);});returned=true;
    require(!premature&&host.gate->retired==1&&host.admitted==0,"root cancellation returned before physical drain or admitted stale bytes");
  }
  auto externallyBlocked=source(R"(
fn main()->i64 !{task}{return with_tasks(1,fn(scope:task_scope)->i64 !{task}{
 let pending:task<i64>=task_spawn(scope,fn()->i64 !{task}{let held:list<str>=["owned"];task_yield();assert(false);return len(held);});
 return task_wait(pending);
});}
)");
  // Fatal physical resource failures survive both global abort and local task
  // cancellation. Ordinary E_IO above remains discarded during cancellation.
  for(bool rootAbort:{false,true})for(const std::string code:{"E_MEMORY","E_LIMIT","E_TIMEOUT"}){
    Host host;host.cooperative=false;host.badAllocation=code=="E_MEMORY";if(!host.badAllocation)host.thrown=code;
    std::stop_source stop;host.cancellation=stop.get_token();std::atomic<bool> cancelIssued=false,returned=false,premature=false;
    std::jthread release([&]{eventually([&]{return host.gate->started.load()==1;},"fatal cleanup operation did not start");
      if(rootAbort)stop.request_stop();else eventually([&]{return cancelIssued.load();},"fatal cleanup task was not cancelled");
      std::this_thread::sleep_for(25ms);premature=returned.load()||host.scopesRetired.load()!=0||host.gate->retired.load()!=0;host.gate->release();});
    sourceRejected(code,[&]{evaluateTaskReference(rootAbort?externallyBlocked:cancelled,"main",{},1000000,[&](size_t,const TaskTransition &transition){
      if(transition.operation=="task_cancel"){
        eventually([&]{return host.gate->started.load()==1;},"fatal task cancellation raced before physical start");cancelIssued=true;
      }
    },nullptr,&host);});returned=true;
    require(!premature&&host.gate->retired==1&&host.scopesRetired==1&&host.admitted==0,
      "fatal cleanup error lost physical/scope fence or admitted cancelled source");
  }
  // The region owner itself can be externally parked with no member jobs.
  // Root cancellation must retain that empty region's ledger until retirement.
  for(bool deadline:{false,true}){Host host;host.cooperative=false;std::stop_source stop;host.cancellation=stop.get_token();std::atomic<bool> premature=false;
    auto nestedOwner=source("fn main()->i64 !{task}{return with_tasks(1,fn(scope:task_scope)->i64 !{task}{task_yield();return 42;});}");
    std::jthread release([&]{eventually([&]{return host.gate->started.load()==1;},"empty-region owner did not start external operation");
      if(!deadline)stop.request_stop();std::this_thread::sleep_for(deadline?200ms:25ms);
      premature=host.scopesRetired.load()!=0||host.gate->retired.load()!=0;host.gate->release();});
    auto regionLimits=nexrt::TaskExecutionLimits{1000000,100,1};
    sourceRejected(deadline?"E_TIMEOUT":"E_CANCELLED",[&]{evaluateTaskReference(nestedOwner,"main",{},1000000,{},deadline?&regionLimits:nullptr,&host);});
    require(!premature&&host.gate->retired==1&&host.scopesRetired==1&&host.admitted==0,
      "empty owned region closed before its owner's physical external retirement");
  }
  auto timed=nexrt::TaskExecutionLimits{nexrt::maximumTaskExecutionSteps,100,1};
  for(bool pureHelper:{false,true}){
    Host host;host.cooperative=false;std::atomic<bool> returned=false,premature=false;
    // The already selected root timeout remains the first fatal, even when a
    // later physical memory/limit failure arrives while it is draining.
    host.badAllocation=!pureHelper;if(pureHelper)host.thrown="E_LIMIT";
    std::jthread release([&]{eventually([&]{return host.gate->started.load()==1;},"deadline fixture did not start");
      std::this_thread::sleep_for(200ms);premature=returned.load()||host.gate->retired.load()!=0;host.gate->release();});
    auto program=pureHelper?source(spinning):p;
    auto error=sourceRejected("E_TIMEOUT",[&]{evaluateTaskReference(program,"main",{},timed.steps,{},&timed,&host);});returned=true;
    require(!premature&&host.gate->retired==1&&host.admitted==0,"deadline released root/scope/frame before external retirement");
    require(error.span.file=="reference_external.nex","external deadline lost source location");
    if(pureHelper)require(error.output=="before\n","pure-helper deadline lost source output");
  }
  {Host host;std::stop_source stop;stop.request_stop();host.cancellation=stop.get_token();
    sourceRejected("E_CANCELLED",[&]{evaluateTaskReference(p,"main",{},1000000,{},nullptr,&host);});
    require(!host.prepared&&!host.gate->started,"pre-cancelled root admitted physical work");}
  {Host host;host.throwPrepare=true;
    sourceRejected("E_TASK_HOST",[&]{evaluateTaskReference(p,"main",{},1000000,{},nullptr,&host);});
    require(!host.gate->started&&!host.gate->retired,"failed preparation created a physical operation");}
  {Host host;host.throwAdmit=true;host.gate->release();
    sourceRejected("E_TASK_HOST",[&]{evaluateTaskReference(p,"main",{},1000000,{},nullptr,&host);});
    require(host.gate->retired==1,"failed admission retained a physical lease");}
  {Host host;host.thrown="E_IO";host.gate->release();
    sourceRejected("E_IO",[&]{evaluateTaskReference(p,"main",{},1000000,{},nullptr,&host);});require(host.admitted==0,"raw host failure reached unit admission");}
  {Host host;host.raw.bytes={1};host.gate->release();
    sourceRejected("E_TASK_VALUE",[&]{evaluateTaskReference(p,"main",{},1000000,{},nullptr,&host);});require(host.admitted==0,"invalid payload reached unit admission");}
  {Host host;auto filesystem=source("server fn main()->i64 !{fs,task}{task_yield();return 42;}");
    sourceRejected("E_TASK_UNIMPLEMENTED",[&]{evaluateTaskReference(filesystem,"main",{},1000000,{},nullptr,&host);});
    require(host.prepared==0,"experimental host widened ordinary filesystem constructor support");}
  auto stalled=source("fn main()->i64 !{task}{return with_tasks(1,fn(scope:task_scope)->i64 !{task}{let queue:channel<i64>=channel_new<i64>(scope,0);return unwrap(task_recv(queue));});}");
  sourceRejected("E_TASK_DEADLOCK",[&]{evaluateTaskReference(stalled);});
  require(nexrt::liveObjects.load()==before,"scheduler tests retained source frames/values/capabilities");++cases;
}
}
int main()try{
  mailboxTests();schedulerTests();require(nexrt::liveObjects.load()==0,"probe leaked owned values");
  std::cout<<json(llvm::json::Object{{"ok",true},{"cases",int64_t(cases)},
    {"independent_reference_coordinator",true},{"source_execution_workers",1},
    {"bounded_raw_mailbox",true},{"owner_generation_single_use",true},
    {"cancel_deadline_physical_retirement_fence",true},{"empty_owned_region_retirement_fence",true},
    {"retained_capacity_quotas",true},{"fatal_resource_cleanup_priority",true},{"public_source_async_io",false}})<<'\n';return 0;
}catch(const std::exception &error){std::cerr<<"after "<<cases<<" checks: "<<error.what()<<'\n';return 1;}
