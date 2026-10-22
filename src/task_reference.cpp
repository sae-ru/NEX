#include "nex/task_reference.h"
#include "nex_task_reference_value.h"
#include <algorithm>
#include <chrono>
#include <deque>
#include <unordered_set>

namespace nex {
using RV=nexrt::Value;
using RD=nexrt::Data;
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
// This reference intentionally uses a single coordinator, scanning completion
// states and FIFO deques. It shares neither native wait lists nor dispatch code.
struct Reference {
  static constexpr size_t none=size_t(-1),maximumTasks=4096,maximumScopes=1024;
  enum State {Ready,Future,Send,Receive,Drain,Finishing,Done};
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
  };
  struct Region {
    size_t parent=none,owner=none,depth=1;
    bool closing=false,closed=false,abort=false;
    std::vector<size_t> members,children,pipes;
    std::shared_ptr<Error> failure;
    std::weak_ptr<RD> capability;
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

  static nexrt::TaskExecutionLimits selectedLimits(uint64_t legacy,const nexrt::TaskExecutionLimits *requested){
    if(requested){
      if(!nexrt::validTaskExecutionLimits(*requested))throw Error("E_OPTION","invalid task execution limits");
      return *requested;
    }
    // Existing numeric probes retain their step semantics, including zero.
    // Public explicit configurations use the canonical positive/range checks.
    nexrt::TaskExecutionLimits result;result.steps=legacy;return result;
  }
  Reference(const Program &p,uint64_t legacy,TaskReferenceObserver observer,const nexrt::TaskExecutionLimits *requested)
    :program(p),limits(selectedLimits(legacy,requested)),limit(limits.steps),
     deadline(Clock::now()+std::chrono::milliseconds(limits.timeoutMs)),observer(std::move(observer)){
    controlPoll=[this](Span span){checkControl(span);};
  }
  void checkControl(Span span={}){
    if(controlFailure)throw *controlFailure;
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
  void snapshot(const RV &root,size_t target,size_t current){
    std::vector<RV> work{root};std::unordered_set<const RD*> seen;size_t members=1;
    while(!work.empty()){
      auto v=std::move(work.back());work.pop_back();charge(1);
      if(v.tag==RV::Integer)continue;
      if(v.tag==RV::Floating){(void)v.floating();continue;}
      if(v.tag==RV::Boolean){if(v.scalar<0||v.scalar>1)throw Error("E_TASK_VALUE","invalid reference snapshot boolean");continue;}
      if(v.tag!=RV::Object||!v.object)throw Error("E_TASK_VALUE","invalid reference snapshot value");
      if(!seen.insert(v.object.get()).second)continue;
      if(seen.size()>262144||v.object->values.size()>262144-members)throw Error("E_LIMIT","reference snapshot graph exceeds262144 members");
      auto kind=v.object->kind;
      if(kind==RD::File)throw Error("E_TASK_VALUE","reference task cannot transport file authority");
      if(kind==RD::TaskScope||kind==RD::Task||kind==RD::Channel){
        capability(v,kind,current);
        auto scope=TaskReferenceAccess::scope(TaskReferenceAccess::get(v,kind,identity));
        if(target==none||!within(scope,target))throw Error("E_TASK_SCOPE","reference task capability escapes its logical owner scope");
      }
      members+=v.object->values.size();work.insert(work.end(),v.object->values.begin(),v.object->values.end());
    }
  }
  void enqueue(size_t i){auto &j=*jobs[i];if(j.state==Ready&&!j.queued){ready.push_back(i);j.queued=true;}}
  void answer(size_t i,RV result={}){
    auto &j=*jobs[i];j.stack.back().machine->resume(j.request.ticket,std::move(result));
    j.request={};j.pending={};j.target=none;j.state=Ready;enqueue(i);
  }
  static bool resource(const std::shared_ptr<Error> &e){return e&&(e->code=="E_LIMIT"||e->code=="E_MEMORY"||e->code=="E_TIMEOUT"||e->code=="E_CANCELLED");}
  static void prefer(std::shared_ptr<Error> &selected,const std::shared_ptr<Error> &candidate){
    if(candidate&&(!selected||(!resource(selected)&&resource(candidate))))selected=candidate;
  }
  void beginFinish(size_t i,std::shared_ptr<Error> failure={},RV result={}){
    auto &j=*jobs[i];if(j.state==Done)return;
    if(j.state==Finishing)prefer(j.failure,failure);
    else{j.state=Finishing;j.failure=std::move(failure);j.result=std::move(result);}
    // No completion is published until every retained frame and owned scope
    // has been released. Single-thread cleanup needs no native coroutine lock.
    j.stack.clear();j.request={};j.pending={};
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
      for(size_t s=regions.size();s-->0;){auto &r=regions[s];if(!r.closing||r.closed)continue;
        if(std::any_of(r.members.begin(),r.members.end(),[&](size_t i){return jobs[i]->state!=Done;})||
           std::any_of(r.children.begin(),r.children.end(),[&](size_t i){return !regions[i].closed;}))continue;
        for(auto i:r.members){auto &j=*jobs[i];if(!r.abort&&!j.observed&&!j.cancelled)prefer(r.failure,j.failure);j.observed=true;j.result={};j.capability.reset();}
        for(auto p:r.pipes){closePipe(p);channelSlots-=pipes[p].capacity;pipes[p].capacity=0;pipes[p].buffer.clear();pipes[p].capability.reset();}
        r.closed=true;r.capability.reset();if(jobs[r.owner]->state==Finishing)prefer(jobs[r.owner]->failure,r.failure);changed=true;
      }
      for(size_t i=0;i<jobs.size();++i){auto &j=*jobs[i];
        if(j.state==Finishing&&std::all_of(j.owned.begin(),j.owned.end(),[&](size_t s){return regions[s].closed;})){
          if(j.failure)j.result={};j.state=Done;changed=true;
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
    size_t s=regions.size();Region region;region.owner=i;region.parent=parent;region.depth=depth;regions.push_back(std::move(region));
    if(parent!=none)regions[parent].children.push_back(s);j.owned.push_back(s);j.current=s;
    Activation a;a.region=s;a.parent=parent;a.depth=outer;a.returnTicket=r.ticket;a.scopeSpan=r.span;
    a.machine=std::make_unique<TaskAstMachine>(program,fn.name,std::vector<RV>{value(RD::TaskScope,s)},limit-used,r.arguments[1],unsigned(outer),262144-pending,controlPoll);
    j.stack.push_back(std::move(a));j.request={};enqueue(i);
  }
  void spawn(size_t i,const TaskTransition &r){
    auto &parent=*jobs[i];auto s=capability(r.arguments.at(0),RD::TaskScope,parent.current);
    auto closure=r.arguments.at(1);const auto &fn=callback(closure,0);snapshot(closure,s,parent.current);
    if(jobs.size()>=maximumTasks||parent.depth>=256)throw Error("E_LIMIT","reference task slot/nesting limit exceeded",r.span);
    auto job=std::make_unique<Job>();job->member=job->current=s;job->parent=i;job->depth=parent.depth+1;
    Activation a;a.scopeSpan=fn.span;a.machine=std::make_unique<TaskAstMachine>(program,fn.name,std::vector<RV>{},limit-used,closure,0,262144,controlPoll);job->stack.push_back(std::move(a));
    auto id=jobs.size();jobs.push_back(std::move(job));regions[s].members.push_back(id);enqueue(id);answer(i,value(RD::Task,id));
  }
  void dispatch(size_t i){
    auto &j=*jobs[i];const auto &r=j.request;charge(1,r.span);
    if(r.operation=="task_yield"){answer(i);return;}
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
      auto item=r.arguments.at(1);snapshot(item,pipe.scope,j.current);
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
        auto target=a.region==none?j.member:a.parent;snapshot(r.value,target,j.current);
        if(a.region==none){beginFinish(i,{},std::move(r.value));return;}
        auto s=a.region;auto &region=regions[s];bool failed=r.value.tag==RV::Object&&r.value.object&&r.value.object->kind==RD::Failure;
        if(!failed&&cycle(i,s,true))throw Error("E_TASK_CYCLE","cyclic reference scope drain");
        a.result=std::move(r.value);a.completed=true;region.closing=true;region.abort=failed;
        if(failed)cancelRegion(s);j.target=s;j.state=Drain;return;
      }
      j.request=std::move(r);dispatch(i);
    }catch(const Error &e){
      auto located=std::make_shared<Error>(e);
      // An ordinary failure cannot hide shared resource exhaustion discovered
      // at the same source/host boundary. Already chosen resource errors keep
      // their established precedence during cancellation cleanup.
      try{checkControl(operationSpan);}catch(const Error &control){prefer(located,std::make_shared<Error>(control));}
      if(located->span.file.empty())located->span=operationSpan;beginFinish(i,std::move(located));
    }
    catch(const nexrt::DataError &e){beginFinish(i,std::make_shared<Error>(e.code,e.what(),j.request.span));}
  }
  void finishControl(){
    // No source continuation is resumed after a shared control failure. This
    // independent coordinator owns no physical IO; destroying all activations
    // and settling their scope ledgers drains every retained owned value.
    for(size_t i=0;i<jobs.size();++i)beginFinish(i,controlFailure);
    for(auto &region:regions)if(!region.closed){region.closing=true;region.abort=true;}
    settle();
    if(jobs[0]->state!=Done)throw Error("E_TASK_STATE","reference control cleanup did not drain all scopes");
    prefer(jobs[0]->failure,controlFailure);jobs[0]->result={};
  }
  TaskReferenceResult run(const std::string &entry,const std::vector<RV> &arguments){
    if(!program.taskPrototype)throw Error("E_TASK_STATE","reference scheduler requires checked task source");
    rootSpan=program.function(entry).span;
    for(const auto &v:arguments)snapshot(v,none,none);
    auto root=std::make_unique<Job>();Activation a;a.scopeSpan=rootSpan;a.machine=std::make_unique<TaskAstMachine>(program,entry,arguments,limit-used,RV{},0,262144,controlPoll);root->stack.push_back(std::move(a));jobs.push_back(std::move(root));enqueue(0);
    while(jobs[0]->state!=Done){
      try{checkControl();}catch(const Error &){finishControl();break;}
      settle();if(jobs[0]->state==Done)break;
      bool ran=false;
      while(!ready.empty()){
        auto i=ready.front();ready.pop_front();auto &j=*jobs[i];j.queued=false;
        if(j.state!=Ready||j.cancelled)continue;
        turn(i);ran=true;break;
      }
      if(!ran&&!settle()){
        try{checkControl();}catch(const Error &){finishControl();break;}
        throw Error("E_TASK_DEADLOCK","reference tasks are parked with no possible progress");
      }
    }
    try{checkControl();}catch(const Error &){finishControl();}
    if(jobs[0]->failure){auto error=*jobs[0]->failure;error.output=output;throw error;}
    TaskReferenceResult result;result.value=jobs[0]->result;result.output=output;result.steps=used;
    result.tasks=jobs.size();result.scopes=regions.size();result.channels=pipes.size();result.limits=limits;result.executionWorkers=1;return result;
  }
};
}
TaskReferenceResult evaluateTaskReference(const Program &p,const std::string &entry,const std::vector<RV> &arguments,uint64_t limit,TaskReferenceObserver observer,const nexrt::TaskExecutionLimits *taskLimits){
  Reference scheduler(p,limit,std::move(observer),taskLimits);
  try{return scheduler.run(entry,arguments);}catch(Error &e){e.output=scheduler.output;throw;}
}
}
