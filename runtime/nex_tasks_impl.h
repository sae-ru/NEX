// Included inside namespace nexrt after the request/parallel runtime internals.
#ifndef NEX_STRUCTURED_WORKERS
#error NEX_ASYNC_TASKS requires NEX_STRUCTURED_WORKERS
#endif
namespace {
thread_local const void *activeTaskState=nullptr;
thread_local size_t activeTaskIndex=static_cast<size_t>(-1);
#ifdef NEX_TASK_PROFILE_ENABLED
thread_local uint64_t taskProfileTransactionStamp=0;
struct TaskProfileTransaction {
  uint64_t previous=taskProfileTransactionStamp;
  explicit TaskProfileTransaction(TaskProfileCollector *collector)noexcept{if(collector)taskProfileTransactionStamp=collector->sample().wallNs;}
  ~TaskProfileTransaction(){taskProfileTransactionStamp=previous;}
};
#endif
void taskValue(TaskGroup &group,const Value &value,const TaskGroup::Scope &target){
  hostOperation({},[&]{
    validateTaskSnapshot(group,value,target);
  });
}
}
struct TaskAccess {
  using Control=RequestScope::Control;
  static std::shared_ptr<Control> control(){
    if(!currentRequest||activeTaskState)throw Trap("E_TASK_SCOPE","a task group requires a coordinator request scope",0);
    return currentRequest->impl->control;
  }
  static bool same(const std::shared_ptr<Control> &control){return currentRequest&&currentRequest->impl->control==control;}
  static void poll(const std::shared_ptr<Control> &control){
    if(!same(control))throw Trap("E_TASK_SCOPE","task operation is outside its request",0);
    currentRequest->checkExecution(0,true,false);
  }
  static bool healthy(const std::shared_ptr<Control> &control){
    return control->active.load()&&!control->cancelled.load()&&!control->exhausted.load()&&std::chrono::steady_clock::now()<control->deadline;
  }
  static TaskExternalControl externalControl(const std::shared_ptr<Control> &control,const std::shared_ptr<const task_detail::Cancellation> &cancel){
    return TaskExternalControl([control,cancel]{
      if(!control->active.load()||control->cancelled.load())throw DataError("E_CANCELLED","external request was cancelled or ended");
      auto steps=control->steps.load();
      while(steps<control->budget&&!control->steps.compare_exchange_weak(steps,steps+1)){}
      if(steps>=control->budget)control->exhausted=true;
      if(control->exhausted.load())throw DataError("E_LIMIT","external request execution budget exceeded");
      if(std::chrono::steady_clock::now()>=control->deadline)throw DataError("E_TIMEOUT","external request deadline exceeded");
      if(cancel->stopped())throw DataError("E_CANCELLED","external task was cancelled");
    });
  }
  static void resume(const std::shared_ptr<Control> &control,const std::atomic<bool> &stop,
      const std::shared_ptr<const task_detail::Cancellation> &cancel,TaskBody::Handle handle,TaskGroup &group,TaskGroup::Scope resultScope,SourceLocation location){
    RequestScope scope(control,&stop);scope.impl->taskStop=cancel;ParallelDepth depth;
    hostOperation(location,[&]{
      scope.checkExecution(0,true,true);handle.resume();
      if(handle.done()){
        if(handle.promise().failure)std::rethrow_exception(handle.promise().failure);
        taskValue(group,handle.promise().value,resultScope);
      }
      scope.checkExecution(0,true,false);
    });
  }
};
struct TaskGroup::Impl {
  enum Wait { None, Future, Send, Receive, ScopeDrain, WaitExternal };
  struct External {TaskExternalTicket ticket;size_t scope=none;bool physical=false,consumed=false;};
  struct Job {
    TaskBody::Handle body;Value result,pending;TaskGroup *group=nullptr;std::weak_ptr<Data> capability;SourceLocation location;TaskEvent event;
    Value retiredResult,retiredPending,retiredEvent;
    size_t valueRetirementNext=none,valueRetirementsInFlight=0,retiredResultScope=none;
    bool valueRetirementQueued=false;
    std::exception_ptr failure,externalFatal;
    std::shared_ptr<task_detail::Cancellation> cancellation;
    Wait wait=None;size_t target=none,previous=none,next=none,head=none,tail=none;
    size_t scope=none,memberScope=none;
    std::vector<size_t> ownedScopes;
    std::vector<External> external;size_t externalPending=0;
    bool running=false,queued=false,again=false,done=false,observed=false,finishing=false,cleanupDone=false;
#ifdef NEX_TASK_PROFILE_ENABLED
    TaskProfileTask profileTask;TaskProfileSchedulerTotals profileTotals;
    uint64_t profileReadyAt=0,profileWaitAt=0,profileDrainAt=0;
    bool profilePending=false;
#endif
#ifdef NEX_TASK_DEBUG_ENABLED
    TaskDebugTask debugTask;
#endif
    ~Job(){if(body)body.destroy();}
  };
  struct Pipe {
    std::vector<std::optional<Value>> buffer;size_t start=0,count=0;
    std::vector<std::optional<Value>> retiredBuffer;
    size_t valueRetirementNext=none,retirementScope=none;
    bool valueRetirementQueued=false;
    size_t sendHead=none,sendTail=none,receiveHead=none,receiveTail=none;
    bool closed=false;size_t scope=none;std::weak_ptr<Data> capability;
    explicit Pipe(size_t capacity):buffer(capacity){}
    void push(Value value){buffer[(start+count)%buffer.size()]=std::move(value);++count;}
    Value pop(){auto value=std::move(*buffer[start]);buffer[start].reset();start=(start+1)%buffer.size();--count;return value;}
  };
  struct Region {
    size_t parent=none,owner=none,limit=1,active=0,pending=0,nested=0,externalPending=0,depth=1,head=none,tail=none;
    bool closing=false,closed=false,abort=false;
    bool valuesRetirementStarted=false;
    size_t valueRetirementsPending=0;
    std::vector<size_t> members,pipes,children;
    std::exception_ptr failure,externalFatal;std::weak_ptr<Data> capability;
    std::unique_ptr<ResourceRegion> resources;
    std::optional<ResourceRegionRetirement> resourceRetirement;
    bool resourceRetirementStarted=false,resourceRetirementRequested=false,resourceRetirementInFlight=false;
  };
  std::unique_ptr<ResourceRegion> resourceRoot;
  std::vector<std::unique_ptr<Region>> regions;
  std::vector<uint64_t> graphSeen;std::vector<size_t> graphWork;uint64_t graphEpoch=0;
  std::shared_ptr<TaskAccess::Control> control;
  std::thread::id coordinator=std::this_thread::get_id();
  std::mutex mutex;std::condition_variable changed;
  std::vector<std::unique_ptr<Job>> jobs;
  std::vector<std::unique_ptr<Pipe>> pipes;
  std::vector<size_t> ready;size_t readyStart=0,readyCount=0,completed=0,reservedSlots=0;
  size_t valueJobHead=none,valueJobTail=none,valuePipeHead=none,valuePipeTail=none,valueRetirementsInFlight=0;
  std::vector<size_t> completionWork;std::vector<uint8_t> completionQueued;
  size_t completionStart=0,completionCount=0;bool completing=false;
  std::atomic<bool> cancelled{false};
  const bool sourceFileReadFailures;std::exception_ptr sourceFileReadFatal;
  bool started=false,stop=false,sealed=false,finished=false;
  std::vector<std::jthread> threads;
  TaskExternalLimits externalLimits;std::once_flag externalInit;std::unique_ptr<TaskExternalPool> externalPool;bool externalRetirementReady=false;
#ifdef NEX_TASK_PROFILE_ENABLED
  TaskProfileCollector *profileCollector=taskProfileCollector();
  uint64_t profileLastStamp=0;
  std::vector<size_t> profilePending;size_t profileRead=0,profileCount=0;
  uint64_t profileNow()noexcept{profileLastStamp=std::max(profileLastStamp,taskProfileTransactionStamp);return profileLastStamp;}
  void profileAdd(Job &job,uint64_t &destination,uint64_t start,uint64_t end)noexcept{
    if(!start||end<start||end-start>std::numeric_limits<uint64_t>::max()-destination){job.profileTotals.elapsedAvailable=false;return;}destination+=end-start;
  }
  void profileWaitEnd(Job &job,Wait reason)noexcept{
    if(!profileCollector||!job.profileWaitAt)return;
    auto *destination=reason==Future?&job.profileTotals.blockedFutureNs:reason==Send?&job.profileTotals.blockedSendNs:reason==Receive?&job.profileTotals.blockedReceiveNs:reason==ScopeDrain?&job.profileTotals.blockedScopeNs:&job.profileTotals.blockedExternalNs;
    profileAdd(job,*destination,job.profileWaitAt,profileNow());job.profileWaitAt=0;
  }
  void profilePublish(size_t index)noexcept{
    if(!profileCollector)return;auto &job=*jobs[index];
    if(job.profileDrainAt)profileAdd(job,job.profileTotals.drainNs,job.profileDrainAt,profileNow());
    if(profileCount>=profilePending.size())return; // Incomplete metadata cannot affect execution.
    profilePending[(profileRead+profileCount)%profilePending.size()]=index;++profileCount;job.profilePending=true;
  }
  void flushProfiles()noexcept{
    if(!profileCollector)return;
    for(;;){TaskProfileTask task;TaskProfileSchedulerTotals totals;TaskProfileTaskOutcome outcome;
      {std::lock_guard lock(mutex);if(!profileCount)return;const auto index=profilePending[profileRead];profileRead=(profileRead+1)%profilePending.size();--profileCount;
        auto &job=*jobs[index];job.profilePending=false;task=job.profileTask;totals=job.profileTotals;outcome=job.failure?(cancellationFailure(job.failure)?TaskProfileTaskOutcome::Cancelled:TaskProfileTaskOutcome::Aborted):TaskProfileTaskOutcome::Completed;}
      if(task){profileCollector->scheduler(task,totals);profileCollector->terminal(task,outcome);}
    }
  }
#endif
#ifdef NEX_TASK_DEBUG_ENABLED
  bool debugEnabled=taskDebugEnabled();
#endif
  Impl(size_t workers,size_t maximum,TaskExternalLimits limits,bool fileReadFailures):control(TaskAccess::control()),ready(maximum),sourceFileReadFailures(fileReadFailures),externalLimits(limits){
    if(workers<1||workers>16||maximum<1||maximum>65536)throw Trap("E_RANGE","task group requires1..16 workers and1..65536 task slots",0);
    jobs.reserve(maximum);pipes.reserve(1024);regions.reserve(1024);graphSeen.resize(maximum+1024);graphWork.reserve(maximum+1024);threads.reserve(workers);
    completionWork.resize(maximum+1024);completionQueued.resize(maximum+1024);
#ifdef NEX_TASK_PROFILE_ENABLED
    if(profileCollector)profilePending.resize(maximum);
#endif
    try{
      for(size_t i=0;i<workers;++i)threads.emplace_back([this]{work();});
      {std::lock_guard lock(mutex);started=true;}changed.notify_all();
    }catch(...){
      {std::lock_guard lock(mutex);stop=true;}changed.notify_all();
      for(auto &thread:threads)thread.join();throw;
    }
  }
  void requireContext(bool coordinatorOnly=false){
    bool worker=activeTaskState==this;
    if((!worker&&std::this_thread::get_id()!=coordinator)||(coordinatorOnly&&worker)||!TaskAccess::same(control))
      throw Trap("E_TASK_SCOPE","task operation belongs to another scope or thread",0);
  }
  void require(bool coordinatorOnly=false){
    requireContext(coordinatorOnly);bool worker=activeTaskState==this;
    TaskAccess::poll(control);
    if(cancelled.load()&&worker)throw Trap("E_CANCELLED","task group was cancelled",0);
  }
  // Intrusive queues use admitted Job/Pipe storage. No cleanup admission or
  // allocation can fail after a value has to be discarded under the mutex.
  void queueValueRetirement(size_t index)noexcept{
    auto &job=*jobs[index];if(job.valueRetirementQueued)return;
    job.valueRetirementQueued=true;job.valueRetirementNext=none;
    if(valueJobTail==none)valueJobHead=index;else jobs[valueJobTail]->valueRetirementNext=index;
    valueJobTail=index;changed.notify_all();
  }
  void retireValue(size_t index,Value &value,Value &retired)noexcept{
    if(value.object){
      if(retired.object)std::terminate(); // A reusable field must be flushed before reuse.
      retired=std::move(value);queueValueRetirement(index);
    }
    value={};
  }
  void retirePending(size_t index)noexcept{auto &job=*jobs[index];retireValue(index,job.pending,job.retiredPending);}
  void retireEvent(size_t index)noexcept{auto &job=*jobs[index];retireValue(index,job.event.value,job.retiredEvent);job.event.present=false;}
  void setEvent(size_t index,TaskEvent event)noexcept{retireEvent(index);jobs[index]->event=std::move(event);}
  void retireResult(size_t index,size_t scope=none)noexcept{
    auto &job=*jobs[index];
    if(job.result.object&&scope!=none){
      if(job.retiredResultScope!=none)std::terminate();
      job.retiredResultScope=scope;++regions[scope]->valueRetirementsPending;
    }
    retireValue(index,job.result,job.retiredResult);
  }
  void retirePipeBuffer(size_t index,size_t scope)noexcept{
    auto &pipe=*pipes[index];
    if(pipe.valueRetirementQueued||!pipe.retiredBuffer.empty())std::terminate();
    pipe.buffer.swap(pipe.retiredBuffer);pipe.count=pipe.start=0;
    if(pipe.retiredBuffer.empty())return;
    pipe.retirementScope=scope;++regions[scope]->valueRetirementsPending;
    pipe.valueRetirementQueued=true;pipe.valueRetirementNext=none;
    if(valuePipeTail==none)valuePipeHead=index;else pipes[valuePipeTail]->valueRetirementNext=index;
    valuePipeTail=index;changed.notify_all();
  }
  void flushValueRetirements(){
    for(;;){
      size_t jobIndex=none,pipeIndex=none,scope=none,slots=0;
      std::array<Value,3> values;std::vector<std::optional<Value>> buffer;
#ifdef NEX_TASK_PROFILE_ENABLED
      TaskProfileTask profileTask;
#endif
#ifdef NEX_TASK_DEBUG_ENABLED
      TaskDebugTask debugTask;
#endif
      {
        std::lock_guard lock(mutex);
        size_t metadataOwner=none;
        if(valueJobHead!=none){
          jobIndex=valueJobHead;auto &job=*jobs[jobIndex];valueJobHead=job.valueRetirementNext;
          if(valueJobHead==none)valueJobTail=none;
          job.valueRetirementQueued=false;job.valueRetirementNext=none;++job.valueRetirementsInFlight;
          values[0]=std::move(job.retiredResult);values[1]=std::move(job.retiredPending);values[2]=std::move(job.retiredEvent);
          scope=std::exchange(job.retiredResultScope,none);metadataOwner=jobIndex;
        }else if(valuePipeHead!=none){
          pipeIndex=valuePipeHead;auto &pipe=*pipes[pipeIndex];valuePipeHead=pipe.valueRetirementNext;
          if(valuePipeHead==none)valuePipeTail=none;
          pipe.valueRetirementQueued=false;pipe.valueRetirementNext=none;buffer.swap(pipe.retiredBuffer);
          scope=std::exchange(pipe.retirementScope,none);slots=buffer.size();metadataOwner=regions[scope]->owner;
        }else return;
        ++valueRetirementsInFlight;
#ifdef NEX_TASK_PROFILE_ENABLED
        profileTask=jobs[metadataOwner]->profileTask;
#endif
#ifdef NEX_TASK_DEBUG_ENABLED
        debugTask=jobs[metadataOwner]->debugTask;
#endif
        (void)metadataOwner;
      }
      {
#ifdef NEX_TASK_DEBUG_ENABLED
        TaskDebugTurn debug(debugTask);
#endif
#ifdef NEX_TASK_PROFILE_ENABLED
        TaskProfileTurnScope profile(profileTask,false);
#endif
        // Last aliases, actual payloads and buffer storage all leave outside
        // the scheduler mutex. Reentrant cleanup may enqueue another batch.
        values={};std::vector<std::optional<Value>>().swap(buffer);
      }
      {
        std::lock_guard lock(mutex);
        if(!valueRetirementsInFlight)std::terminate();--valueRetirementsInFlight;
        if(jobIndex!=none){auto &job=*jobs[jobIndex];if(!job.valueRetirementsInFlight)std::terminate();--job.valueRetirementsInFlight;tryComplete(jobIndex);}
        if(pipeIndex!=none){if(slots>reservedSlots)std::terminate();reservedSlots-=slots;}
        if(scope!=none){auto &region=*regions[scope];if(!region.valueRetirementsPending)std::terminate();--region.valueRetirementsPending;closeRegion(scope);}
        changed.notify_all();
      }
    }
  }
  struct ValueFlush {Impl *state;~ValueFlush(){state->flushValueRetirements();}};
  void enqueue(size_t index){
    auto &job=*jobs[index];if(job.done||job.finishing||job.queued)return;
    if(job.running){job.again=true;return;}
    ready[(readyStart+readyCount)%ready.size()]=index;++readyCount;job.queued=true;changed.notify_all();
#ifdef NEX_TASK_DEBUG_ENABLED
    taskDebugKernelState(job.debugTask,TaskDebugState::Ready);
#endif
#ifdef NEX_TASK_PROFILE_ENABLED
    if(profileCollector)job.profileReadyAt=profileNow();
#endif
  }
  std::pair<size_t*,size_t*> ends(Job &job){
    if(job.wait==Future)return {&jobs[job.target]->head,&jobs[job.target]->tail};
    if(job.wait==ScopeDrain)return {&regions[job.target]->head,&regions[job.target]->tail};
    auto &pipe=*pipes[job.target];
    return job.wait==Send?std::pair{&pipe.sendHead,&pipe.sendTail}:std::pair{&pipe.receiveHead,&pipe.receiveTail};
  }
  void unlink(size_t index){
    auto &job=*jobs[index];if(job.wait==None)return;
#ifdef NEX_TASK_PROFILE_ENABLED
    profileWaitEnd(job,job.wait);
#endif
    if(job.wait==WaitExternal){job.wait=None;job.previous=job.next=job.target=none;return;}
    auto [head,tail]=ends(job);
    if(job.previous==none)*head=job.next;else jobs[job.previous]->next=job.next;
    if(job.next==none)*tail=job.previous;else jobs[job.next]->previous=job.previous;
    job.wait=None;job.previous=job.next=job.target=none;
  }
  void link(size_t index,Wait wait,size_t target){
    auto &job=*jobs[index];job.wait=wait;job.target=target;auto [head,tail]=ends(job);
#ifdef NEX_TASK_DEBUG_ENABLED
    auto debugWait=wait==Future?TaskDebugWait::Future:wait==Send?TaskDebugWait::Send:wait==Receive?TaskDebugWait::Receive:TaskDebugWait::Scope;
    taskDebugKernelState(job.debugTask,TaskDebugState::Blocked,debugWait,wait==Future?jobs[target]->debugTask.id:0);
#endif
#ifdef NEX_TASK_PROFILE_ENABLED
    if(profileCollector)job.profileWaitAt=profileNow();
#endif
    job.previous=*tail;job.next=none;
    if(*tail==none)*head=index;else jobs[*tail]->next=index;*tail=index;
  }
  void wake(size_t index){unlink(index);enqueue(index);}
  void interrupt(){
    const bool global=cancelled.load()||!TaskAccess::healthy(control);
    for(size_t i=0;i<jobs.size();++i){auto &job=*jobs[i];
      if(!job.done&&(global||job.cancellation->stopped())){
        if(externalPool)for(auto &entry:job.external)if(!entry.consumed)externalPool->cancel(entry.ticket);
        if(job.wait!=None){retirePending(i);wake(i);}
      }
    }
  }
  bool within(size_t ancestor,size_t descendant)const{
    for(size_t next=descendant;next!=none;next=regions[next]->parent)if(next==ancestor)return true;
    return false;
  }
  void scopeAccess(size_t scope)const{
    if(scope==none)return;
    if(scope>=regions.size()||regions[scope]->closed||activeTaskState!=this||activeTaskIndex>=jobs.size()||!within(scope,jobs[activeTaskIndex]->scope))throw Trap("E_TASK_SCOPE","logical task scope is foreign or has ended",0);
  }
  static bool resourceFailure(const std::exception_ptr &failure){
    if(!failure)return false;
    try{std::rethrow_exception(failure);}catch(const Trap &e){return e.code=="E_MEMORY"||e.code=="E_LIMIT"||e.code=="E_TIMEOUT"||e.code=="E_CANCELLED";}
    catch(const std::bad_alloc &){return true;}catch(...){return false;}
  }
  static bool cancellationFailure(const std::exception_ptr &failure){
    if(!failure)return false;try{std::rethrow_exception(failure);}catch(const Trap &error){return error.code=="E_CANCELLED";}catch(...){return false;}
  }
  static bool fatalFailure(const std::exception_ptr &failure){return resourceFailure(failure)&&!cancellationFailure(failure);}
  static void preferFailure(std::exception_ptr &selected,const std::exception_ptr &candidate){
    if(candidate&&(!selected||(fatalFailure(candidate)&&!fatalFailure(selected))||(!resourceFailure(selected)&&resourceFailure(candidate))))selected=candidate;
  }
  // Scheduler mutex held. Only canonical runtime failures reach this boundary;
  // the selected exception stays retained until the group is physically drained.
  void selectFileReadFatal(const std::exception_ptr &failure){
    if(!sourceFileReadFailures||!fatalFailure(failure))return;
    preferFailure(sourceFileReadFatal,failure);cancelled=true;interrupt();changed.notify_all();
  }
  bool dependencyCycle(size_t index,size_t target,bool scopeRoot){
    // All graph storage is reserved before workers start. Completion/cleanup
    // must not allocate, even when draining after a resource failure.
    if(++graphEpoch==0){std::fill(graphSeen.begin(),graphSeen.end(),0);graphEpoch=1;}
    graphWork.clear();
    auto add=[&](size_t node){if(node==index)return true;if(graphSeen[node]!=graphEpoch){graphSeen[node]=graphEpoch;graphWork.push_back(node);}return false;};
    if(add(scopeRoot?ready.size()+target:target))return true;
    while(!graphWork.empty()){
      auto next=graphWork.back();graphWork.pop_back();
      if(next>=ready.size()){
        const auto &scope=*regions[next-ready.size()];if(scope.closed)continue;
        for(auto member:scope.members)if(!jobs[member]->done&&add(member))return true;
        for(auto child:scope.children)if(!regions[child]->closed&&add(ready.size()+child))return true;
      }else{
        const auto &job=*jobs[next];if(job.done)continue;
        if(job.wait==Future){if(add(job.target))return true;}
        else if(job.wait==ScopeDrain&&add(ready.size()+job.target))return true;
      }
    }
    return false;
  }
  bool waitCycle(size_t index,size_t target){return dependencyCycle(index,target,false);}
  bool scopeCycle(size_t index,size_t scope){return dependencyCycle(index,scope,true);}
  void cancelRegion(size_t scope){
    for(auto &job:jobs)if(!job->done&&within(scope,job->memberScope))job->cancellation->cancelled=true;
    if(externalPool)for(auto &job:jobs)for(auto &entry:job->external)
      if(!entry.consumed&&entry.scope!=none&&within(scope,entry.scope))externalPool->cancel(entry.ticket);
    interrupt();changed.notify_all();
  }
  void closePipe(size_t index){
    auto &pipe=*pipes[index];if(pipe.closed)return;pipe.closed=true;
    while(pipe.sendHead!=none){auto sender=pipe.sendHead;retirePending(sender);retireEvent(sender);wake(sender);}
    while(pipe.receiveHead!=none){auto receiver=pipe.receiveHead;setEvent(receiver,pipe.count?TaskEvent{true,pipe.pop()}:TaskEvent{});wake(receiver);}
  }
  void queueCompletion(size_t index,bool scope)noexcept{
    const auto node=scope?ready.size()+index:index;
    if(node>=completionQueued.size())std::terminate();
    if(completionQueued[node])return;
    if(completionCount>=completionWork.size())std::terminate();
    completionQueued[node]=1;completionWork[(completionStart+completionCount)%completionWork.size()]=node;++completionCount;
  }
  void completeQueued(){
    if(completing)return;
    completing=true;struct Reset {bool &value;~Reset(){value=false;}}reset{completing};
    while(completionCount){
      const auto node=completionWork[completionStart];completionStart=(completionStart+1)%completionWork.size();--completionCount;completionQueued[node]=0;
      if(node>=ready.size())closeRegionStep(node-ready.size());else tryCompleteStep(node);
    }
  }
  void closeRegion(size_t index){queueCompletion(index,true);completeQueued();}
  void tryComplete(size_t index){queueCompletion(index,false);completeQueued();}
  void closeRegionStep(size_t index){
    auto &scope=*regions[index];if(scope.closed||!scope.closing||scope.pending||scope.nested||scope.externalPending)return;
    if(scope.resources){
      if(!scope.resourceRetirementStarted){scope.resourceRetirement.emplace(scope.resources->beginClose());scope.resourceRetirementStarted=true;}
      if(scope.resourceRetirementInFlight||!scope.resourceRetirement->ready()){changed.notify_all();return;}
    }
    if(!scope.valuesRetirementStarted){
      scope.valuesRetirementStarted=true;
      for(auto member:scope.members)retireResult(member,index);
      for(auto pipe:scope.pipes){closePipe(pipe);retirePipeBuffer(pipe,index);}
    }
    if(scope.valueRetirementsPending)return;
    scope.closed=true;
    if(scope.externalFatal)preferFailure(scope.failure,scope.externalFatal);
    for(auto member:scope.members){auto &job=*jobs[member];
      if(!scope.abort&&!job.observed&&!job.cancellation->stopped())preferFailure(scope.failure,job.failure);
      job.observed=true;job.capability.reset();
    }
    scope.capability.reset();
    auto &owner=*jobs[scope.owner];
    if(scope.externalFatal)preferFailure(owner.externalFatal,scope.externalFatal);
    if(owner.scope==index){if(owner.running){if(!scope.active)throw Trap("E_TASK_STATE","logical task lease is unbalanced",0);--scope.active;}owner.scope=scope.parent;}
    if(scope.active)throw Trap("E_TASK_STATE","closed logical task scope has active workers",0);
    if(owner.finishing)preferFailure(owner.failure,scope.failure);
    while(scope.head!=none)wake(scope.head);
    if(scope.parent!=none){auto &parent=*regions[scope.parent];if(scope.externalFatal){preferFailure(parent.externalFatal,scope.externalFatal);preferFailure(parent.failure,scope.externalFatal);}if(!parent.nested)throw Trap("E_TASK_STATE","logical nested scope count is unbalanced",0);--parent.nested;closeRegion(scope.parent);}
    tryComplete(scope.owner);changed.notify_all();
  }
  void flushResourceRetirements(){
    // Extract one cleanup request under the scheduler lock, perform every
    // possible foreign destructor outside it, then publish only a settled fence.
    for(;;){
      size_t index=none;std::optional<ResourceRegionRetirement> retirement;
      {std::lock_guard lock(mutex);if(!resourceRoot)return;
        for(size_t i=0;i<regions.size();++i){auto &scope=*regions[i];
          if(!scope.resourceRetirementStarted||scope.closed||scope.resourceRetirementInFlight)continue;
          if(scope.resourceRetirement->ready()){closeRegion(i);continue;}
          if(!scope.resourceRetirementRequested){index=i;scope.resourceRetirementInFlight=true;
            retirement.emplace(std::move(*scope.resourceRetirement));scope.resourceRetirement.reset();break;}
        }
      }
      if(index==none)return;
      retirement->requestClose();
      {std::lock_guard lock(mutex);auto &scope=*regions[index];scope.resourceRetirement.emplace(std::move(*retirement));
        scope.resourceRetirementInFlight=false;scope.resourceRetirementRequested=true;closeRegion(index);changed.notify_all();}
    }
  }
  void tryCompleteStep(size_t index){
    auto &job=*jobs[index];if(!job.finishing||!job.cleanupDone)return;
    if(job.valueRetirementQueued||job.valueRetirementsInFlight)return;
    if(job.externalPending)return;
    for(const auto &entry:job.external)if(!entry.consumed)return;
    for(auto scope:job.ownedScopes)if(!regions[scope]->closed)return;
    if(job.failure){retireResult(index);if(job.valueRetirementQueued)return;}
    job.finishing=false;job.done=true;++completed;
#ifdef NEX_TASK_DEBUG_ENABLED
    taskDebugKernelState(job.debugTask,TaskDebugState::Terminal);
#endif
#ifdef NEX_TASK_PROFILE_ENABLED
    profilePublish(index);
#endif
    while(job.head!=none)wake(job.head);
    if(job.memberScope!=none){auto &scope=*regions[job.memberScope];if(!scope.pending)throw Trap("E_TASK_STATE","logical task count is unbalanced",0);--scope.pending;closeRegion(job.memberScope);}
    changed.notify_all();
  }
  void retireExternal(Job &job,External &entry){
    entry.consumed=true;std::exception_ptr failure;
    try{(void)externalPool->take(entry.ticket);}
    catch(const DataError &error){try{throw Trap(error.code,error.what(),job.location);}catch(...){failure=std::current_exception();}}
    catch(const std::bad_alloc &){try{throw Trap("E_MEMORY","external host allocation failed",job.location);}catch(...){failure=std::current_exception();}}
    catch(...){failure=std::current_exception();}
    bool fatal=fatalFailure(failure);
    if(fatal)selectFileReadFatal(failure);
    if(fatal){preferFailure(job.externalFatal,failure);if(entry.scope!=none)preferFailure(regions[entry.scope]->externalFatal,failure);}
    if(failure&&(fatal||((entry.scope==none||!regions[entry.scope]->abort)&&!(job.failure&&cancellationFailure(failure))))){
      if(job.finishing||entry.scope==none)preferFailure(job.failure,failure);
      else preferFailure(regions[entry.scope]->failure,failure);
    }
    if(entry.scope!=none){auto &scope=*regions[entry.scope];if(!scope.externalPending)std::terminate();--scope.externalPending;closeRegion(entry.scope);}
  }
  bool canRetireExternal(size_t index,const External &entry)const{
    const auto &job=*jobs[index];if(job.finishing)return true;
    return entry.scope!=none&&regions[entry.scope]->owner==index&&regions[entry.scope]->closing&&job.wait==ScopeDrain&&job.target==entry.scope;
  }
  void retireExternalCompletions(){
    // Only task scheduler workers accept/discard raw completions or publish a
    // finished source task. IO notification threads merely mark/wake tickets.
    if(!externalRetirementReady)return;
    externalRetirementReady=false;
    for(size_t index=0;index<jobs.size();++index){auto &job=*jobs[index];
      for(auto &entry:job.external)if(entry.physical&&!entry.consumed&&canRetireExternal(index,entry))retireExternal(job,entry);
      tryComplete(index);
    }
  }
  void beginComplete(size_t index,std::exception_ptr failure){
    auto &job=*jobs[index];unlink(index);job.running=false;job.again=false;job.finishing=true;job.failure=std::move(failure);
    retirePending(index);retireEvent(index);
#ifdef NEX_TASK_DEBUG_ENABLED
    taskDebugKernelState(job.debugTask,TaskDebugState::Draining);
#endif
#ifdef NEX_TASK_PROFILE_ENABLED
    if(profileCollector)job.profileDrainAt=profileNow();
#endif
    if(!job.failure)job.result=std::move(job.body.promise().value);
    size_t outer=none;
    for(auto scope:job.ownedScopes)if(!regions[scope]->closed){if(outer==none)outer=scope;regions[scope]->closing=true;regions[scope]->abort=bool(job.failure);}
    if(!job.failure&&outer!=none&&scopeCycle(index,outer)){
      try{throw Trap("E_TASK_CYCLE","cyclic logical scope drain",0);}catch(...){job.failure=std::current_exception();}
      for(auto scope:job.ownedScopes)if(!regions[scope]->closed)regions[scope]->abort=true;
    }
    if(job.failure&&outer!=none)cancelRegion(outer);
    if(externalPool)for(auto &entry:job.external)if(!entry.consumed){
      if(job.failure)externalPool->cancel(entry.ticket);
      if(entry.physical)retireExternal(job,entry);
    }
    for(auto it=job.ownedScopes.rbegin();it!=job.ownedScopes.rend();++it)closeRegion(*it);
  }
  void lease(size_t scope,int delta){
    for(auto next=scope;next!=none;next=regions[next]->parent){auto &region=*regions[next];if(delta>0)++region.active;else{if(!region.active)throw Trap("E_TASK_STATE","logical task worker lease is unbalanced",0);--region.active;}}
  }
  size_t runnable(){
    size_t count=readyCount;
    while(count--){
      auto index=ready[readyStart];readyStart=(readyStart+1)%ready.size();--readyCount;auto &job=*jobs[index];bool allowed=true;
      if(job.valueRetirementQueued||job.valueRetirementsInFlight)allowed=false;
      for(auto next=job.scope;next!=none;next=regions[next]->parent)if(regions[next]->active>=regions[next]->limit){allowed=false;break;}
      if(allowed){job.queued=false;job.running=true;job.again=false;
#ifdef NEX_TASK_DEBUG_ENABLED
        taskDebugKernelState(job.debugTask,TaskDebugState::Running);
#endif
#ifdef NEX_TASK_PROFILE_ENABLED
        if(profileCollector&&job.profileReadyAt){profileAdd(job,job.profileTotals.readyNs,job.profileReadyAt,profileNow());job.profileReadyAt=0;}
#endif
        lease(job.scope,1);return index;}
      ready[(readyStart+readyCount)%ready.size()]=index;++readyCount;
    }
    return none;
  }
  void work(){
    for(;;){
#ifdef NEX_TASK_PROFILE_ENABLED
      flushProfiles();TaskProfileTransaction profileTransaction(profileCollector);
#endif
      size_t index;Job *runningJob;
      {
        std::unique_lock lock(mutex);changed.wait(lock,[&]{return started||stop;});
        while(!stop){
          const bool resourceRegionsEnabled=bool(resourceRoot);
          lock.unlock();flushValueRetirements();if(resourceRegionsEnabled)flushResourceRetirements();lock.lock();
          retireExternalCompletions();interrupt();index=runnable();if(index!=none)break;
#ifdef NEX_TASK_PROFILE_ENABLED
          if(profileCollector&&profileCount){lock.unlock();flushProfiles();taskProfileTransactionStamp=profileCollector->sample().wallNs;lock.lock();continue;}
#endif
          changed.wait_for(lock,std::chrono::milliseconds(2));
#ifdef NEX_TASK_PROFILE_ENABLED
          if(profileCollector){lock.unlock();flushProfiles();taskProfileTransactionStamp=profileCollector->sample().wallNs;lock.lock();}
#endif
        }
        if(stop)return;
        runningJob=jobs[index].get();
      }
      auto previousState=activeTaskState;auto previousIndex=activeTaskIndex;
      activeTaskState=this;activeTaskIndex=index;
      std::exception_ptr failure;
      try{
#ifdef NEX_TASK_DEBUG_ENABLED
        TaskDebugTurn debug(runningJob->debugTask);
#endif
#ifdef NEX_TASK_PROFILE_ENABLED
        TaskProfileTurnScope profile(runningJob->profileTask);
#endif
        TaskAccess::resume(control,cancelled,runningJob->cancellation,runningJob->body,*runningJob->group,runningJob->memberScope==none?Scope{}:Scope(runningJob->group->impl,runningJob->memberScope),runningJob->location);}
      catch(...){failure=std::current_exception();}
      activeTaskState=previousState;activeTaskIndex=previousIndex;
      TaskBody::Handle destroy;
#ifdef NEX_TASK_PROFILE_ENABLED
      TaskProfileTransaction profileFinishing(profileCollector);
#endif
      {
        std::lock_guard lock(mutex);auto &job=*jobs[index];lease(job.scope,-1);job.running=false;
        if(failure||job.body.done()){selectFileReadFatal(failure);beginComplete(index,std::move(failure));destroy=std::exchange(job.body,{});}
        else if(job.again)enqueue(index);
        else if(job.wait==None){
          try{throw Trap("E_TASK_STATE","coroutine suspended outside its task scheduler",0);}catch(...){beginComplete(index,std::current_exception());destroy=std::exchange(job.body,{});}
        }
        changed.notify_all();
      }
      // Destroy all retained native frames before publishing completion, outside
      // the scheduler mutex so owned-value/profile destructors cannot deadlock it.
      if(destroy){
        {
#ifdef NEX_TASK_DEBUG_ENABLED
          TaskDebugTurn debug(runningJob->debugTask);
#endif
#ifdef NEX_TASK_PROFILE_ENABLED
          TaskProfileTurnScope profile(runningJob->profileTask,false);
#endif
          destroy.destroy();
        }
#ifdef NEX_TASK_PROFILE_ENABLED
        TaskProfileTransaction profileRetirement(profileCollector);
#endif
        std::lock_guard lock(mutex);jobs[index]->cleanupDone=true;tryComplete(index);
      }
    }
  }
  bool suspend(size_t index,Awaiter::Kind kind,size_t target,Value value){
#ifdef NEX_TASK_PROFILE_ENABLED
    TaskProfileTransaction profileTransaction(profileCollector);
#endif
    require();
    ValueFlush flush{this};
    if(kind==Awaiter::Send){Scope targetScope;TaskGroup *group;{std::lock_guard lock(mutex);if(target>=pipes.size()||index>=jobs.size())throw Trap("E_TASK_SCOPE","invalid channel/task",0);group=jobs[index]->group;if(pipes[target]->scope!=none)targetScope=Scope(group->impl,pipes[target]->scope);}taskValue(*group,value,targetScope);}
    std::lock_guard lock(mutex);
    if(index>=jobs.size()||activeTaskState!=this||activeTaskIndex!=index)throw Trap("E_TASK_SCOPE","awaiter belongs to another task",0);
    auto &job=*jobs[index];retireEvent(index);
    if(kind==Awaiter::Yield){job.again=true;
#ifdef NEX_TASK_DEBUG_ENABLED
      taskDebugKernelState(job.debugTask,TaskDebugState::Ready);
#endif
      return true;}
    if(kind==Awaiter::DrainScope){
      if(target>=regions.size()||regions[target]->closed||regions[target]->owner!=index||job.scope!=target)throw Trap("E_TASK_SCOPE","logical scope exit must belong to its innermost owner",0);
      auto &scope=*regions[target];
      if(!value.scalar&&scopeCycle(index,target))throw Trap("E_TASK_CYCLE","cyclic logical scope drain",0);
      scope.closing=true;scope.abort=bool(value.scalar);
      if(scope.abort)cancelRegion(target);
      if(scope.externalPending)externalRetirementReady=true;
      if(!scope.pending&&!scope.nested&&!scope.externalPending){closeRegion(target);if(scope.closed)return false;}
      link(index,ScopeDrain,target);return true;
    }
    if(kind==Awaiter::Future){
      if(target>=jobs.size())throw Trap("E_TASK_SCOPE","invalid task ticket",0);
      if(waitCycle(index,target))throw Trap("E_TASK_CYCLE","cyclic task wait",0);
      if(jobs[target]->done)return false;
      link(index,Future,target);return true;
    }
    if(finished||target>=pipes.size())throw Trap("E_TASK_SCOPE","channel scope has ended",0);
    auto &pipe=*pipes[target];scopeAccess(pipe.scope);
    if(kind==Awaiter::Send){
      if(pipe.closed)return false;
      if(pipe.receiveHead!=none){size_t receiver=pipe.receiveHead;setEvent(receiver,{true,std::move(value)});wake(receiver);job.event.present=true;return false;}
      if(pipe.count<pipe.buffer.size()){pipe.push(std::move(value));job.event.present=true;return false;}
      job.pending=std::move(value);link(index,Send,target);return true;
    }
    if(pipe.count){
      setEvent(index,{true,pipe.pop()});
      if(pipe.sendHead!=none){auto sender=pipe.sendHead;pipe.push(std::move(jobs[sender]->pending));retirePending(sender);jobs[sender]->event.present=true;wake(sender);}
      return false;
    }
    if(pipe.sendHead!=none){auto sender=pipe.sendHead;setEvent(index,{true,std::move(jobs[sender]->pending)});retirePending(sender);jobs[sender]->event.present=true;wake(sender);return false;}
    if(pipe.closed)return false;
    link(index,Receive,target);return true;
  }
  void drain(bool abort){
#ifdef NEX_TASK_PROFILE_ENABLED
    TaskProfileTransaction profileTransaction(profileCollector);
#endif
    {
      std::lock_guard lock(mutex);if(finished)return;sealed=true;
      if(abort)cancelled=true;interrupt();changed.notify_all();
    }
    std::exception_ptr coordinatorFailure;
    for(;;){
#ifdef NEX_TASK_PROFILE_ENABLED
      TaskProfileTransaction profileTick(profileCollector);
#endif
      flushValueRetirements();
      std::unique_lock lock(mutex);preferFailure(coordinatorFailure,sourceFileReadFatal);
      if(completed==jobs.size()&&valueJobHead==none&&valuePipeHead==none&&!valueRetirementsInFlight)break;
      lock.unlock();
      if(!abort&&!coordinatorFailure)try{TaskAccess::poll(control);}catch(...){coordinatorFailure=std::current_exception();cancelled=true;}
      lock.lock();selectFileReadFatal(coordinatorFailure);interrupt();changed.wait_for(lock,std::chrono::milliseconds(2));
    }
    if(resourceRoot){
      auto retirement=resourceRoot->beginClose();retirement.requestClose();
      while(!retirement.ready()){
        if(!abort&&!coordinatorFailure)try{TaskAccess::poll(control);}catch(...){coordinatorFailure=std::current_exception();cancelled=true;}
        std::unique_lock lock(mutex);changed.wait_for(lock,std::chrono::milliseconds(2));
      }
    }
    {std::lock_guard lock(mutex);stop=true;}changed.notify_all();
    for(auto &thread:threads)thread.join();
#ifdef NEX_TASK_PROFILE_ENABLED
    flushProfiles();
#endif
    if(externalPool)externalPool->drain(abort);
    {std::lock_guard lock(mutex);finished=true;}
    // Workers are joined. Frame destructors and profiling hooks run outside the
    // scheduler lock; they cannot deadlock by acquiring another runtime lock.
    for(auto &job:jobs){
      if(job->body){
#ifdef NEX_TASK_DEBUG_ENABLED
        TaskDebugTurn debug(job->debugTask);
#endif
#ifdef NEX_TASK_PROFILE_ENABLED
        TaskProfileTurnScope profile(job->profileTask,false);
#endif
        job->body.destroy();job->body={};
      }job->pending={};job->event={};}
    pipes.clear();
    if(sourceFileReadFatal){auto selected=sourceFileReadFatal;preferFailure(selected,coordinatorFailure);coordinatorFailure=std::move(selected);}
    if(!abort)for(const auto &job:jobs)if(!job->observed&&job->externalFatal){preferFailure(coordinatorFailure,job->failure);preferFailure(coordinatorFailure,job->externalFatal);}
    if(coordinatorFailure)std::rethrow_exception(coordinatorFailure);
    if(!abort)TaskAccess::poll(control);
    for(const auto &job:jobs)if(!abort&&!job->observed&&job->failure&&!cancelled.load()&&!job->cancellation->stopped())try{std::rethrow_exception(job->failure);}
    catch(const Trap &e){if(e.code=="E_MEMORY"||e.code=="E_LIMIT"||e.code=="E_TIMEOUT"||e.code=="E_CANCELLED")throw;}
    catch(const std::bad_alloc &){throw;}catch(...){/* Select an ordinary failure by spawn order below. */}
    for(const auto &job:jobs)if(!abort&&!job->observed&&job->failure&&!cancelled.load()&&!job->cancellation->stopped())std::rethrow_exception(job->failure);
  }
};
TaskGroup::TaskGroup(size_t workers,size_t maximumTasks,TaskExternalLimits externalLimits,bool sourceFileReadFailures){impl=hostOperation({},[&]{
  if(workers<1||workers>16||maximumTasks<1||maximumTasks>65536)throw Trap("E_RANGE","task group requires1..16 workers and1..65536 task slots",0);
  if(!validTaskExternalLimits(externalLimits))throw Trap("E_RANGE","invalid external kernel limits",0);
  return std::make_shared<Impl>(workers,maximumTasks,externalLimits,sourceFileReadFailures);
});}
TaskGroup::~TaskGroup(){try{impl->drain(true);}catch(...){/* Destruction cannot replace an active exception. */}}
size_t TaskGroup::taskIndex(const Ticket &ticket)const{
  if(ticket.owner.lock()!=impl)throw Trap("E_TASK_SCOPE","task belongs to another or ended group",0);
  std::lock_guard lock(impl->mutex);if(ticket.index>=impl->jobs.size())throw Trap("E_TASK_SCOPE","invalid task ticket",0);impl->scopeAccess(impl->jobs[ticket.index]->memberScope);return ticket.index;
}
size_t TaskGroup::channelIndex(const Channel &channel)const{
  if(channel.owner.lock()!=impl)throw Trap("E_TASK_SCOPE","channel belongs to another or ended group",0);
  std::lock_guard lock(impl->mutex);if(impl->finished||channel.index>=impl->pipes.size())throw Trap("E_TASK_SCOPE","channel scope has ended",0);impl->scopeAccess(impl->pipes[channel.index]->scope);return channel.index;
}
size_t TaskGroup::scopeIndex(const Scope &scope)const{
  if(scope.owner.lock()!=impl)throw Trap("E_TASK_SCOPE","logical scope belongs to another or ended group",0);
  std::lock_guard lock(impl->mutex);if(scope.index>=impl->regions.size()||impl->regions[scope.index]->closed)throw Trap("E_TASK_SCOPE","logical scope has ended",0);return scope.index;
}
TaskGroup::Scope TaskGroup::currentScopeOrEmpty()const{
  impl->require();std::lock_guard lock(impl->mutex);
  if(activeTaskState!=impl.get()||activeTaskIndex>=impl->jobs.size()||impl->jobs[activeTaskIndex]->scope==none)return {};
  return Scope(impl,impl->jobs[activeTaskIndex]->scope);
}
TaskGroup::Scope TaskGroup::currentScope()const{auto scope=currentScopeOrEmpty();if(scope.empty())throw Trap("E_TASK_SCOPE","no current logical task scope",0);return scope;}
void TaskGroup::enableResourceRegions(){
  impl->require(true);auto resources=std::make_unique<ResourceRegion>(ResourceRegionFamily::Native);
  std::lock_guard lock(impl->mutex);
  if(impl->resourceRoot||!impl->jobs.empty()||impl->sealed||impl->finished)throw Trap("E_TASK_SCOPE","resource regions must be enabled once before spawning tasks",0);
  impl->resourceRoot=std::move(resources);
}
ResourceRegionAuthority TaskGroup::resourceAuthority()const{
  return hostOperation({},[&]{
    impl->require();std::lock_guard lock(impl->mutex);
    if(!impl->resourceRoot||impl->finished)throw Trap("E_TASK_SCOPE","logical resource authority is unavailable",0);
    if(activeTaskState==impl.get()&&activeTaskIndex<impl->jobs.size()){
      auto scope=impl->jobs[activeTaskIndex]->scope;
      if(scope!=none){impl->scopeAccess(scope);return impl->regions[scope]->resources->authority();}
    }
    return impl->resourceRoot->authority();
  });
}

