#include "nex/task_reference.h"
#include "nex/task_frontend.h"
#include "nex/operations.h"
#include "nex_task_reference_value.h"
#include "nex_task_file_read.h"
#include "nex_task_foreign.h"
#include "nex_host.h"
#include <algorithm>
#include <chrono>
#include <deque>
#include <condition_variable>
#include <mutex>
#include <thread>
#include <unordered_set>

namespace nex {
using RV=nexrt::Value;
using RD=nexrt::Data;
struct TaskReferenceExternalMailbox::Impl {
  struct Pending {
    TaskReferenceExternalTicket ticket;
    std::shared_ptr<nexrt::TaskExternalOperation> operation;
    std::shared_ptr<std::atomic<bool>> cancelled=std::make_shared<std::atomic<bool>>(false);
    size_t reservation=0;
    bool done=false;
    nexrt::TaskExternalResult result;
  };
  inline static std::atomic<uint64_t> identities{0};
  const uint64_t identity=++identities;
  const std::thread::id coordinator=std::this_thread::get_id();
  Clock::time_point deadline;
  std::stop_token cancellation;
  nexrt::TaskExternalLimits limits;
  mutable std::mutex mutex;
  std::condition_variable changed;
  std::vector<std::shared_ptr<Pending>> slots;
  std::vector<uint64_t> generations;
  std::deque<std::shared_ptr<Pending>> queue;
  std::vector<std::thread> workers;
  TaskReferenceExternalStats counts;
  bool sealed=false,stopping=false;
  std::optional<std::stop_callback<std::function<void()>>> stopWake;

