// Included inside namespace nexrt after the request/parallel runtime internals.
#ifndef NEX_STRUCTURED_WORKERS
#error NEX_ASYNC_TASKS requires NEX_STRUCTURED_WORKERS
#endif
namespace {
thread_local const void *activeTaskState=nullptr;
thread_local size_t activeTaskIndex=static_cast<size_t>(-1);
void taskValue(const Value &value){
  hostOperation({},[&]{
    try{validateParallelValue(value,[]{pollHostOperation(0);});}
    catch(const DataError &e){if(e.code=="E_PARALLEL_VALUE")throw DataError("E_TASK_VALUE",e.what());throw;}
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
      const std::shared_ptr<const task_detail::Cancellation> &cancel,TaskBody::Handle handle){
    RequestScope scope(control,&stop);scope.impl->taskStop=cancel;ParallelDepth depth;
    hostOperation({},[&]{
      scope.checkExecution(0,true,true);handle.resume();
      if(handle.done()){
        if(handle.promise().failure)std::rethrow_exception(handle.promise().failure);
        taskValue(handle.promise().value);
      }
      scope.checkExecution(0,true,false);
    });
  }
};
struct TaskGroup::Impl {
  enum Wait { None, Future, Send, Receive };
  struct Job {
    TaskBody::Handle body;Value result,pending;TaskEvent event;
    std::exception_ptr failure;
    std::shared_ptr<task_detail::Cancellation> cancellation;
    Wait wait=None;size_t target=none,previous=none,next=none,head=none,tail=none;
    bool running=false,queued=false,again=false,done=false,observed=false;
    ~Job(){if(body)body.destroy();}
  };
  struct Pipe {
    std::vector<std::optional<Value>> buffer;size_t start=0,count=0;
    size_t sendHead=none,sendTail=none,receiveHead=none,receiveTail=none;
    bool closed=false;
    explicit Pipe(size_t capacity):buffer(capacity){}
    void push(Value value){buffer[(start+count)%buffer.size()]=std::move(value);++count;}
    Value pop(){auto value=std::move(*buffer[start]);buffer[start].reset();start=(start+1)%buffer.size();--count;return value;}
  };
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
    jobs.reserve(maximum);pipes.reserve(1024);threads.reserve(workers);
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
    auto &job=*jobs[index];if(job.done||job.queued)return;
    if(job.running){job.again=true;return;}
    ready[(readyStart+readyCount)%ready.size()]=index;++readyCount;job.queued=true;changed.notify_all();
  }
  std::pair<size_t*,size_t*> ends(Job &job){
    if(job.wait==Future)return {&jobs[job.target]->head,&jobs[job.target]->tail};
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
  void complete(size_t index,std::exception_ptr failure){
    auto &job=*jobs[index];unlink(index);job.running=false;job.done=true;job.failure=std::move(failure);++completed;
    if(!job.failure)job.result=std::move(job.body.promise().value);
    while(job.head!=none)wake(job.head);changed.notify_all();
  }
  void work(){
    for(;;){
      size_t index;Job *runningJob;
      {
        std::unique_lock lock(mutex);changed.wait(lock,[&]{return started||stop;});
        while(!stop&&!readyCount){interrupt();if(readyCount)break;changed.wait_for(lock,std::chrono::milliseconds(2));}
        if(stop)return;
        index=ready[readyStart];readyStart=(readyStart+1)%ready.size();--readyCount;
        runningJob=jobs[index].get();auto &job=*runningJob;job.queued=false;job.running=true;job.again=false;
      }
      auto previousState=activeTaskState;auto previousIndex=activeTaskIndex;
      activeTaskState=this;activeTaskIndex=index;
      std::exception_ptr failure;
      try{TaskAccess::resume(control,cancelled,runningJob->cancellation,runningJob->body);}
      catch(...){failure=std::current_exception();}
      activeTaskState=previousState;activeTaskIndex=previousIndex;
      {
        std::lock_guard lock(mutex);auto &job=*jobs[index];
        if(failure||job.body.done())complete(index,std::move(failure));
        else if(job.again){job.running=false;enqueue(index);}
        else if(job.wait!=None)job.running=false;
        else{
          try{throw Trap("E_TASK_STATE","coroutine suspended outside its task scheduler",0);}catch(...){complete(index,std::current_exception());}
        }
      }
    }
  }
  bool suspend(size_t index,Awaiter::Kind kind,size_t target,Value value){
    require();
    if(kind==Awaiter::Send)taskValue(value);
    std::lock_guard lock(mutex);
    if(index>=jobs.size()||activeTaskState!=this||activeTaskIndex!=index)throw Trap("E_TASK_SCOPE","awaiter belongs to another task",0);
    auto &job=*jobs[index];job.event={};
    if(kind==Awaiter::Yield){job.again=true;return true;}
    if(kind==Awaiter::Future){
      if(target>=jobs.size())throw Trap("E_TASK_SCOPE","invalid task ticket",0);
      for(size_t next=target;next!=none;next=jobs[next]->wait==Future?jobs[next]->target:none)
        if(next==index)throw Trap("E_TASK_CYCLE","cyclic task wait",0);
      if(jobs[target]->done)return false;
      link(index,Future,target);return true;
    }
    if(finished||target>=pipes.size())throw Trap("E_TASK_SCOPE","channel scope has ended",0);
    auto &pipe=*pipes[target];
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
  std::lock_guard lock(impl->mutex);if(ticket.index>=impl->jobs.size())throw Trap("E_TASK_SCOPE","invalid task ticket",0);return ticket.index;
}
size_t TaskGroup::channelIndex(const Channel &channel)const{
  if(channel.owner.lock()!=impl)throw Trap("E_TASK_SCOPE","channel belongs to another or ended group",0);
  std::lock_guard lock(impl->mutex);if(impl->finished||channel.index>=impl->pipes.size())throw Trap("E_TASK_SCOPE","channel scope has ended",0);return channel.index;
}
TaskGroup::Ticket TaskGroup::spawn(Factory factory,Value input,Value captures){
  return hostOperation({},[&]{
    impl->require();if(!factory)throw Trap("E_TASK_SCOPE","task factory is missing",0);taskValue(input);taskValue(captures);
    auto job=std::make_unique<Impl::Job>();job->cancellation=std::make_shared<task_detail::Cancellation>();
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
    size_t index=impl->jobs.size();impl->jobs.push_back(std::move(job));impl->enqueue(index);return Ticket(impl,index);
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
  auto impl=group->impl;impl->require();
  {
    std::lock_guard lock(impl->mutex);
    if(activeTaskState!=impl.get()||activeTaskIndex>=impl->jobs.size()||impl->jobs[activeTaskIndex]->body!=handle)throw Trap("E_TASK_SCOPE","foreign coroutine cannot use this scheduler",0);
  }
  return impl->suspend(activeTaskIndex,kind,target,std::move(value));
}
TaskEvent TaskGroup::Awaiter::await_resume(){
  auto impl=group->impl;impl->require();std::lock_guard lock(impl->mutex);
  if(activeTaskState!=impl.get()||activeTaskIndex>=impl->jobs.size())throw Trap("E_TASK_SCOPE","awaiter resumed outside its task",0);
  if(kind==Future){auto &job=*impl->jobs[target];if(!job.done)throw Trap("E_TASK_STATE","future resumed before completion",0);job.observed=true;if(job.failure)std::rethrow_exception(job.failure);return {true,job.result};}
  return std::move(impl->jobs[activeTaskIndex]->event);
}
TaskGroup::Channel TaskGroup::channel(size_t capacity){
  return hostOperation({},[&]{impl->require();
    if(capacity>65536)throw Trap("E_RANGE","channel capacity exceeds65536",0);
    auto pipe=std::make_unique<Impl::Pipe>(capacity);std::lock_guard lock(impl->mutex);
    if(impl->finished||(impl->sealed&&activeTaskState!=impl.get()))throw Trap("E_TASK_SCOPE","channel scope is sealed",0);
    if(impl->pipes.size()>=1024||capacity>65536-impl->reservedSlots)throw Trap("E_LIMIT","channel slot limit exceeded",0);
    size_t index=impl->pipes.size();impl->pipes.push_back(std::move(pipe));impl->reservedSlots+=capacity;return Channel(impl,index);
  });
}
bool TaskGroup::close(const Channel &channel){
  impl->require();auto index=channelIndex(channel);std::lock_guard lock(impl->mutex);auto &pipe=*impl->pipes[index];
  if(pipe.closed)return false;pipe.closed=true;
  while(pipe.sendHead!=none){auto sender=pipe.sendHead;impl->jobs[sender]->pending={};impl->jobs[sender]->event={};impl->wake(sender);}
  while(pipe.receiveHead!=none){auto receiver=pipe.receiveHead;impl->jobs[receiver]->event=pipe.count?TaskEvent{true,pipe.pop()}:TaskEvent{};impl->wake(receiver);}
  return true;
}
bool TaskGroup::cancel(const Ticket &ticket){
  impl->require();auto index=taskIndex(ticket);std::lock_guard lock(impl->mutex);auto &job=*impl->jobs[index];if(job.done)return false;
  bool changed=!job.cancellation->cancelled.exchange(true);impl->interrupt();impl->changed.notify_all();return changed;
}
void TaskGroup::cancel(){impl->require();std::lock_guard lock(impl->mutex);impl->cancelled=true;impl->interrupt();impl->changed.notify_all();}
void TaskGroup::finish(){impl->require(true);impl->drain(false);}