void TaskGroup::requireScope(const Scope &scope)const{impl->require();auto index=scopeIndex(scope);std::lock_guard lock(impl->mutex);impl->scopeAccess(index);}
bool TaskGroup::scopeContains(const Scope &ancestor,const Scope &descendant)const{
  impl->require();auto a=scopeIndex(ancestor),d=scopeIndex(descendant);std::lock_guard lock(impl->mutex);return impl->within(a,d);
}
TaskGroup::Scope TaskGroup::openScope(size_t workers){
  return hostOperation({},[&]{
    impl->require();if(workers<1||workers>16)throw Trap("E_RANGE","logical task scope requires1..16 workers",0);
    auto scope=std::make_unique<Impl::Region>();std::lock_guard lock(impl->mutex);
    if(activeTaskState!=impl.get()||activeTaskIndex>=impl->jobs.size())throw Trap("E_TASK_SCOPE","logical scope requires a running task",0);
    if(impl->regions.size()>=1024)throw Trap("E_LIMIT","logical task scope count exceeds1024",0);
    auto &job=*impl->jobs[activeTaskIndex];scope->parent=job.scope;scope->owner=activeTaskIndex;scope->limit=workers;
    if(job.scope!=none){impl->scopeAccess(job.scope);scope->depth=impl->regions[job.scope]->depth+1;}
    if(scope->depth>256)throw Trap("E_LIMIT","logical task scope depth exceeds256",0);
    if(impl->resourceRoot)scope->resources=std::make_unique<ResourceRegion>(job.scope==none?
      impl->resourceRoot->child():impl->regions[job.scope]->resources->child());
    // Reserve every growing adjacency list before publishing any new identity.
    if(job.ownedScopes.size()==job.ownedScopes.capacity())job.ownedScopes.reserve(std::max(size_t(1),job.ownedScopes.size()*2));
    if(job.scope!=none){auto &children=impl->regions[job.scope]->children;if(children.size()==children.capacity())children.reserve(std::max(size_t(1),children.size()*2));}
    scope->active=1;size_t index=impl->regions.size();job.ownedScopes.push_back(index);impl->regions.push_back(std::move(scope));
    if(job.scope!=none){auto &parent=*impl->regions[job.scope];++parent.nested;parent.children.push_back(index);}job.scope=index;return Scope(impl,index);
  });
}
TaskGroup::Awaiter TaskGroup::leaveScope(const Scope &scope,bool cancelChildren){return Awaiter(Awaiter::DrainScope,this,scopeIndex(scope),Value(cancelChildren,true));}
TaskGroup::Ticket TaskGroup::spawn(Factory factory,Value input,Value captures){
  size_t scope=none;{std::lock_guard lock(impl->mutex);if(activeTaskState==impl.get())scope=impl->jobs[activeTaskIndex]->scope;}
  return spawnIn(scope,factory,std::move(input),std::move(captures));
}
TaskGroup::Ticket TaskGroup::spawn(const Scope &scope,Factory factory,Value input,Value captures){return spawnIn(scopeIndex(scope),factory,std::move(input),std::move(captures));}
TaskGroup::Ticket TaskGroup::spawnWithContext(ContextFactory factory,const void *context,Value input,Value captures){
  size_t scope=none;{std::lock_guard lock(impl->mutex);if(activeTaskState==impl.get())scope=impl->jobs[activeTaskIndex]->scope;}
  return spawnIn(scope,nullptr,std::move(input),std::move(captures),factory,context);
}
TaskGroup::Ticket TaskGroup::spawnWithContext(const Scope &scope,ContextFactory factory,const void *context,Value input,Value captures){
  return spawnIn(scopeIndex(scope),nullptr,std::move(input),std::move(captures),factory,context);
}
TaskGroup::Ticket TaskGroup::spawnIn(size_t scope,Factory factory,Value input,Value captures,ContextFactory contextFactory,const void *context){
  return hostOperation({},[&]{
    impl->require();if(bool(factory)==bool(contextFactory))throw Trap("E_TASK_SCOPE","task factory is missing or ambiguous",0);auto targetScope=scope==none?Scope{}:Scope(impl,scope);taskValue(*this,input,targetScope);taskValue(*this,captures,targetScope);
    auto job=std::make_unique<Impl::Job>();job->group=this;job->cancellation=std::make_shared<task_detail::Cancellation>();
    if(activeTaskState==impl.get()){
      std::lock_guard lock(impl->mutex);job->cancellation->parent=impl->jobs[activeTaskIndex]->cancellation;
      job->cancellation->depth=job->cancellation->parent->depth+1;
      if(job->cancellation->depth>256)throw Trap("E_LIMIT","task nesting exceeds256",0);
    }
    auto body=contextFactory?contextFactory(*this,std::move(input),std::move(captures),context):factory(*this,std::move(input),std::move(captures));if(!body.handle)throw Trap("E_TASK_SCOPE","task factory returned no coroutine",0);
    job->body=std::exchange(body.handle,{});
    size_t index;
    {
      std::lock_guard lock(impl->mutex);
      if(impl->finished||(impl->sealed&&activeTaskState!=impl.get()))throw Trap("E_TASK_SCOPE","task group is sealed",0);
      if(impl->jobs.size()>=impl->ready.size())throw Trap("E_LIMIT","task group slot limit exceeded",0);
      impl->scopeAccess(scope);job->scope=job->memberScope=scope;
      index=impl->jobs.size();if(scope!=none){impl->regions[scope]->members.push_back(index);++impl->regions[scope]->pending;}
      impl->jobs.push_back(std::move(job));
      bool metadata=false;
#ifdef NEX_TASK_PROFILE_ENABLED
      metadata|=bool(impl->profileCollector);
#endif
#ifdef NEX_TASK_DEBUG_ENABLED
      metadata|=impl->debugEnabled;
#endif
      if(!metadata){impl->enqueue(index);return Ticket(impl,index);}
    }
    // The admitted job cannot run until all optional metadata is registered
    // outside the kernel mutex. Cancellation may mark it before this commit.
#ifdef NEX_TASK_PROFILE_ENABLED
    auto profileTask=impl->profileCollector?impl->profileCollector->taskFromCurrent():TaskProfileTask{};
    TaskProfileTransaction profileCommit(impl->profileCollector);
#endif
#ifdef NEX_TASK_DEBUG_ENABLED
    auto debugTask=impl->debugEnabled?taskDebugCreateTask():TaskDebugTask{};
#endif
    {std::lock_guard lock(impl->mutex);
#ifdef NEX_TASK_PROFILE_ENABLED
      impl->jobs[index]->profileTask=std::move(profileTask);
#endif
#ifdef NEX_TASK_DEBUG_ENABLED
      impl->jobs[index]->debugTask=debugTask;
#endif
      impl->enqueue(index);}
    return Ticket(impl,index);
  });
}
Value TaskGroup::join(const Ticket &ticket){
  impl->requireContext(true);auto index=taskIndex(ticket);std::exception_ptr coordinatorFailure;
  for(;;){
#ifdef NEX_TASK_PROFILE_ENABLED
    TaskProfileTransaction profileTick(impl->profileCollector);
#endif
    {std::lock_guard lock(impl->mutex);Impl::preferFailure(coordinatorFailure,impl->sourceFileReadFatal);}
    if(!coordinatorFailure)try{TaskAccess::poll(impl->control);}catch(...){coordinatorFailure=std::current_exception();impl->cancelled=true;std::lock_guard lock(impl->mutex);impl->selectFileReadFatal(coordinatorFailure);}
    std::unique_lock lock(impl->mutex);impl->interrupt();auto &job=*impl->jobs[index];
    if(job.done){job.observed=true;auto selected=impl->sourceFileReadFatal;Impl::preferFailure(selected,coordinatorFailure);Impl::preferFailure(selected,job.failure);Impl::preferFailure(selected,job.externalFatal);if(selected)std::rethrow_exception(selected);return job.result;}
    impl->changed.wait_for(lock,std::chrono::milliseconds(2));
  }
}
TaskGroup::Awaiter TaskGroup::await(const Ticket &ticket){return Awaiter(Awaiter::Future,this,taskIndex(ticket));}
TaskGroup::Awaiter TaskGroup::yield(){return Awaiter(Awaiter::Yield,this);}
TaskGroup::Awaiter TaskGroup::send(const Channel &channel,Value value){return Awaiter(Awaiter::Send,this,channelIndex(channel),std::move(value));}
TaskGroup::Awaiter TaskGroup::receive(const Channel &channel){return Awaiter(Awaiter::Receive,this,channelIndex(channel));}
bool TaskGroup::Awaiter::await_suspend(TaskBody::Handle handle){
  const bool suspended=hostOperation(location,[&]{
  auto impl=group->impl;impl->require();
  {
    std::lock_guard lock(impl->mutex);
    if(activeTaskState!=impl.get()||activeTaskIndex>=impl->jobs.size()||impl->jobs[activeTaskIndex]->body!=handle)throw Trap("E_TASK_SCOPE","foreign coroutine cannot use this scheduler",0);
    impl->jobs[activeTaskIndex]->location=location;
  }
  return impl->suspend(activeTaskIndex,kind,target,std::move(value));
  });
#ifdef NEX_TASK_DEBUG_ENABLED
  if(suspended)taskDebugPublishPark();else taskDebugInvalidate(taskDebugCurrentTask());
#endif
  return suspended;
}
TaskEvent TaskGroup::Awaiter::await_resume(){
#ifdef NEX_TASK_DEBUG_ENABLED
  taskDebugInvalidate(taskDebugCurrentTask());
#endif
  return hostOperation(location,[&]() -> TaskEvent {
  auto impl=group->impl;impl->require();std::lock_guard lock(impl->mutex);
  if(activeTaskState!=impl.get()||activeTaskIndex>=impl->jobs.size())throw Trap("E_TASK_SCOPE","awaiter resumed outside its task",0);
  if(kind==DrainScope){auto &scope=*impl->regions[target];if(!scope.closed)throw Trap("E_TASK_STATE","logical scope resumed before draining",0);if(scope.failure)std::rethrow_exception(scope.failure);return {};}
  if(kind==Future){auto &job=*impl->jobs[target];if(!job.done)throw Trap("E_TASK_STATE","future resumed before completion",0);job.observed=true;if(job.failure)std::rethrow_exception(job.failure);return {true,job.result};}
  return std::move(impl->jobs[activeTaskIndex]->event);
  });
}
TaskGroup::Channel TaskGroup::channel(size_t capacity){
  size_t scope=none;{std::lock_guard lock(impl->mutex);if(activeTaskState==impl.get())scope=impl->jobs[activeTaskIndex]->scope;}
  return channelIn(scope,capacity);
}
TaskGroup::Channel TaskGroup::channel(const Scope &scope,size_t capacity){return channelIn(scopeIndex(scope),capacity);}
TaskGroup::Channel TaskGroup::channelIn(size_t scope,size_t capacity){
  return hostOperation({},[&]{impl->require();
    if(capacity>65536)throw Trap("E_RANGE","channel capacity exceeds65536",0);
    auto pipe=std::make_unique<Impl::Pipe>(capacity);std::lock_guard lock(impl->mutex);
    if(impl->finished||(impl->sealed&&activeTaskState!=impl.get()))throw Trap("E_TASK_SCOPE","channel scope is sealed",0);
    if(impl->pipes.size()>=1024||capacity>65536-impl->reservedSlots)throw Trap("E_LIMIT","channel slot limit exceeded",0);
    impl->scopeAccess(scope);pipe->scope=scope;
    size_t index=impl->pipes.size();if(scope!=none)impl->regions[scope]->pipes.push_back(index);
    impl->pipes.push_back(std::move(pipe));impl->reservedSlots+=capacity;return Channel(impl,index);
  });
}
bool TaskGroup::close(const Channel &channel){
#ifdef NEX_TASK_PROFILE_ENABLED
  TaskProfileTransaction profileTransaction(impl->profileCollector);
#endif
  impl->require();auto index=channelIndex(channel);Impl::ValueFlush flush{impl.get()};std::lock_guard lock(impl->mutex);
  if(impl->pipes[index]->closed)return false;impl->closePipe(index);return true;
}
bool TaskGroup::cancel(const Ticket &ticket){
#ifdef NEX_TASK_PROFILE_ENABLED
  TaskProfileTransaction profileTransaction(impl->profileCollector);
#endif
  impl->require();auto index=taskIndex(ticket);Impl::ValueFlush flush{impl.get()};std::lock_guard lock(impl->mutex);auto &job=*impl->jobs[index];if(job.done)return false;
  bool changed=!job.cancellation->cancelled.exchange(true);impl->interrupt();impl->changed.notify_all();return changed;
}
void TaskGroup::cancel(){
#ifdef NEX_TASK_PROFILE_ENABLED
  TaskProfileTransaction profileTransaction(impl->profileCollector);
#endif
  impl->require();Impl::ValueFlush flush{impl.get()};std::lock_guard lock(impl->mutex);impl->cancelled=true;impl->interrupt();impl->changed.notify_all();}