  Impl(Clock::time_point until,std::stop_token stop,nexrt::TaskExternalLimits bounds)
      :deadline(until),cancellation(stop),limits(bounds){
    if(!nexrt::validTaskExternalLimits(limits))
      throw nexrt::DataError("E_OPTION","invalid reference external mailbox bounds");
    slots.resize(limits.tickets);generations.resize(limits.tickets);
    stopWake.emplace(cancellation,std::function<void()>([this]{
      // Synchronize with the wait predicate/atomic unlock so a stop cannot
      // notify between the predicate check and parking the coordinator.
      {std::lock_guard lock(mutex);}changed.notify_all();
    }));
    try{for(size_t i=0;i<limits.workers;++i)workers.emplace_back([this]{worker();});}
    catch(...){shutdown();throw;}
  }
  ~Impl(){shutdown();}
  void coordinatorOnly()const{
    if(std::this_thread::get_id()!=coordinator)
      throw nexrt::DataError("E_TASK_STATE","reference external acceptance requires its creating coordinator");
  }
  std::shared_ptr<Pending> lookup(const TaskReferenceExternalTicket &ticket)const{
    if(ticket.scheduler!=identity||ticket.slot>=slots.size()||!slots[ticket.slot]||
       slots[ticket.slot]->ticket!=ticket)
      throw nexrt::DataError("E_TASK_STATE","invalid, stale or foreign reference external ticket");
    return slots[ticket.slot];
  }
  void cancelLocked(Pending &pending){
    if(!pending.done&&!pending.cancelled->exchange(true))++counts.cancelRequests;
  }
  void closeLocked(){sealed=true;for(auto &pending:slots)if(pending)cancelLocked(*pending);}
  bool hasReady()const{return std::any_of(slots.begin(),slots.end(),[](const auto &p){return p&&p->done;});}
  static void boundedFailure(nexrt::TaskExternalResult &result,const char *code,const char *message){
    nexrt::TaskExternalResult replacement{{},code,message};
    // Assignment need not shrink a container's retained allocation. Swap with
    // fresh bounded containers so rejected capacity is physically freed here.
    result.bytes.swap(replacement.bytes);result.errorCode.swap(replacement.errorCode);
    result.errorMessage.swap(replacement.errorMessage);
  }
  void worker()noexcept{
    for(;;){
      std::shared_ptr<Pending> pending;
      {
        std::unique_lock lock(mutex);changed.wait(lock,[&]{return stopping||!queue.empty();});
        if(queue.empty()){if(stopping)return;continue;}
        pending=std::move(queue.front());queue.pop_front();++counts.running;
        counts.maximumRunning=std::max(counts.maximumRunning,counts.running);
      }
      nexrt::TaskExternalResult result;
      // The worker closure contains only a cancellation flag and absolute
      // deadline. It cannot reach the AST, scheduler, source values or TLS.
      auto cancelled=pending->cancelled;auto until=deadline;
      nexrt::TaskExternalControl control([cancelled,until]{
        if(cancelled->load())throw nexrt::DataError("E_CANCELLED","reference external operation cancelled");
        if(Clock::now()>=until)throw nexrt::DataError("E_TIMEOUT","reference external operation deadline exceeded");
      });
      auto operation=std::move(pending->operation);
      try{
        control.checkpoint();result=operation->run(control);
      }catch(const nexrt::DataError &error){result={{},error.code,error.what()};}
      catch(const std::bad_alloc &){result={{},"E_MEMORY","reference external host allocation failed"};}
      catch(const std::exception &){result={{},"E_TASK_HOST","reference external host operation failed"};}
      catch(...){result={{},"E_TASK_HOST","reference external host operation failed"};}
      if(result.bytes.capacity()>limits.maximumResultBytes||result.bytes.capacity()>pending->reservation)
        boundedFailure(result,"E_LIMIT","reference external result capacity exceeds its byte reservation");
      // Diagnostic storage has a separate fixed per-ticket allowance. SSO
      // capacity is included; no source/host diagnostic can retain a large
      // allocation merely by shrinking its logical string length.
      if(result.errorCode.capacity()>nexrt::taskExternalErrorCodeCapacity||
         result.errorMessage.capacity()>nexrt::taskExternalErrorMessageCapacity)
        boundedFailure(result,"E_LIMIT","reference external diagnostic capacity exceeds its bound");
      // Retirement is a physical fence: even the operation/lease destructor
      // finishes before publication, admission or reservation release.
      operation.reset();
      {
        std::lock_guard lock(mutex);pending->result=std::move(result);pending->done=true;
        --counts.running;++counts.ready;++counts.retired;
      }
      changed.notify_all();
    }
  }
  void shutdown()noexcept{
    {std::lock_guard lock(mutex);closeLocked();stopping=true;}
    changed.notify_all();
    for(auto &worker:workers)if(worker.joinable())worker.join();
    workers.clear();stopWake.reset();
  }
};
TaskReferenceExternalMailbox::TaskReferenceExternalMailbox(Clock::time_point until,
    std::stop_token cancellation,nexrt::TaskExternalLimits limits)
    :impl(std::make_unique<Impl>(until,cancellation,limits)){}
TaskReferenceExternalMailbox::~TaskReferenceExternalMailbox()=default;
TaskReferenceExternalTicket TaskReferenceExternalMailbox::submit(size_t owner,
    std::shared_ptr<nexrt::TaskExternalOperation> operation,size_t reservation){
  impl->coordinatorOnly();std::lock_guard lock(impl->mutex);
  if(impl->sealed||impl->cancellation.stop_requested())throw nexrt::DataError("E_CANCELLED","reference external admission is closed");
  if(Clock::now()>=impl->deadline)throw nexrt::DataError("E_TIMEOUT","reference external admission deadline exceeded");
  if(!operation||owner==size_t(-1))throw nexrt::DataError("E_TASK_STATE","invalid reference external operation owner");
  if(impl->counts.pending==impl->limits.tickets||reservation>impl->limits.reservedBytes-impl->counts.reservedBytes)
    throw nexrt::DataError("E_LIMIT","reference external pending/byte capacity exceeded");
  auto free=std::find(impl->slots.begin(),impl->slots.end(),nullptr);auto slot=size_t(free-impl->slots.begin());
  if(impl->generations[slot]==UINT64_MAX)throw nexrt::DataError("E_LIMIT","reference external ticket generation exhausted");
  auto pending=std::make_shared<Impl::Pending>();
  pending->ticket={impl->identity,++impl->generations[slot],slot,owner};
  pending->reservation=reservation;
  // Register the authenticated slot and quota before a worker may start.
  // Queue allocation also precedes transferring the host operation, so an
  // allocation failure cannot invoke its lease destructor under this lock.
  impl->queue.push_back(pending);pending->operation=std::move(operation);impl->slots[slot]=pending;
  ++impl->counts.pending;impl->counts.reservedBytes+=reservation;++impl->counts.submitted;
  impl->changed.notify_all();return pending->ticket;
}
bool TaskReferenceExternalMailbox::cancel(const TaskReferenceExternalTicket &ticket){
  impl->coordinatorOnly();std::lock_guard lock(impl->mutex);auto pending=impl->lookup(ticket);
  bool result=!pending->done&&!pending->cancelled->load();impl->cancelLocked(*pending);impl->changed.notify_all();return result;
}
std::optional<TaskReferenceExternalTicket> TaskReferenceExternalMailbox::ready()const{
  impl->coordinatorOnly();std::lock_guard lock(impl->mutex);
  for(const auto &pending:impl->slots)if(pending&&pending->done)return pending->ticket;
  return {};
}
nexrt::TaskExternalResult TaskReferenceExternalMailbox::take(const TaskReferenceExternalTicket &ticket){
  impl->coordinatorOnly();std::lock_guard lock(impl->mutex);auto pending=impl->lookup(ticket);
  if(!pending->done)throw nexrt::DataError("E_TASK_STATE","reference external ticket has not physically retired");
  auto result=std::move(pending->result);impl->slots[ticket.slot].reset();
  --impl->counts.pending;--impl->counts.ready;impl->counts.reservedBytes-=pending->reservation;++impl->counts.consumed;return result;
}
void TaskReferenceExternalMailbox::close(){
  impl->coordinatorOnly();{std::lock_guard lock(impl->mutex);impl->closeLocked();}impl->changed.notify_all();
}
void TaskReferenceExternalMailbox::wait(){
  impl->coordinatorOnly();std::unique_lock lock(impl->mutex);
  auto available=[&]{return impl->hasReady()||!impl->counts.pending||
      (!impl->sealed&&(impl->cancellation.stop_requested()||Clock::now()>=impl->deadline));};
  if(impl->sealed)impl->changed.wait(lock,available);
  else impl->changed.wait_until(lock,impl->deadline,available);
}
void TaskReferenceExternalMailbox::waitForControl(std::chrono::milliseconds maximumPause){
  impl->coordinatorOnly();
  if(maximumPause.count()<=0)throw nexrt::DataError("E_OPTION","reference control wait must be positive");
  std::unique_lock lock(impl->mutex);
  auto available=[&]{return impl->hasReady()||!impl->counts.pending||
      (!impl->sealed&&(impl->cancellation.stop_requested()||Clock::now()>=impl->deadline));};
  if(impl->sealed)impl->changed.wait(lock,available);
  else impl->changed.wait_until(lock,std::min(impl->deadline,Clock::now()+maximumPause),available);
}
void TaskReferenceExternalMailbox::drain(){
  close();std::unique_lock lock(impl->mutex);
  impl->changed.wait(lock,[&]{return impl->counts.retired==impl->counts.submitted;});
  for(auto &pending:impl->slots)pending.reset();
  impl->counts.pending=impl->counts.reservedBytes=impl->counts.ready=0;
}
TaskReferenceExternalStats TaskReferenceExternalMailbox::stats()const{
  impl->coordinatorOnly();std::lock_guard lock(impl->mutex);return impl->counts;
}
struct TaskReferenceAccess {
  static RV create(RD::Kind kind,const std::shared_ptr<const void> &owner,size_t scope,size_t index){
    return RV(std::shared_ptr<RD>(new nexrt::ReferenceTaskData(kind,owner,scope,index)));
  }
  static const nexrt::ReferenceTaskData &get(const RV &value,RD::Kind kind,const std::shared_ptr<const void> &owner){
    if(value.tag!=RV::Object||!value.object||value.object->kind!=kind||
       value.object->taskOwnerFamily()!=RD::TaskOwnerFamily::Reference)
      throw Error("E_TASK_VALUE","expected a reference-owned task capability");
    const auto &cap=static_cast<const nexrt::ReferenceTaskData&>(*value.object);
    if(cap.owner.lock()!=owner)throw Error("E_TASK_SCOPE","reference task capability belongs to an ended or foreign scheduler");
    return cap;
  }
  static size_t scope(const nexrt::ReferenceTaskData &v){return v.scope;}
  static size_t index(const nexrt::ReferenceTaskData &v){return v.index;}
};
namespace {
void annotateReferenceError(const Program &program,Error &error){
  if(!isPublicTaskLanguage(program)||!error.operationSite.empty()||error.span.file.empty())return;
  for(const auto &function:program.functions)for(const auto &operation:operationTree(program,function))
    if(operation.ast&&operation.span.file==error.span.file&&operation.span.begin==error.span.begin&&
       operation.span.end==error.span.end){
      error.operationSite=operation.site;error.operationRevision=revision(program);
      error.operationSource=hash(json(sourceBundle(program),false));return;
    }
}
// This reference intentionally uses a single coordinator, scanning completion
// states and FIFO deques. It shares neither native wait lists nor dispatch code.
struct Reference {
  static constexpr size_t none=size_t(-1),maximumTasks=4096,maximumScopes=1024;
  enum State {Ready,Future,Send,Receive,Drain,External,Finishing,Done};
  struct Activation {
    std::unique_ptr<TaskAstMachine> machine;
    size_t region=none,parent=none,depth=0,outputRead=0;
    uint64_t returnTicket=0;
    RV result;
    bool completed=false;
    Span scopeSpan;
  };
  struct Job {
    std::vector<Activation> stack;
    State state=Ready;
    size_t member=none,current=none,parent=none,depth=1,target=none;
    bool queued=false,cancelled=false,observed=false;
    TaskTransition request;
    RV result,pending;
    std::shared_ptr<Error> failure;
    std::weak_ptr<RD> capability;
    std::vector<size_t> owned;
    std::optional<nexrt::ResourceRegion> resources;
    std::optional<nexrt::ResourceRegionRetirement> resourceRetirement;
    std::optional<TaskReferenceExternalTicket> external;
    std::optional<nexrt::PreparedTaskForeignCall> foreignCall;
    size_t externalScope=none;
#ifndef _WIN32
    std::unique_ptr<nexrt::PreparedTaskFileRead> fileRead;
#endif
  };
  struct Region {
    size_t parent=none,owner=none,depth=1;
    bool closing=false,closed=false,abort=false;
    size_t external=0;
    std::vector<size_t> members,children,pipes;
    std::shared_ptr<Error> failure;
    std::weak_ptr<RD> capability;
    std::unique_ptr<nexrt::ResourceRegion> resources;
    std::optional<nexrt::ResourceRegionRetirement> resourceRetirement;
  };
  struct Pipe {
    size_t scope,capacity;
    Type type;
    bool closed=false;
    std::deque<RV> buffer;
    std::deque<size_t> senders,receivers;
    std::weak_ptr<RD> capability;
  };
  const Program &program;
  std::shared_ptr<const void> identity=std::make_shared<const int>(0);
  std::vector<std::unique_ptr<Job>> jobs;
  std::vector<Region> regions;
  std::vector<Pipe> pipes;
  std::deque<size_t> ready;
  using Clock=std::chrono::steady_clock;
  nexrt::TaskExecutionLimits limits;
  uint64_t limit,used=0;
  Clock::time_point deadline;
  std::shared_ptr<Error> controlFailure;
  TaskControlPoll controlPoll;
  size_t channelSlots=0;
  std::string output;
  Span rootSpan;
  TaskReferenceObserver observer;
  TaskReferenceExternalHost *externalHost;
  std::unique_ptr<nexrt::ResourceRegion> resourceRoot;
  std::shared_ptr<nexrt::ResourceExecutor> foreignCleanup;
  std::unique_ptr<TaskReferenceExternalMailbox> external;
  nexrt::CapturedForeignScope foreignScope;
#ifndef _WIN32
  nexrt::FileReadGrant fileGrant;
#endif

