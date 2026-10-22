// Included inside namespace nexrt after the request/parallel runtime internals.
#ifndef NEX_STRUCTURED_WORKERS
#error NEX_ASYNC_TASKS requires NEX_STRUCTURED_WORKERS
#endif
namespace {
thread_local const void *activeTaskState=nullptr;
thread_local size_t activeTaskIndex=static_cast<size_t>(-1);
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
  enum Wait { None, Future, Send, Receive, ScopeDrain };
  struct Job {
    TaskBody::Handle body;Value result,pending;TaskGroup *group=nullptr;std::weak_ptr<Data> capability;SourceLocation location;TaskEvent event;
    std::exception_ptr failure;
    std::shared_ptr<task_detail::Cancellation> cancellation;
    Wait wait=None;size_t target=none,previous=none,next=none,head=none,tail=none;
    size_t scope=none,memberScope=none;
    std::vector<size_t> ownedScopes;
    bool running=false,queued=false,again=false,done=false,observed=false,finishing=false,cleanupDone=false;
    ~Job(){if(body)body.destroy();}
  };
  struct Pipe {
    std::vector<std::optional<Value>> buffer;size_t start=0,count=0;
    size_t sendHead=none,sendTail=none,receiveHead=none,receiveTail=none;
    bool closed=false;size_t scope=none;std::weak_ptr<Data> capability;
    explicit Pipe(size_t capacity):buffer(capacity){}
    void push(Value value){buffer[(start+count)%buffer.size()]=std::move(value);++count;}
    Value pop(){auto value=std::move(*buffer[start]);buffer[start].reset();start=(start+1)%buffer.size();--count;return value;}
  };
  struct Region {
    size_t parent=none,owner=none,limit=1,active=0,pending=0,nested=0,depth=1,head=none,tail=none;
    bool closing=false,closed=false,abort=false;
    std::vector<size_t> members,pipes,children;
    std::exception_ptr failure;std::weak_ptr<Data> capability;
  };
  std::vector<std::unique_ptr<Region>> regions;
  std::vector<uint64_t> graphSeen;std::vector<size_t> graphWork;uint64_t graphEpoch=0;
  std::shared_ptr<TaskAccess::Control> control;
  std::thread::id coordinator=std::this_thread::get_id();
  std::mutex mutex;std::condition_variable changed;
  std::vector<std::unique_ptr<Job>> jobs;
  std::vector<std::unique_ptr<Pipe>> pipes;
  std::vector<size_t> ready;size_t readyStart=0,readyCount=0,completed=0,reservedSlots=0;
  std::atomic<bool> cancelled{false};
  bool started=false,stop=false,sealed=false,finished=false;
  std::vector<std::jthread> threads;
  Impl(size_t workers,size_t maximum):control(TaskAccess::control()),ready(maximum){
    if(workers<1||workers>16||maximum<1||maximum>65536)throw Trap("E_RANGE","task group requires1..16 workers and1..65536 task slots",0);
    jobs.reserve(maximum);pipes.reserve(1024);regions.reserve(1024);graphSeen.resize(maximum+1024);graphWork.reserve(maximum+1024);threads.reserve(workers);
    try{
      for(size_t i=0;i<workers;++i)threads.emplace_back([this]{work();});
      {std::lock_guard lock(mutex);started=true;}changed.notify_all();
    }catch(...){
      {std::lock_guard lock(mutex);stop=true;}changed.notify_all();
      for(auto &thread:threads)thread.join();throw;
    }
  }
  void require(bool coordinatorOnly=false){
    bool worker=activeTaskState==this;
    if((!worker&&std::this_thread::get_id()!=coordinator)||(coordinatorOnly&&worker)||!TaskAccess::same(control))
      throw Trap("E_TASK_SCOPE","task operation belongs to another scope or thread",0);
    TaskAccess::poll(control);
    if(cancelled.load()&&worker)throw Trap("E_CANCELLED","task group was cancelled",0);
  }
  void enqueue(size_t index){
    auto &job=*jobs[index];if(job.done||job.finishing||job.queued)return;
    if(job.running){job.again=true;return;}
    ready[(readyStart+readyCount)%ready.size()]=index;++readyCount;job.queued=true;changed.notify_all();
  }
  std::pair<size_t*,size_t*> ends(Job &job){
    if(job.wait==Future)return {&jobs[job.target]->head,&jobs[job.target]->tail};
    if(job.wait==ScopeDrain)return {&regions[job.target]->head,&regions[job.target]->tail};
    auto &pipe=*pipes[job.target];
    return job.wait==Send?std::pair{&pipe.sendHead,&pipe.sendTail}:std::pair{&pipe.receiveHead,&pipe.receiveTail};
  }
  void unlink(size_t index){
    auto &job=*jobs[index];if(job.wait==None)return;auto [head,tail]=ends(job);
    if(job.previous==none)*head=job.next;else jobs[job.previous]->next=job.next;
    if(job.next==none)*tail=job.previous;else jobs[job.next]->previous=job.previous;
    job.wait=None;job.previous=job.next=job.target=none;
  }
  void link(size_t index,Wait wait,size_t target){
    auto &job=*jobs[index];job.wait=wait;job.target=target;auto [head,tail]=ends(job);
    job.previous=*tail;job.next=none;
    if(*tail==none)*head=index;else jobs[*tail]->next=index;*tail=index;
  }
  void wake(size_t index){unlink(index);enqueue(index);}
  void interrupt(){
    const bool global=cancelled.load()||!TaskAccess::healthy(control);
    for(size_t i=0;i<jobs.size();++i){auto &job=*jobs[i];if(!job.done&&job.wait!=None&&(global||job.cancellation->stopped())){job.pending={};wake(i);}}
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
  static void preferFailure(std::exception_ptr &selected,const std::exception_ptr &candidate){
    if(candidate&&(!selected||(!resourceFailure(selected)&&resourceFailure(candidate))))selected=candidate;
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
    interrupt();changed.notify_all();
  }
  void closePipe(size_t index){
    auto &pipe=*pipes[index];if(pipe.closed)return;pipe.closed=true;
    while(pipe.sendHead!=none){auto sender=pipe.sendHead;jobs[sender]->pending={};jobs[sender]->event={};wake(sender);}
    while(pipe.receiveHead!=none){auto receiver=pipe.receiveHead;jobs[receiver]->event=pipe.count?TaskEvent{true,pipe.pop()}:TaskEvent{};wake(receiver);}
  }
  void closeRegion(size_t index){
    auto &scope=*regions[index];if(scope.closed||!scope.closing||scope.pending||scope.nested)return;
    scope.closed=true;
    for(auto member:scope.members){auto &job=*jobs[member];
      if(!scope.abort&&!job.observed&&!job.cancellation->stopped())preferFailure(scope.failure,job.failure);
      job.observed=true;job.result={};job.capability.reset();
    }
    scope.capability.reset();
    for(auto pipe:scope.pipes){closePipe(pipe);auto &state=*pipes[pipe];reservedSlots-=state.buffer.size();std::vector<std::optional<Value>>().swap(state.buffer);state.count=state.start=0;}
    auto &owner=*jobs[scope.owner];
    if(owner.scope==index){if(owner.running){if(!scope.active)throw Trap("E_TASK_STATE","logical task lease is unbalanced",0);--scope.active;}owner.scope=scope.parent;}
    if(scope.active)throw Trap("E_TASK_STATE","closed logical task scope has active workers",0);
    if(owner.finishing)preferFailure(owner.failure,scope.failure);
    while(scope.head!=none)wake(scope.head);
    if(scope.parent!=none){auto &parent=*regions[scope.parent];if(!parent.nested)throw Trap("E_TASK_STATE","logical nested scope count is unbalanced",0);--parent.nested;closeRegion(scope.parent);}
    tryComplete(scope.owner);changed.notify_all();
  }
  void tryComplete(size_t index){
    auto &job=*jobs[index];if(!job.finishing||!job.cleanupDone)return;
    for(auto scope:job.ownedScopes)if(!regions[scope]->closed)return;
    if(job.failure)job.result={};job.finishing=false;job.done=true;++completed;
    while(job.head!=none)wake(job.head);
    if(job.memberScope!=none){auto &scope=*regions[job.memberScope];if(!scope.pending)throw Trap("E_TASK_STATE","logical task count is unbalanced",0);--scope.pending;closeRegion(job.memberScope);}
    changed.notify_all();
  }
  void beginComplete(size_t index,std::exception_ptr failure){
    auto &job=*jobs[index];unlink(index);job.running=false;job.again=false;job.finishing=true;job.failure=std::move(failure);
    if(!job.failure)job.result=std::move(job.body.promise().value);
    size_t outer=none;
    for(auto scope:job.ownedScopes)if(!regions[scope]->closed){if(outer==none)outer=scope;regions[scope]->closing=true;regions[scope]->abort=bool(job.failure);}
    if(!job.failure&&outer!=none&&scopeCycle(index,outer)){
      try{throw Trap("E_TASK_CYCLE","cyclic logical scope drain",0);}catch(...){job.failure=std::current_exception();}
      for(auto scope:job.ownedScopes)if(!regions[scope]->closed)regions[scope]->abort=true;
    }
    if(job.failure&&outer!=none)cancelRegion(outer);
    for(auto it=job.ownedScopes.rbegin();it!=job.ownedScopes.rend();++it)closeRegion(*it);
  }
  void lease(size_t scope,int delta){
    for(auto next=scope;next!=none;next=regions[next]->parent){auto &region=*regions[next];if(delta>0)++region.active;else{if(!region.active)throw Trap("E_TASK_STATE","logical task worker lease is unbalanced",0);--region.active;}}
  }
  size_t runnable(){
    size_t count=readyCount;
    while(count--){
      auto index=ready[readyStart];readyStart=(readyStart+1)%ready.size();--readyCount;auto &job=*jobs[index];bool allowed=true;
      for(auto next=job.scope;next!=none;next=regions[next]->parent)if(regions[next]->active>=regions[next]->limit){allowed=false;break;}
      if(allowed){job.queued=false;job.running=true;job.again=false;lease(job.scope,1);return index;}
      ready[(readyStart+readyCount)%ready.size()]=index;++readyCount;
    }
    return none;
  }
  void work(){
    for(;;){
      size_t index;Job *runningJob;
      {
        std::unique_lock lock(mutex);changed.wait(lock,[&]{return started||stop;});
        while(!stop){interrupt();index=runnable();if(index!=none)break;changed.wait_for(lock,std::chrono::milliseconds(2));}
        if(stop)return;
        runningJob=jobs[index].get();
      }
      auto previousState=activeTaskState;auto previousIndex=activeTaskIndex;
      activeTaskState=this;activeTaskIndex=index;
      std::exception_ptr failure;
      try{TaskAccess::resume(control,cancelled,runningJob->cancellation,runningJob->body,*runningJob->group,runningJob->memberScope==none?Scope{}:Scope(runningJob->group->impl,runningJob->memberScope),runningJob->location);}
      catch(...){failure=std::current_exception();}
      activeTaskState=previousState;activeTaskIndex=previousIndex;
      TaskBody::Handle destroy;
      {
        std::lock_guard lock(mutex);auto &job=*jobs[index];lease(job.scope,-1);job.running=false;
        if(failure||job.body.done()){beginComplete(index,std::move(failure));destroy=std::exchange(job.body,{});}
        else if(job.again)enqueue(index);
        else if(job.wait==None){
          try{throw Trap("E_TASK_STATE","coroutine suspended outside its task scheduler",0);}catch(...){beginComplete(index,std::current_exception());destroy=std::exchange(job.body,{});}
        }
        changed.notify_all();
      }
      // Destroy all retained native frames before publishing completion, outside
      // the scheduler mutex so owned-value/profile destructors cannot deadlock it.
      if(destroy){destroy.destroy();std::lock_guard lock(mutex);jobs[index]->cleanupDone=true;tryComplete(index);}
    }
  }
  bool suspend(size_t index,Awaiter::Kind kind,size_t target,Value value){
    require();
    if(kind==Awaiter::Send){Scope targetScope;TaskGroup *group;{std::lock_guard lock(mutex);if(target>=pipes.size()||index>=jobs.size())throw Trap("E_TASK_SCOPE","invalid channel/task",0);group=jobs[index]->group;if(pipes[target]->scope!=none)targetScope=Scope(group->impl,pipes[target]->scope);}taskValue(*group,value,targetScope);}
    std::lock_guard lock(mutex);
    if(index>=jobs.size()||activeTaskState!=this||activeTaskIndex!=index)throw Trap("E_TASK_SCOPE","awaiter belongs to another task",0);
    auto &job=*jobs[index];job.event={};
    if(kind==Awaiter::Yield){job.again=true;return true;}
    if(kind==Awaiter::DrainScope){
      if(target>=regions.size()||regions[target]->closed||regions[target]->owner!=index||job.scope!=target)throw Trap("E_TASK_SCOPE","logical scope exit must belong to its innermost owner",0);
      auto &scope=*regions[target];
      if(!value.scalar&&scopeCycle(index,target))throw Trap("E_TASK_CYCLE","cyclic logical scope drain",0);
      scope.closing=true;scope.abort=bool(value.scalar);
      if(scope.abort)cancelRegion(target);
      if(!scope.pending&&!scope.nested){closeRegion(target);return false;}
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
      if(pipe.receiveHead!=none){size_t receiver=pipe.receiveHead;jobs[receiver]->event={true,std::move(value)};wake(receiver);job.event.present=true;return false;}
      if(pipe.count<pipe.buffer.size()){pipe.push(std::move(value));job.event.present=true;return false;}
      job.pending=std::move(value);link(index,Send,target);return true;
    }
    if(pipe.count){
      job.event={true,pipe.pop()};
      if(pipe.sendHead!=none){auto sender=pipe.sendHead;pipe.push(std::move(jobs[sender]->pending));jobs[sender]->pending={};jobs[sender]->event.present=true;wake(sender);}
      return false;
    }
    if(pipe.sendHead!=none){auto sender=pipe.sendHead;job.event={true,std::move(jobs[sender]->pending)};jobs[sender]->pending={};jobs[sender]->event.present=true;wake(sender);return false;}
    if(pipe.closed)return false;
    link(index,Receive,target);return true;
  }
  void drain(bool abort){
    {
      std::lock_guard lock(mutex);if(finished)return;sealed=true;
      if(abort)cancelled=true;interrupt();changed.notify_all();
    }
    std::exception_ptr coordinatorFailure;
    for(;;){
      std::unique_lock lock(mutex);if(completed==jobs.size())break;
      lock.unlock();
      if(!abort&&!coordinatorFailure)try{TaskAccess::poll(control);}catch(...){coordinatorFailure=std::current_exception();}
      lock.lock();interrupt();changed.wait_for(lock,std::chrono::milliseconds(2));
    }
    {std::lock_guard lock(mutex);stop=true;}changed.notify_all();
    for(auto &thread:threads)thread.join();
    {std::lock_guard lock(mutex);finished=true;}
    // Workers are joined. Frame destructors and profiling hooks run outside the
    // scheduler lock; they cannot deadlock by acquiring another runtime lock.
    for(auto &job:jobs){if(job->body){job->body.destroy();job->body={};}job->pending={};}
    pipes.clear();
    if(coordinatorFailure)std::rethrow_exception(coordinatorFailure);
    if(!abort)TaskAccess::poll(control);
    for(const auto &job:jobs)if(!abort&&!job->observed&&job->failure&&!cancelled.load()&&!job->cancellation->stopped())try{std::rethrow_exception(job->failure);}
    catch(const Trap &e){if(e.code=="E_MEMORY"||e.code=="E_LIMIT"||e.code=="E_TIMEOUT"||e.code=="E_CANCELLED")throw;}
    catch(const std::bad_alloc &){throw;}catch(...){/* Select an ordinary failure by spawn order below. */}
    for(const auto &job:jobs)if(!abort&&!job->observed&&job->failure&&!cancelled.load()&&!job->cancellation->stopped())std::rethrow_exception(job->failure);
  }
};
TaskGroup::TaskGroup(size_t workers,size_t maximumTasks){impl=hostOperation({},[&]{
  if(workers<1||workers>16||maximumTasks<1||maximumTasks>65536)throw Trap("E_RANGE","task group requires1..16 workers and1..65536 task slots",0);
  return std::make_shared<Impl>(workers,maximumTasks);
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
TaskGroup::Ticket TaskGroup::spawnIn(size_t scope,Factory factory,Value input,Value captures){
  return hostOperation({},[&]{
    impl->require();if(!factory)throw Trap("E_TASK_SCOPE","task factory is missing",0);auto targetScope=scope==none?Scope{}:Scope(impl,scope);taskValue(*this,input,targetScope);taskValue(*this,captures,targetScope);
    auto job=std::make_unique<Impl::Job>();job->group=this;job->cancellation=std::make_shared<task_detail::Cancellation>();
    if(activeTaskState==impl.get()){
      std::lock_guard lock(impl->mutex);job->cancellation->parent=impl->jobs[activeTaskIndex]->cancellation;
      job->cancellation->depth=job->cancellation->parent->depth+1;
      if(job->cancellation->depth>256)throw Trap("E_LIMIT","task nesting exceeds256",0);
    }
    auto body=factory(*this,std::move(input),std::move(captures));if(!body.handle)throw Trap("E_TASK_SCOPE","task factory returned no coroutine",0);
    job->body=std::exchange(body.handle,{});
    std::lock_guard lock(impl->mutex);
    if(impl->finished||(impl->sealed&&activeTaskState!=impl.get()))throw Trap("E_TASK_SCOPE","task group is sealed",0);
    if(impl->jobs.size()>=impl->ready.size())throw Trap("E_LIMIT","task group slot limit exceeded",0);
    impl->scopeAccess(scope);job->scope=job->memberScope=scope;
    size_t index=impl->jobs.size();if(scope!=none){impl->regions[scope]->members.push_back(index);++impl->regions[scope]->pending;}
    impl->jobs.push_back(std::move(job));impl->enqueue(index);return Ticket(impl,index);
  });
}
Value TaskGroup::join(const Ticket &ticket){
  impl->require(true);auto index=taskIndex(ticket);
  for(;;){
    TaskAccess::poll(impl->control);std::unique_lock lock(impl->mutex);auto &job=*impl->jobs[index];
    if(job.done){job.observed=true;if(job.failure)std::rethrow_exception(job.failure);return job.result;}
    impl->changed.wait_for(lock,std::chrono::milliseconds(2));
  }
}
TaskGroup::Awaiter TaskGroup::await(const Ticket &ticket){return Awaiter(Awaiter::Future,this,taskIndex(ticket));}
TaskGroup::Awaiter TaskGroup::yield(){return Awaiter(Awaiter::Yield,this);}
TaskGroup::Awaiter TaskGroup::send(const Channel &channel,Value value){return Awaiter(Awaiter::Send,this,channelIndex(channel),std::move(value));}
TaskGroup::Awaiter TaskGroup::receive(const Channel &channel){return Awaiter(Awaiter::Receive,this,channelIndex(channel));}
bool TaskGroup::Awaiter::await_suspend(TaskBody::Handle handle){
  return hostOperation(location,[&]{
  auto impl=group->impl;impl->require();
  {
    std::lock_guard lock(impl->mutex);
    if(activeTaskState!=impl.get()||activeTaskIndex>=impl->jobs.size()||impl->jobs[activeTaskIndex]->body!=handle)throw Trap("E_TASK_SCOPE","foreign coroutine cannot use this scheduler",0);
    impl->jobs[activeTaskIndex]->location=location;
  }
  return impl->suspend(activeTaskIndex,kind,target,std::move(value));
  });
}
TaskEvent TaskGroup::Awaiter::await_resume(){
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
  impl->require();auto index=channelIndex(channel);std::lock_guard lock(impl->mutex);
  if(impl->pipes[index]->closed)return false;impl->closePipe(index);return true;
}
bool TaskGroup::cancel(const Ticket &ticket){
  impl->require();auto index=taskIndex(ticket);std::lock_guard lock(impl->mutex);auto &job=*impl->jobs[index];if(job.done)return false;
  bool changed=!job.cancellation->cancelled.exchange(true);impl->interrupt();impl->changed.notify_all();return changed;
}
void TaskGroup::cancel(){impl->require();std::lock_guard lock(impl->mutex);impl->cancelled=true;impl->interrupt();impl->changed.notify_all();}
void TaskGroup::finish(){impl->require(true);impl->drain(false);}