namespace {
struct ControlledExternalOperation final:TaskExternalOperation {
  std::shared_ptr<TaskExternalOperation> operation;TaskExternalControl request;size_t reservation,maximumResultBytes;
  ControlledExternalOperation(std::shared_ptr<TaskExternalOperation> operation,TaskExternalControl request,size_t reservation,size_t maximumResultBytes):operation(std::move(operation)),request(std::move(request)),reservation(reservation),maximumResultBytes(maximumResultBytes){}
  TaskExternalResult run(const TaskExternalControl &stop)override{
    TaskExternalControl control([&]{stop.checkpoint();request.checkpoint();});control.checkpoint();auto result=operation->run(control);validateTaskExternalResult(result,reservation,maximumResultBytes);control.checkpoint();return result;
  }
};
}
TaskExternalTicket TaskGroup::submitExternal(std::shared_ptr<TaskExternalOperation> operation,size_t reservation){
  return hostOperation({},[&]{
    impl->require();
    if(!operation)throw Trap("E_TASK_STATE","external operation is absent",0);
    if(activeTaskState!=impl.get())throw Trap("E_TASK_SCOPE","external admission requires a running task",0);
    std::call_once(impl->externalInit,[&]{
      std::weak_ptr<Impl> weak=impl;
      auto pool=std::make_unique<TaskExternalPool>(impl->externalLimits,[weak](const TaskExternalTicket &ticket){
        if(auto state=weak.lock()){
#ifdef NEX_TASK_PROFILE_ENABLED
          TaskProfileTransaction profileTransaction(state->profileCollector);
#endif
          std::lock_guard lock(state->mutex);
          if(ticket.owner()>=state->jobs.size())std::terminate();auto &job=*state->jobs[ticket.owner()];
          for(size_t i=0;i<job.external.size();++i){auto &entry=job.external[i];if(entry.ticket==ticket){
            if(entry.physical||!job.externalPending)std::terminate();entry.physical=true;--job.externalPending;
            if(state->canRetireExternal(ticket.owner(),entry))state->externalRetirementReady=true;
            if(!job.finishing&&job.wait==Impl::WaitExternal&&job.target==i)state->wake(ticket.owner());
            state->changed.notify_all();return;
          }}
          std::terminate();
        }
      });
      std::lock_guard lock(impl->mutex);impl->externalPool=std::move(pool);
    });
    auto control=TaskAccess::externalControl(impl->control,impl->jobs[activeTaskIndex]->cancellation);
    control.checkpoint();auto wrapped=std::make_shared<ControlledExternalOperation>(std::move(operation),std::move(control),reservation,impl->externalLimits.maximumResultBytes);
    std::lock_guard lock(impl->mutex);auto &job=*impl->jobs[activeTaskIndex];
    if(impl->finished||impl->cancelled.load()||job.cancellation->stopped())throw Trap("E_CANCELLED","external admission was cancelled",0);
    size_t reusable=job.external.size();for(size_t i=0;i<job.external.size();++i)if(job.external[i].consumed){reusable=i;break;}
    if(reusable==job.external.size()){
      if(job.external.size()>=impl->externalLimits.tickets)throw Trap("E_LIMIT","external task ticket limit exceeded",0);
      if(job.external.size()==job.external.capacity())job.external.reserve(std::min(impl->externalLimits.tickets,std::max(size_t(1),job.external.size()*2)));
    }
    // Default pool control has no callback. The retained request checkpoint is
    // invoked by ControlledExternalOperation only outside scheduler/kernel locks.
    auto ticket=impl->externalPool->submit(activeTaskIndex,wrapped,reservation);
    if(reusable<job.external.size())job.external[reusable]={ticket,job.scope};else job.external.push_back({ticket,job.scope});
    if(job.scope!=none)++impl->regions[job.scope]->externalPending;
    ++job.externalPending;return ticket;
  });
}
TaskGroup::ExternalAwaiter TaskGroup::awaitExternal(const TaskExternalTicket &ticket){return ExternalAwaiter(this,ticket);}
bool TaskGroup::ExternalAwaiter::await_suspend(TaskBody::Handle handle){
  const bool suspended=hostOperation(location,[&]{
    auto state=group->impl;state->require();
#ifdef NEX_TASK_PROFILE_ENABLED
    TaskProfileTransaction profileTransaction(state->profileCollector);
#endif
    std::lock_guard lock(state->mutex);
    if(activeTaskState!=state.get()||activeTaskIndex>=state->jobs.size()||state->jobs[activeTaskIndex]->body!=handle||ticket.owner()!=activeTaskIndex)
      throw Trap("E_TASK_SCOPE","external ticket belongs to another task or group",0);
    auto &job=*state->jobs[activeTaskIndex];
    for(size_t i=0;i<job.external.size();++i)if(job.external[i].ticket==ticket){
      auto &entry=job.external[i];if(entry.consumed)throw Trap("E_TASK_STATE","external ticket was already consumed",0);
      job.location=location;if(entry.physical)return false;
      job.wait=Impl::WaitExternal;job.target=i;
#ifdef NEX_TASK_DEBUG_ENABLED
      taskDebugKernelState(job.debugTask,TaskDebugState::Blocked,TaskDebugWait::External);
#endif
#ifdef NEX_TASK_PROFILE_ENABLED
      if(state->profileCollector)job.profileWaitAt=state->profileNow();
#endif
      return true;
    }
    throw Trap("E_TASK_SCOPE","external ticket belongs to another or ended group",0);
  });
#ifdef NEX_TASK_DEBUG_ENABLED
  if(suspended)taskDebugPublishPark();else taskDebugInvalidate(taskDebugCurrentTask());
#endif
  return suspended;
}
TaskExternalResult TaskGroup::ExternalAwaiter::await_resume(){
#ifdef NEX_TASK_DEBUG_ENABLED
  taskDebugInvalidate(taskDebugCurrentTask());
#endif
  return hostOperation(location,[&]{
    auto state=group->impl;state->require();
#ifdef NEX_TASK_PROFILE_ENABLED
    TaskProfileTransaction profileTransaction(state->profileCollector);
#endif
    {std::lock_guard lock(state->mutex);
      if(activeTaskState!=state.get()||activeTaskIndex>=state->jobs.size()||ticket.owner()!=activeTaskIndex)throw Trap("E_TASK_SCOPE","external completion resumed outside its owner",0);
      auto &job=*state->jobs[activeTaskIndex];bool found=false;
      for(auto &entry:job.external)if(entry.ticket==ticket){
        if(entry.consumed||!entry.physical)throw Trap("E_TASK_STATE","external completion is absent or already consumed",0);
        entry.consumed=true;found=true;break;
      }
      if(!found)throw Trap("E_TASK_SCOPE","external completion belongs to another or ended group",0);
    }
    TaskExternalResult result;std::exception_ptr failure;
    try{result=state->externalPool->take(ticket);}
    catch(const DataError &error){try{throw Trap(error.code,error.what(),location);}catch(...){failure=std::current_exception();}}
    catch(...){failure=std::current_exception();}
    {
      std::lock_guard lock(state->mutex);auto &job=*state->jobs[activeTaskIndex];
      state->selectFileReadFatal(failure);
      for(auto &entry:job.external)if(entry.ticket==ticket){if(entry.scope!=none){auto &scope=*state->regions[entry.scope];if(!scope.externalPending)std::terminate();--scope.externalPending;state->closeRegion(entry.scope);}break;}
    }
    if(failure)std::rethrow_exception(failure);return result;
  });
}
TaskExternalStats TaskGroup::externalStats()const{std::lock_guard lock(impl->mutex);return impl->externalPool?impl->externalPool->stats():TaskExternalStats{};}
void TaskGroup::failFileRead(std::exception_ptr failure){
#ifdef NEX_TASK_PROFILE_ENABLED
  TaskProfileTransaction profileTransaction(impl->profileCollector);
#endif
  impl->requireContext();std::lock_guard lock(impl->mutex);impl->selectFileReadFatal(failure);}
void TaskGroup::finish(){impl->requireContext(true);impl->drain(false);}