  static nexrt::TaskExecutionLimits selectedLimits(uint64_t legacy,const nexrt::TaskExecutionLimits *requested){
    if(requested){
      if(!nexrt::validTaskExecutionLimits(*requested))throw Error("E_OPTION","invalid task execution limits");
      return *requested;
    }
    // Existing numeric probes retain their step semantics, including zero.
    // Public explicit configurations use the canonical positive/range checks.
    nexrt::TaskExecutionLimits result;result.steps=legacy;return result;
  }
  Reference(const Program &p,uint64_t legacy,TaskReferenceObserver observer,const nexrt::TaskExecutionLimits *requested,
      TaskReferenceExternalHost *host,const nexrt::FileReadGrant *grant)
    :program(p),limits(selectedLimits(legacy,requested)),limit(limits.steps),
     deadline(Clock::now()+std::chrono::milliseconds(limits.timeoutMs)),observer(std::move(observer)),externalHost(host){
    if(supportsTaskFileReads(program))if(auto inherited=nexrt::currentRequestDeadline())deadline=std::min(deadline,*inherited);
    controlPoll=[this](Span span){checkControl(span);};
    if(supportsTaskForeignCalls(program))foreignScope=nexrt::captureForeignScope(true);
#ifndef _WIN32
    if(grant)fileGrant=*grant;
#else
    (void)grant;
#endif
    if(host)external=std::make_unique<TaskReferenceExternalMailbox>(deadline,host->cancellation,host->limits);
    if((host&&host->resourceRegions)||supportsTaskForeignCalls(program)){
      nexrt::ResourceRegionLimits bounds;bounds.tasks=maximumTasks;
      const auto parent=host?host->resourceRequestParent:nexrt::ResourceRegionAuthority{};
      resourceRoot=parent?std::make_unique<nexrt::ResourceRegion>(nexrt::ResourceRegion::inRequest(nexrt::ResourceRegionFamily::Reference,parent,bounds)):
        std::make_unique<nexrt::ResourceRegion>(nexrt::ResourceRegionFamily::Reference,bounds);
    }
    if(supportsTaskForeignCalls(program))foreignCleanup=std::make_shared<nexrt::ResourceExecutor>(nexrt::ResourceExecutorLimits{4096,64,8*1048576});
  }
  // Also cover unexpected observer/host failures. Physical operations stop
  // retaining frames/leases before root revocation waits for finalizers.
  ~Reference(){
    if(resourceRoot){
      if(external)external->drain();
      jobs.clear();pipes.clear();retireRootResources();
    }
  }
  const nexrt::ResourceRegion &resourceContext(const Job &job)const{
    if(!resourceRoot)throw Error("E_RESOURCE_SCOPE","reference resource regions are not enabled");
    return job.current==job.member?*job.resources:*regions.at(job.current).resources;
  }
  nexrt::ResourceRegionAuthority resourceAuthority(const Job &job)const{
    return resourceContext(job).authority();
  }
  bool resourceRetirementsPending()const{
    return std::any_of(jobs.begin(),jobs.end(),[](const auto &job){
      return job->resourceRetirement&&!job->resourceRetirement->ready();
    })||std::any_of(regions.begin(),regions.end(),[](const Region &r){
      return r.resourceRetirement&&!r.resourceRetirement->ready();
    });
  }
  void retireRootResources()noexcept{
    if(!resourceRoot)return;
    auto retirement=resourceRoot->beginClose();retirement.requestClose();
    while(!retirement.ready())std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
  void checkControl(Span span={}){
    if(controlFailure)throw *controlFailure;
    if(supportsTaskFileReads(program))try{nexrt::pollHostOperation(span.line);}
    catch(const nexrt::Trap &error){
      if(span.file.empty())span=rootSpan;
      controlFailure=std::make_shared<Error>(error.code,error.what(),span);throw *controlFailure;
    }
    if(externalHost&&externalHost->cancellation.stop_requested()){
      if(span.file.empty())span=rootSpan;
      controlFailure=std::make_shared<Error>("E_CANCELLED","reference host cancelled task execution",span);
      throw *controlFailure;
    }
    if(Clock::now()>=deadline){
      if(span.file.empty())span=rootSpan;
      controlFailure=std::make_shared<Error>("E_TIMEOUT","reference task deadline exceeded",span);
      throw *controlFailure;
    }
  }
  void account(uint64_t amount,Span span={}){
    if(amount>limit-used){
      if(!controlFailure)controlFailure=std::make_shared<Error>("E_LIMIT","reference scheduler step budget exceeded",span);
      throw *controlFailure;
    }
    used+=amount;
  }
  void charge(uint64_t amount,Span span={}){checkControl(span);account(amount,span);}
  bool within(size_t ancestor,size_t scope)const{
    for(;scope!=none;scope=regions.at(scope).parent)if(scope==ancestor)return true;
    return false;
  }
  void access(size_t scope,size_t current)const{
    if(scope>=regions.size()||regions[scope].closed||!within(scope,current))
      throw Error("E_TASK_SCOPE","reference capability scope is foreign or has ended");
  }
  size_t capability(const RV &v,RD::Kind kind,size_t current)const{
    const auto &cap=TaskReferenceAccess::get(v,kind,identity);
    auto s=TaskReferenceAccess::scope(cap),i=TaskReferenceAccess::index(cap);access(s,current);
    std::shared_ptr<RD> canonical;
    if(kind==RD::TaskScope&&i==s)canonical=regions[s].capability.lock();
    else if(kind==RD::Task&&i<jobs.size()&&jobs[i]->member==s)canonical=jobs[i]->capability.lock();
    else if(kind==RD::Channel&&i<pipes.size()&&pipes[i].scope==s)canonical=pipes[i].capability.lock();
    if(canonical!=v.object)throw Error("E_TASK_SCOPE","reference capability identity is invalid");
    return i;
  }
  RV value(RD::Kind kind,size_t i){
    size_t scope=kind==RD::TaskScope?i:kind==RD::Task?jobs.at(i)->member:pipes.at(i).scope;
    auto &weak=kind==RD::TaskScope?regions.at(i).capability:kind==RD::Task?jobs.at(i)->capability:pipes.at(i).capability;
    if(auto cached=weak.lock())return RV(std::move(cached));
    auto result=TaskReferenceAccess::create(kind,identity,scope,i);weak=result.object;return result;
  }
  void snapshot(const RV &root,size_t target,size_t current,nexrt::ResourceRegionAuthority actor={},nexrt::ResourceRegionAuthority receiver={},bool transfer=true){
    std::vector<RV> work{root};std::unordered_set<const RD*> seen;size_t members=1;
    std::vector<nexrt::ExternalResource> owners;std::unordered_set<uint64_t> ownerIds;
    while(!work.empty()){
      auto v=std::move(work.back());work.pop_back();charge(1);
      if(v.tag==RV::Integer)continue;
      if(v.tag==RV::Floating){(void)v.floating();continue;}
      if(v.tag==RV::Boolean){if(v.scalar<0||v.scalar>1)throw Error("E_TASK_VALUE","invalid reference snapshot boolean");continue;}
      if(v.tag!=RV::Object||!v.object)throw Error("E_TASK_VALUE","invalid reference snapshot value");
      if(!seen.insert(v.object.get()).second)continue;
      if(seen.size()>262144||v.object->values.size()>262144-members)throw Error("E_LIMIT","reference snapshot graph exceeds262144 members");
      auto kind=v.object->kind;
      if(kind==RD::External){
        if(!supportsTaskForeignCalls(program))throw Error("E_TASK_VALUE","reference task cannot transport external resource authority");
        const auto &owner=nexrt::externalResource(v.object);
        if(ownerIds.insert(owner.identity()).second){
          if(owners.size()==4096)throw Error("E_RESOURCE_REGION_LIMIT","reference snapshot exceeds4096 distinct resource owners");
          owners.push_back(owner);
        }
      }
      if(kind==RD::File)throw Error("E_TASK_VALUE","reference task cannot transport file authority");
      if(kind==RD::TaskScope||kind==RD::Task||kind==RD::Channel){
        capability(v,kind,current);
        auto scope=TaskReferenceAccess::scope(TaskReferenceAccess::get(v,kind,identity));
        if(target==none||!within(scope,target))throw Error("E_TASK_SCOPE","reference task capability escapes its logical owner scope");
      }
      members+=v.object->values.size();work.insert(work.end(),v.object->values.begin(),v.object->values.end());
    }
    if(!owners.empty()){
      if(!resourceRoot)throw Error("E_RESOURCE_SCOPE","reference resource transfer requires enabled ownership regions");
      if(!actor)actor=resourceRoot->authority();
      if(!receiver)receiver=target==none?resourceRoot->authority():regions.at(target).resources->authority();
      nexrt::ExternalResource::transferRegions(owners,actor,receiver,transfer);
    }
  }
  void enqueue(size_t i){auto &j=*jobs[i];if(j.state==Ready&&!j.queued){ready.push_back(i);j.queued=true;}}
  void answer(size_t i,RV result={}){
    auto &j=*jobs[i];j.stack.back().machine->resume(j.request.ticket,std::move(result));
    j.request={};j.pending={};j.target=none;j.state=Ready;enqueue(i);
  }
  static bool fatal(const std::shared_ptr<Error> &e){return e&&(e->code=="E_LIMIT"||e->code=="E_MEMORY"||e->code=="E_TIMEOUT");}
  static bool resource(const std::shared_ptr<Error> &e){return fatal(e)||(e&&e->code=="E_CANCELLED");}
  static void prefer(std::shared_ptr<Error> &selected,const std::shared_ptr<Error> &candidate){
    // Cleanup cancellation cannot hide physical resource exhaustion. Once a
    // fatal resource error is selected, retain that first fatal through drain.
    if(candidate&&(!selected||(fatal(candidate)&&!fatal(selected))||(!resource(selected)&&resource(candidate))))selected=candidate;
  }
  void beginFinish(size_t i,std::shared_ptr<Error> failure={},RV result={}){
    auto &j=*jobs[i];if(j.state==Done)return;
    if(j.state==Finishing)prefer(j.failure,failure);
    else{j.state=Finishing;j.failure=std::move(failure);j.result=std::move(result);}
    // No completion is published until every retained frame and owned scope
    // has been released. Single-thread cleanup needs no native coroutine lock.
    if(j.external)external->cancel(*j.external);
    else{j.stack.clear();j.request={};j.pending={};}
    for(auto s:j.owned)if(!regions[s].closed){regions[s].closing=true;regions[s].abort=bool(j.failure);if(j.failure)cancelRegion(s);}
  }
  void cancelRegion(size_t scope){
    for(auto &j:jobs)if(j->state!=Done&&within(scope,j->member))j->cancelled=true;
  }
  bool cancelJob(size_t i){
    auto &selected=*jobs[i];if(selected.state==Done||selected.state==Finishing)return false;
    for(size_t n=0;n<jobs.size();++n){
      for(size_t parent=n;parent!=none;parent=jobs[parent]->parent)if(parent==i){jobs[n]->cancelled=true;break;}
    }
    return true;
  }
  // A dependency node is a job or (maximumTasks + region). Channel readiness
  // is external to this graph; a fully stalled channel program is diagnosed
  // separately rather than pretending it is a future/scope cycle.
  bool cycle(size_t waiter,size_t target,bool scope){
    std::vector<size_t> work{scope?maximumTasks+target:target};std::unordered_set<size_t> seen;
    while(!work.empty()){
      checkControl();
      auto node=work.back();work.pop_back();if(node==waiter)return true;if(!seen.insert(node).second)continue;
      if(node>=maximumTasks){const auto &r=regions.at(node-maximumTasks);if(r.closed)continue;
        for(auto member:r.members)if(jobs[member]->state!=Done)work.push_back(member);
        for(auto child:r.children)if(!regions[child].closed)work.push_back(maximumTasks+child);
      }else{const auto &j=*jobs.at(node);if(j.state==Future)work.push_back(j.target);else if(j.state==Drain)work.push_back(maximumTasks+j.target);}
    }
    return false;
  }
  size_t first(std::deque<size_t> &queue,State expected,size_t pipe){
    while(!queue.empty()){
      auto i=queue.front();queue.pop_front();auto &j=*jobs[i];
      if(j.state==expected&&j.target==pipe&&!j.cancelled)return i;
    }
    return none;
  }
  bool closePipe(size_t p){
    auto &pipe=pipes[p];if(pipe.closed)return false;pipe.closed=true;
    for(auto i=first(pipe.senders,Send,p);i!=none;i=first(pipe.senders,Send,p))answer(i,RV(0,true));
    for(auto i=first(pipe.receivers,Receive,p);i!=none;i=first(pipe.receivers,Receive,p)){
      if(pipe.buffer.empty())answer(i,nexrt::failure("E_CHANNEL_CLOSED","channel is closed"));
      else{auto item=std::move(pipe.buffer.front());pipe.buffer.pop_front();answer(i,nexrt::success(std::move(item)));}
    }
    return true;
  }
  bool settle(){
    bool any=false,changed=true;
    while(changed){changed=false;
      for(size_t i=0;i<jobs.size();++i){auto &j=*jobs[i];if(j.cancelled&&j.state!=Done&&j.state!=Finishing){beginFinish(i,std::make_shared<Error>("E_CANCELLED","reference task was cancelled"));changed=true;}}
      for(size_t s=regions.size();s-->0;){auto &r=regions[s];if(!r.closing||r.closed||r.external)continue;
        if(std::any_of(r.members.begin(),r.members.end(),[&](size_t i){return jobs[i]->state!=Done;})||
           std::any_of(r.children.begin(),r.children.end(),[&](size_t i){return !regions[i].closed;}))continue;
        if(r.resources){
          if(!r.resourceRetirement){
            r.resourceRetirement.emplace(r.resources->beginClose());
            // The serial AST coordinator holds no scheduler/mailbox lock.
            r.resourceRetirement->requestClose();
          }
          if(!r.resourceRetirement->ready())continue;
        }
        for(auto i:r.members){auto &j=*jobs[i];
          if(fatal(j.failure)||(!r.abort&&!j.observed&&!j.cancelled))prefer(r.failure,j.failure);
          j.observed=true;j.result={};j.capability.reset();
        }
        for(auto p:r.pipes){closePipe(p);channelSlots-=pipes[p].capacity;pipes[p].capacity=0;pipes[p].buffer.clear();pipes[p].capability.reset();}
        r.closed=true;r.capability.reset();if(jobs[r.owner]->state==Finishing)prefer(jobs[r.owner]->failure,r.failure);
        if(externalHost)externalHost->scopeRetired(s);changed=true;
      }
      for(size_t i=0;i<jobs.size();++i){auto &j=*jobs[i];
        if(j.state==Finishing&&!j.external&&std::all_of(j.owned.begin(),j.owned.end(),[&](size_t s){return regions[s].closed;})){
          j.stack.clear();j.request={};j.pending={};if(j.failure)j.result={};
          if(j.resources){
            if(!j.resourceRetirement){j.resourceRetirement.emplace(j.resources->beginClose());j.resourceRetirement->requestClose();}
            if(!j.resourceRetirement->ready())continue;
          }
          if(externalHost)externalHost->taskRetired(i);
          j.state=Done;changed=true;
        }else if(j.state==Future&&jobs[j.target]->state==Done){
          auto &target=*jobs[j.target];target.observed=true;
          if(target.failure)beginFinish(i,target.failure);else answer(i,target.result);changed=true;
        }else if(j.state==Drain&&regions[j.target].closed){
          auto &region=regions[j.target];
          if(region.failure)beginFinish(i,region.failure);
          else{auto value=std::move(j.stack.back().result);j.current=j.stack.back().parent;
            auto ticket=j.stack.back().returnTicket;j.stack.pop_back();j.request.ticket=ticket;answer(i,std::move(value));}
          changed=true;
        }
      }
      any|=changed;
    }
    return any;
  }
  const Function &callback(const RV &closure,size_t parameters){
    if(closure.tag!=RV::Object||!closure.object||closure.object->kind!=RD::Closure)throw Error("E_FUNCTION","reference callback requires a checked closure");
    const auto &function=program.function(closure.object->text);
    if(function.params.size()!=parameters)throw Error("E_TASK_STATE","reference callback argument count differs");
    return function;
  }
  void withTasks(size_t i,const TaskTransition &r){
    auto workers=r.arguments.at(0);
    if(workers.tag!=RV::Integer||workers.scalar<1||workers.scalar>16)throw Error("E_RANGE","with_tasks requires1..16 workers",r.span);
    if(regions.size()>=maximumScopes)throw Error("E_LIMIT","reference scope count exceeds1024",r.span);
    auto &j=*jobs[i];auto parent=j.current;size_t depth=parent==none?1:regions[parent].depth+1;
    if(depth>256)throw Error("E_LIMIT","reference scope depth exceeds256",r.span);
    const auto &fn=callback(r.arguments.at(1),1);
    size_t outer=j.stack.back().depth+r.callDepth,pending=0;
    for(const auto &a:j.stack)pending+=a.machine->pendingActions();
    if(outer>=256||pending>=262144)throw Error("E_LIMIT","reference callback frame/action limit exceeded",r.span);
    size_t s=regions.size();Region region;region.owner=i;region.parent=parent;region.depth=depth;
    if(resourceRoot)region.resources=std::make_unique<nexrt::ResourceRegion>(resourceContext(j).child());
    regions.push_back(std::move(region));
    if(parent!=none)regions[parent].children.push_back(s);j.owned.push_back(s);
    snapshot(r.arguments.at(1),s,parent,resourceRoot?resourceAuthority(j):nexrt::ResourceRegionAuthority{},resourceRoot?regions[s].resources->authority():nexrt::ResourceRegionAuthority{});
    j.current=s;
    Activation a;a.region=s;a.parent=parent;a.depth=outer;a.returnTicket=r.ticket;a.scopeSpan=r.span;
    a.machine=std::make_unique<TaskAstMachine>(program,fn.name,std::vector<RV>{value(RD::TaskScope,s)},limit-used,r.arguments[1],unsigned(outer),262144-pending,controlPoll);
    j.stack.push_back(std::move(a));j.request={};enqueue(i);
  }
  void spawn(size_t i,const TaskTransition &r){
    auto &parent=*jobs[i];auto s=capability(r.arguments.at(0),RD::TaskScope,parent.current);
    auto closure=r.arguments.at(1);const auto &fn=callback(closure,0);snapshot(closure,s,parent.current,resourceRoot?resourceAuthority(parent):nexrt::ResourceRegionAuthority{});
    if(jobs.size()>=maximumTasks||parent.depth>=256)throw Error("E_LIMIT","reference task slot/nesting limit exceeded",r.span);
    auto job=std::make_unique<Job>();job->member=job->current=s;job->parent=i;job->depth=parent.depth+1;
    Activation a;a.scopeSpan=fn.span;a.machine=std::make_unique<TaskAstMachine>(program,fn.name,std::vector<RV>{},limit-used,closure,0,262144,controlPoll);job->stack.push_back(std::move(a));
    if(resourceRoot)job->resources.emplace(regions[s].resources->taskChild());
    auto id=jobs.size();jobs.push_back(std::move(job));regions[s].members.push_back(id);enqueue(id);answer(i,value(RD::Task,id));
  }
  bool sourceHostRequest(const std::string &operation)const{
    if(supportsTaskFileReads(program)&&taskFileReadOperation(operation))return true;
    return supportsTaskForeignCalls(program)&&!operation.empty()&&!taskBuiltins().contains(operation)&&!taskFileBuiltin(operation)&&program.function(operation).foreign.has_value();
  }
  void dispatch(size_t i){
    auto &j=*jobs[i];const auto &r=j.request;charge(1,r.span);
    if(supportsTaskForeignCalls(program)&&!taskBuiltins().contains(r.operation)&&!taskFileReadOperation(r.operation)&&program.function(r.operation).foreign){
      auto prepared=nexrt::PreparedTaskForeignCall(foreignScope,json(foreignBinding(program,program.function(r.operation)),false),r.arguments,[&]{checkControl(r.span);},resourceAuthority(j),foreignCleanup);
      if(!external)external=std::make_unique<TaskReferenceExternalMailbox>(deadline,
          externalHost?externalHost->cancellation:std::stop_token{},externalHost?externalHost->limits:nexrt::TaskExternalLimits{});
      auto ticket=external->submit(i,prepared.operation(),nexrt::PreparedTaskForeignCall::reservation);
      j.foreignCall=std::move(prepared);j.external=ticket;j.externalScope=j.current;
      if(j.externalScope!=none)++regions.at(j.externalScope).external;
      return;
    }
    if(taskFileReadOperation(r.operation)){
      if(!supportsTaskFileReads(program))throw Error("E_TASK_UNIMPLEMENTED","source task file reads require language020",r.span);
      const auto expected=Type::result(r.operation=="file_read_text"?Type(Type::Str):Type(Type::Bytes));
      if(r.arguments.size()!=1||r.arguments[0].tag!=RV::Object||!r.arguments[0].object||
         r.arguments[0].object->kind!=RD::String||r.result!=expected)
        throw Error("E_TASK_TYPE","reference file read has an invalid checked request shape",r.span);
#ifdef _WIN32
      throw Error("E_TASK_TARGET","task file reads require the macOS/Linux native host",r.span);
#else
      try{
        auto prepared=std::make_unique<nexrt::PreparedTaskFileRead>(fileGrant,r.arguments[0].object->text,r.operation=="file_read_text");
        auto operation=prepared->operation();checkControl(r.span);
        if(!external)external=std::make_unique<TaskReferenceExternalMailbox>(deadline,
          externalHost?externalHost->cancellation:std::stop_token{},
          externalHost?externalHost->limits:nexrt::TaskExternalLimits{});
        auto ticket=external->submit(i,std::move(operation),nexrt::PreparedTaskFileRead::reservation);
        j.fileRead=std::move(prepared);j.external=ticket;j.externalScope=j.current;
        if(j.externalScope!=none)++regions.at(j.externalScope).external;
        j.state=External;return;
      }catch(const nexrt::DataError &error){
        if(!nexrt::ordinaryTaskFileReadError(error.code))
          throw Error(error.code,error.what(),r.span);
        checkControl(r.span);answer(i,nexrt::failure(error.code,error.what()));return;
      }catch(const std::bad_alloc &){throw Error("E_MEMORY","reference file read preparation allocation failed",r.span);}
#endif
    }
    if(r.operation=="task_yield"){
      if(externalHost){
        std::optional<TaskReferenceExternalRequest> request;
        try{request=resourceRoot?externalHost->prepareInRegion(i,r.span,resourceAuthority(j)):
              externalHost->prepare(i,r.span);}
        catch(const Error &){throw;}
        catch(const nexrt::DataError &){throw;}
        catch(const std::bad_alloc &){throw Error("E_MEMORY","reference external host preparation allocation failed",r.span);}
        catch(...){throw Error("E_TASK_HOST","reference external host preparation failed",r.span);}
        checkControl(r.span);
        if(request){
          j.external=external->submit(i,std::move(request->operation),request->reservedBytes);
          j.externalScope=j.current;if(j.externalScope!=none)++regions.at(j.externalScope).external;
          j.state=External;return;
        }
      }
      answer(i);return;
    }
    if(r.operation=="with_tasks"){withTasks(i,r);return;}
    if(r.operation=="task_spawn"){spawn(i,r);return;}
    if(r.operation=="current_task_scope"){
      access(j.current,j.current);answer(i,value(RD::TaskScope,j.current));return;
    }
    if(r.operation=="task_wait"||r.operation=="task_cancel"){
      auto target=capability(r.arguments.at(0),RD::Task,j.current);
      if(r.operation=="task_cancel"){auto cancelled=cancelJob(target);answer(i,RV(cancelled,true));return;}
      if(cycle(i,target,false))throw Error("E_TASK_CYCLE","cyclic reference task wait",r.span);
      j.target=target;j.state=Future;return;
    }
    if(r.operation=="channel_new"){
      auto scope=capability(r.arguments.at(0),RD::TaskScope,j.current);auto capacity=r.arguments.at(1);
      if(capacity.tag!=RV::Integer||capacity.scalar<0||capacity.scalar>65536)throw Error("E_RANGE","channel capacity must be0..65536",r.span);
      if(pipes.size()>=1024||size_t(capacity.scalar)>65536-channelSlots)throw Error("E_LIMIT","reference channel/slot limit exceeded",r.span);
      auto id=pipes.size();pipes.push_back(Pipe{scope,size_t(capacity.scalar),*r.result.element,false,{},{},{},{}});
      channelSlots+=size_t(capacity.scalar);regions[scope].pipes.push_back(id);answer(i,value(RD::Channel,id));return;
    }
    auto p=capability(r.arguments.at(0),RD::Channel,j.current);auto &pipe=pipes[p];
    if(r.operation=="task_close"){auto closed=closePipe(p);answer(i,RV(closed,true));return;}
    if(r.operation=="task_send"){
      auto item=r.arguments.at(1);snapshot(item,pipe.scope,j.current,resourceRoot?resourceAuthority(j):nexrt::ResourceRegionAuthority{},{},!pipe.closed);
      if(pipe.closed){answer(i,RV(0,true));return;}
      auto receiver=first(pipe.receivers,Receive,p);
      if(receiver!=none){answer(receiver,nexrt::success(std::move(item)));answer(i,RV(1,true));return;}
      if(pipe.buffer.size()<pipe.capacity){pipe.buffer.push_back(std::move(item));answer(i,RV(1,true));return;}
      j.target=p;j.pending=std::move(item);j.state=Send;pipe.senders.push_back(i);return;
    }
    if(r.operation=="task_recv"){
      if(!pipe.buffer.empty()){
        auto item=std::move(pipe.buffer.front());pipe.buffer.pop_front();auto sender=first(pipe.senders,Send,p);
        if(sender!=none){pipe.buffer.push_back(std::move(jobs[sender]->pending));answer(sender,RV(1,true));}
        answer(i,nexrt::success(std::move(item)));return;
      }
      auto sender=first(pipe.senders,Send,p);
      if(sender!=none){auto item=std::move(jobs[sender]->pending);answer(sender,RV(1,true));answer(i,nexrt::success(std::move(item)));return;}
      if(pipe.closed){answer(i,nexrt::failure("E_CHANNEL_CLOSED","channel is closed"));return;}
      j.target=p;j.state=Receive;pipe.receivers.push_back(i);return;
    }
    throw Error("E_TASK_STATE","unknown reference task request",r.span);
  }
  void absorb(Activation &a){const auto &text=a.machine->output();output+=text.substr(a.outputRead);a.outputRead=text.size();}
  void turn(size_t i){
    auto &j=*jobs[i];
    Span operationSpan;
    try{
      auto &a=j.stack.back();a.machine->restrictBudget(limit-used);auto before=a.machine->steps();TaskTransition r;
      // Account and preserve produced output even if a deadline poll threw.
      // Cleanup/observation must not renew or repoll an already failed budget.
      try{r=a.machine->advance();}catch(...){absorb(a);account(a.machine->steps()-before);throw;}
      absorb(a);account(a.machine->steps()-before);
      operationSpan=r.kind==TaskTransition::Done?a.scopeSpan:r.span;
      checkControl(operationSpan);
      if(observer)observer(i,r);
      checkControl(operationSpan);
      if(r.kind==TaskTransition::Done){
        auto target=a.region==none?j.member:a.parent;
        auto destination=(resourceRoot&&a.region!=none&&target==j.member)?j.resources->authority():nexrt::ResourceRegionAuthority{};
        snapshot(r.value,target,j.current,resourceRoot?resourceAuthority(j):nexrt::ResourceRegionAuthority{},destination);
        if(a.region==none){beginFinish(i,{},std::move(r.value));return;}
        auto s=a.region;auto &region=regions[s];bool failed=r.value.tag==RV::Object&&r.value.object&&r.value.object->kind==RD::Failure;
        if(!failed&&cycle(i,s,true))throw Error("E_TASK_CYCLE","cyclic reference scope drain");
        a.result=std::move(r.value);a.completed=true;region.closing=true;region.abort=failed;
        if(failed)cancelRegion(s);j.target=s;j.state=Drain;return;
      }
      j.request=std::move(r);dispatch(i);
    }catch(const Error &e){
      auto located=std::make_shared<Error>(e);
      if(sourceHostRequest(j.request.operation)){
        if(fatal(located))prefer(controlFailure,located);
        if(fatal(controlFailure))located=controlFailure;
      }
      // An ordinary failure cannot hide shared resource exhaustion discovered
      // at the same source/host boundary. Already chosen resource errors keep
      // their established precedence during cancellation cleanup.
      try{checkControl(operationSpan);}catch(const Error &control){prefer(located,std::make_shared<Error>(control));}
      if(located->span.file.empty())located->span=operationSpan;beginFinish(i,std::move(located));
    }
    catch(const nexrt::DataError &e){
      auto failure=std::make_shared<Error>(e.code,e.what(),j.request.span);
      if(sourceHostRequest(j.request.operation)&&fatal(failure)){
        prefer(controlFailure,failure);failure=controlFailure;
      }
      beginFinish(i,std::move(failure));
    }
    catch(const std::bad_alloc &){
      auto failure=std::make_shared<Error>("E_MEMORY","reference source preparation allocation failed",operationSpan);
      if(sourceHostRequest(j.request.operation)){
        prefer(controlFailure,failure);failure=controlFailure;
      }
      beginFinish(i,std::move(failure));
    }
  }
  bool collectExternal(bool discard=false){
    if(!external)return false;
    bool any=false;
    while(auto ticket=external->ready()){
      any=true;
      if(ticket->owner>=jobs.size()||!jobs[ticket->owner]->external||*jobs[ticket->owner]->external!=*ticket)
        throw Error("E_TASK_STATE","reference external completion has no matching source owner");
      auto i=ticket->owner;auto &job=*jobs[i];auto span=job.request.span;
      const bool fileCompletion=taskFileReadOperation(job.request.operation);
      auto raw=external->take(*ticket);job.external.reset();
      auto foreignPrepared=std::move(job.foreignCall);job.foreignCall.reset();
      const bool sourceHostCompletion=fileCompletion||foreignPrepared.has_value();
#ifndef _WIN32
      auto prepared=std::move(job.fileRead);
#endif
      if(job.externalScope!=none){
        auto &scope=regions.at(job.externalScope);
        if(!scope.external||scope.closed)throw Error("E_TASK_STATE","reference external scope retirement ledger is invalid");
        --scope.external;job.externalScope=none;
      }
      std::shared_ptr<Error> physicalFailure;
      if(raw.errorCode=="E_MEMORY"||raw.errorCode=="E_LIMIT"||raw.errorCode=="E_TIMEOUT")
        physicalFailure=std::make_shared<Error>(raw.errorCode,raw.errorMessage,span);
      if(sourceHostCompletion&&physicalFailure)prefer(controlFailure,physicalFailure);
      if(discard||job.cancelled||job.state==Finishing){
        if(job.state!=Finishing)beginFinish(i,controlFailure?controlFailure:
            std::make_shared<Error>("E_CANCELLED","reference task was cancelled",span));
        prefer(job.failure,physicalFailure);
        job.stack.clear();job.request={};job.pending={};continue;
      }
      try{
        checkControl(span);
        if(foreignPrepared){
          auto value=foreignPrepared->admit(std::move(raw),[&]{checkControl(span);});
          checkControl(span);answer(i,std::move(value));continue;
        }
#ifndef _WIN32
        if(prepared){
          // Fixed adapter and concrete result type only. No source Value or
          // AST/frame reaches the IO worker, and cancelled completions never
          // enter this lease/UTF-8/source-admission boundary.
          if(physicalFailure)throw *physicalFailure;
          auto value=prepared->admit(std::move(raw));checkControl(span);
          const auto &item=*job.request.result.element;
          if(value.tag!=RV::Object||!value.object||
             (value.object->kind!=RD::Success&&value.object->kind!=RD::Failure)||
             (value.object->kind==RD::Success&&
              (value.object->values.size()!=1||value.object->values[0].tag!=RV::Object||
               !value.object->values[0].object||value.object->values[0].object->kind!=(item==Type::Str?RD::String:RD::Bytes))))
            throw Error("E_TASK_TYPE","reference file admission has an invalid concrete result",span);
          answer(i,std::move(value));continue;
        }
#endif
        if(!raw.errorCode.empty())throw Error(raw.errorCode,raw.errorMessage,span);
        // The synthetic bridge has only a unit response. Real filesystem
        // values require a separately reviewed, lease-checked source adapter.
        if(!raw.bytes.empty())throw Error("E_TASK_VALUE","reference yield completion requires an empty unit payload",span);
        try{
          if(resourceRoot)externalHost->admitInRegion(i,raw,resourceAuthority(job));
          else externalHost->admit(i,raw);
        }
        catch(const Error &){throw;}
        catch(const nexrt::DataError &){throw;}
        catch(const std::bad_alloc &){throw Error("E_MEMORY","reference external host admission allocation failed",span);}
        catch(...){throw Error("E_TASK_HOST","reference external host admission failed",span);}
        checkControl(span);answer(i);
      }catch(const Error &error){
        auto selected=std::make_shared<Error>(error);prefer(selected,physicalFailure);
        if(sourceHostCompletion&&fatal(selected)){prefer(controlFailure,selected);selected=controlFailure;}
        beginFinish(i,std::move(selected));
      }
      catch(const nexrt::DataError &error){
        auto selected=std::make_shared<Error>(error.code,error.what(),span);
        if(sourceHostCompletion&&fatal(selected)){prefer(controlFailure,selected);selected=controlFailure;}
        beginFinish(i,std::move(selected));
      }
      catch(const std::bad_alloc &){
        auto selected=std::make_shared<Error>("E_MEMORY","reference source host admission allocation failed",span);
        if(sourceHostCompletion){prefer(controlFailure,selected);selected=controlFailure;}
        beginFinish(i,std::move(selected));
      }
    }
    return any;
  }
  void finishControl(){
    // No source continuation is resumed after a shared control failure. Seal
    // admissions first, then retain each external owner's frames/scope ledger
    // until its physical operation and explicit host lease have retired.
    if(external)external->close();
    for(size_t i=0;i<jobs.size();++i)beginFinish(i,controlFailure);
    for(auto &region:regions)if(!region.closed){region.closing=true;region.abort=true;}
    for(;;){
      collectExternal(true);settle();
      if(jobs[0]->state==Done)break;
      if(external&&external->stats().pending){
        if(resourceRoot)external->waitForControl(std::chrono::milliseconds(1));
        else external->wait();
      }else if(resourceRetirementsPending())std::this_thread::sleep_for(std::chrono::milliseconds(1));
      else throw Error("E_TASK_STATE","reference control cleanup cannot make progress");
    }
    if(jobs[0]->state!=Done)throw Error("E_TASK_STATE","reference control cleanup did not drain all scopes");
    prefer(jobs[0]->failure,controlFailure);jobs[0]->result={};
  }
  void validateEntry(const std::string &entry){
    std::vector<std::string> pending{entry};std::set<std::string> seen;
    while(!pending.empty()){
      auto name=std::move(pending.back());pending.pop_back();if(!seen.insert(name).second)continue;
      const auto &function=program.function(name);
      const bool reads=supportsTaskFileReads(program)&&function.realm=="server"&&
        function.effects.contains("task")&&function.effects.contains("fs");
      const bool foreign=supportsTaskForeignCalls(program)&&function.realm=="server"&&function.effects.contains("ffi")&&
        (function.effects.contains("task")||function.foreign);
      if(supportsTaskFileReads(program)&&function.effects.contains("fs")&&!function.effects.contains("task"))
        throw Error("E_EFFECT","reference task calls require an explicitly resumable task/fs helper",function.span);
      for(const auto &effect:function.effects)if(effect!="task"&&effect!="io"&&!(reads&&effect=="fs")&&!(foreign&&effect=="ffi"))
        throw Error("E_TASK_UNIMPLEMENTED","reference task execution has no bridge for effect "+effect,function.span);
      std::function<void(E)> expression=[&](E e){if(!e)return;
        if(e->kind==Expr::Call&&taskFileBuiltin(e->text)){
          if(!reads||!taskFileReadOperation(e->text))throw Error("E_TASK_UNIMPLEMENTED","reference tasks support only020 whole-file text/bytes reads",e->span);
#ifdef _WIN32
          throw Error("E_TASK_TARGET","task file reads require the macOS/Linux native host",e->span);
#endif
        }
        for(auto argument:e->args)expression(argument);
      };
      std::function<void(const std::vector<S>&)> body=[&](const auto &statements){for(auto statement:statements){expression(statement->expr);childBlocks(statement,body);}};
      body(function.body);pending.insert(pending.end(),function.dependencies.begin(),function.dependencies.end());
    }
  }
  TaskReferenceResult run(const std::string &entry,const std::vector<RV> &arguments){
    if(!program.taskPrototype)throw Error("E_TASK_STATE","reference scheduler requires checked task source");
    validateEntry(entry);
    rootSpan=program.function(entry).span;
    for(const auto &v:arguments)snapshot(v,none,none);
    auto root=std::make_unique<Job>();Activation a;a.scopeSpan=rootSpan;a.machine=std::make_unique<TaskAstMachine>(program,entry,arguments,limit-used,RV{},0,262144,controlPoll);root->stack.push_back(std::move(a));
    if(resourceRoot)root->resources.emplace(resourceRoot->taskChild());
    jobs.push_back(std::move(root));enqueue(0);
    while(jobs[0]->state!=Done){
      try{checkControl();}catch(const Error &){finishControl();break;}
      collectExternal();
      if(controlFailure){finishControl();break;}
      settle();if(jobs[0]->state==Done)break;
      bool ran=false;
      while(!ready.empty()){
        auto i=ready.front();ready.pop_front();auto &j=*jobs[i];j.queued=false;
        if(j.state!=Ready||j.cancelled)continue;
        turn(i);ran=true;break;
      }
      if(!ran&&!settle()){
        try{checkControl();}catch(const Error &){finishControl();break;}
        if(external&&external->stats().pending){
          if(resourceRoot||supportsTaskFileReads(program))external->waitForControl(std::chrono::milliseconds(10));
          else external->wait();
          continue;
        }
        if(resourceRetirementsPending()){
          std::this_thread::sleep_for(std::chrono::milliseconds(1));continue;
        }
        throw Error("E_TASK_DEADLOCK","reference tasks are parked with no possible progress");
      }
    }
    retireRootResources();
    try{checkControl();}catch(const Error &){finishControl();}
    if(jobs[0]->failure){auto error=*jobs[0]->failure;error.output=output;throw error;}
    TaskReferenceResult result;result.value=jobs[0]->result;result.output=output;result.steps=used;
    result.tasks=jobs.size();result.scopes=regions.size();result.channels=pipes.size();result.limits=limits;result.executionWorkers=1;
    if(external){result.external=external->stats();if(result.external.pending)throw Error("E_TASK_STATE","reference root completed before physical retirement");}
    return result;
  }
};
}
TaskReferenceResult evaluateTaskReference(const Program &p,const std::string &entry,const std::vector<RV> &arguments,uint64_t limit,TaskReferenceObserver observer,const nexrt::TaskExecutionLimits *taskLimits,TaskReferenceExternalHost *externalHost,const nexrt::FileReadGrant *fileGrant){
  try{
    std::unique_ptr<nexrt::RequestScope> request;
    std::unique_ptr<nexrt::FileScope> files;
#ifndef _WIN32
    nexrt::FileReadGrant captured;
    if(supportsTaskFileReads(p)){
      const auto limits=Reference::selectedLimits(limit,taskLimits);
      // The reference owns its exact source-work counter. This host scope
      // binds grants/control lifetime and never replaces an inherited request.
      if(!nexrt::inRequestScope())request=std::make_unique<nexrt::RequestScope>(nexrt::maximumTaskExecutionSteps,limits.timeoutMs);
      if(!fileGrant){
        if(!nexrt::inFileScope())files=std::make_unique<nexrt::FileScope>(true);
        captured=nexrt::captureFileReadGrant();fileGrant=&captured;
      }
    }
#endif
    Reference scheduler(p,limit,std::move(observer),taskLimits,externalHost,fileGrant);
    try{return scheduler.run(entry,arguments);}catch(Error &e){e.output=scheduler.output;annotateReferenceError(p,e);throw;}
  }catch(const nexrt::DataError &error){throw Error(error.code,error.what(),p.function(entry).span);}
  catch(const nexrt::Trap &error){throw Error(error.code,error.what(),p.function(entry).span);}
  catch(const std::bad_alloc &){throw Error("E_MEMORY","reference host allocation failed",p.function(entry).span);}
}
}
