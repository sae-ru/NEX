#include "nex_task_profile.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <cstring>
#include <limits>
#include <stdexcept>
#include <utility>
#if defined(__APPLE__) || defined(__linux__)
#include <time.h>
#endif

namespace nexrt {
namespace task_profile_detail {
constexpr size_t none=std::numeric_limits<size_t>::max();
TaskProfileClockSample realSample(void *)noexcept{
  static std::atomic<uint64_t> nextThread{1};
  thread_local const uint64_t thread=nextThread.fetch_add(1,std::memory_order_relaxed);
  TaskProfileClockSample result;
  result.threadId=thread;
  const auto now=std::chrono::steady_clock::now().time_since_epoch();
  const auto wall=std::chrono::duration_cast<std::chrono::nanoseconds>(now).count();
  result.wallAvailable=wall>=0;result.wallNs=wall>=0?uint64_t(wall):0;
#if (defined(__APPLE__) || defined(__linux__)) && defined(CLOCK_THREAD_CPUTIME_ID)
  timespec time{};
  if(clock_gettime(CLOCK_THREAD_CPUTIME_ID,&time)==0&&time.tv_sec>=0&&time.tv_nsec>=0&&time.tv_nsec<1000000000&&uint64_t(time.tv_sec)<=(std::numeric_limits<uint64_t>::max()-uint64_t(time.tv_nsec))/1000000000){
    result.cpuNs=uint64_t(time.tv_sec)*1000000000+uint64_t(time.tv_nsec);
  }else result.cpuAvailable=false;
#else
  result.cpuAvailable=false;
#endif
  return result;
}
struct Text {size_t offset=0,size=0;};
struct Site {Text name,file,content;int64_t line=0;};
struct Task {
  TaskProfileTaskRecord record;
  size_t top=none;
  std::atomic<uint64_t> topId{0};
  bool attached=false;
};
struct Invocation {
  TaskProfileInvocationRecord record;
  size_t next=none,parent=none,task=none;
  uint64_t childCpu=0,childElapsed=0,children=0,segments=0;
  bool used=false,ending=false,aborted=false;
};
struct Event {bool segment=false;TaskProfileInvocationRecord invocation;TaskProfileSegmentRecord source;};
struct State {
  TaskProfileLimits limits;
  TaskProfileClock clock;
  std::atomic_flag mutex=ATOMIC_FLAG_INIT;
  TaskProfileDrops drops;
  std::vector<Site> sites;
  std::vector<char> text;
  std::vector<TaskProfileFunctionRecord> functions;
  std::unique_ptr<Task[]> tasks;
  std::unique_ptr<Invocation[]> invocations;
  std::unique_ptr<Event[]> events;
  size_t taskCount=0,eventCount=0,freeInvocation=none,storageBytes=0;
  uint64_t nextInvocation=1;
  State(TaskProfileOptions options,std::span<const TaskProfileSite> input,TaskProfileClock source):limits(options.limits),clock(source){
    if(limits.tasks>65536||limits.invocations>65536||limits.events>1000000||input.size()>16384)
      throw std::invalid_argument("task profile collector limits exceed private bounds");
    if(!clock.sample)clock={realSample,nullptr};
    size_t bytes=0;
    for(const auto &site:input)for(auto value:{site.name,site.file,site.content}){
      if(value.size()>16*1024*1024-bytes)throw std::invalid_argument("task profile site text exceeds private bound");
      bytes+=value.size();
    }
    sites.resize(input.size());text.resize(bytes);functions.resize(input.size());
    size_t offset=0;
    auto copy=[&](std::string_view value){Text result{offset,value.size()};if(!value.empty())std::memcpy(text.data()+offset,value.data(),value.size());offset+=value.size();return result;};
    for(size_t i=0;i<input.size();++i)sites[i]={copy(input[i].name),copy(input[i].file),copy(input[i].content),input[i].line};
    tasks=std::make_unique<Task[]>(limits.tasks);
    invocations=std::make_unique<Invocation[]>(limits.invocations);
    events=std::make_unique<Event[]>(limits.events);
    for(size_t i=0;i<limits.invocations;++i)invocations[i].next=i+1<limits.invocations?i+1:none;
    freeInvocation=limits.invocations?0:none;
    storageBytes=sizeof(State)+sites.capacity()*sizeof(Site)+text.capacity()+functions.capacity()*sizeof(TaskProfileFunctionRecord)+limits.tasks*sizeof(Task)+limits.invocations*sizeof(Invocation)+limits.events*sizeof(Event);
  }
  TaskProfileClockSample sample()const noexcept{return clock.sample(clock.context);}
  void add(uint64_t &target,uint64_t amount=1)noexcept{
    if(amount>std::numeric_limits<uint64_t>::max()-target){target=std::numeric_limits<uint64_t>::max();if(drops.counterOverflows!=std::numeric_limits<uint64_t>::max())++drops.counterOverflows;drops.incomplete=true;}
    else target+=amount;
  }
  void invalid()noexcept{add(drops.invalidTransitions);drops.incomplete=true;}
  void badClock()noexcept{add(drops.clockFailures);drops.incomplete=true;}
  void event(const TaskProfileInvocationRecord &record)noexcept{
    if(eventCount<limits.events){auto &event=events[eventCount++];event.segment=false;event.invocation=record;}
    else{add(drops.events);drops.incomplete=true;}
  }
  void event(const TaskProfileSegmentRecord &record)noexcept{
    if(eventCount<limits.events){auto &event=events[eventCount++];event.segment=true;event.source=record;}
    else{add(drops.events);drops.incomplete=true;}
  }
  bool live(size_t slot,uint64_t id)const noexcept{return slot<limits.invocations&&invocations[slot].used&&invocations[slot].record.id==id;}
  void refreshTop(Task &task)noexcept{
    while(task.top!=none&&invocations[task.top].ending)task.top=invocations[task.top].parent;
    task.topId.store(task.top==none?0:invocations[task.top].record.id,std::memory_order_relaxed);
  }
  void finalize(size_t index)noexcept{
    while(index!=none){
      auto &entry=invocations[index];
      if(!entry.used||!entry.ending||entry.children||entry.segments)return;
      auto &record=entry.record;
      record.outcome=entry.aborted?TaskProfileInvocationOutcome::Aborted:TaskProfileInvocationOutcome::Completed;
      record.inclusiveCpuNs=record.selfCpuNs;add(record.inclusiveCpuNs,entry.childCpu);
      record.activeElapsedNs=record.selfActiveElapsedNs;add(record.activeElapsedNs,entry.childElapsed);
      if(record.lifetimeAvailable&&record.endWallNs>=record.startWallNs)record.lifetimeNs=record.endWallNs-record.startWallNs;
      else record.lifetimeAvailable=false;
      auto &function=functions[record.site];
      add(entry.aborted?function.aborted:function.completed);
      add(function.selfCpuNs,record.selfCpuNs);add(function.inclusiveCpuNs,record.inclusiveCpuNs);
      add(function.selfActiveElapsedNs,record.selfActiveElapsedNs);add(function.activeElapsedNs,record.activeElapsedNs);
      add(function.lifetimeNs,record.lifetimeNs);function.maxLifetimeNs=std::max(function.maxLifetimeNs,record.lifetimeNs);
      function.cpuAvailable&=record.cpuAvailable;function.elapsedAvailable&=record.elapsedAvailable;function.lifetimeAvailable&=record.lifetimeAvailable;
      event(record);
      auto &task=tasks[entry.task];if(task.record.activeInvocations)--task.record.activeInvocations;else invalid();
      const auto parent=entry.parent;
      if(parent!=none){
        auto &owner=invocations[parent];
        add(owner.childCpu,record.inclusiveCpuNs);add(owner.childElapsed,record.activeElapsedNs);
        owner.record.cpuAvailable&=record.cpuAvailable;owner.record.elapsedAvailable&=record.elapsedAvailable;
        if(owner.ending){owner.record.endWallNs=std::max(owner.record.endWallNs,record.endWallNs);owner.record.lifetimeAvailable&=record.lifetimeAvailable;}
        if(owner.children)--owner.children;else invalid();
      }
      entry.used=false;entry.next=freeInvocation;freeInvocation=index;
      index=parent;
    }
  }
};
struct Lock {
  State &state;
  explicit Lock(State &input)noexcept:state(input){while(state.mutex.test_and_set(std::memory_order_acquire)){};}
  ~Lock(){state.mutex.clear(std::memory_order_release);}
};
struct ThreadContext {
  State *state=nullptr;size_t slot=none;uint64_t task=0;
  TaskProfileResumeGuard *guard=nullptr;TaskProfileSourceSegment *segment=nullptr;
};
thread_local ThreadContext current;
thread_local size_t guardDepth=0;
thread_local size_t suppressionDepth=0;
void invalid(const std::shared_ptr<State> &state)noexcept{if(state){Lock lock(*state);state->invalid();}}
bool suppressed(const std::shared_ptr<State> &state)noexcept{
  if(!suppressionDepth)return false;
  Lock lock(*state);state->add(state->drops.suppressedHooks);state->drops.incomplete=true;return true;
}
bool guardLimit(const std::shared_ptr<State> &state)noexcept{
  if(guardDepth<maximumTaskProfileGuardDepth)return false;
  Lock lock(*state);state->add(state->drops.guards);state->drops.incomplete=true;return true;
}
}
using task_profile_detail::State;
using task_profile_detail::Lock;
using task_profile_detail::none;
using task_profile_detail::current;

TaskProfileCollector::TaskProfileCollector(TaskProfileOptions options,std::span<const TaskProfileSite> sites,TaskProfileClock clock){
  if(options.enabled)state=std::make_shared<State>(options,sites,clock);
}
TaskProfileTask TaskProfileCollector::task()noexcept{
  TaskProfileTask result;if(!state)return result;
  if(task_profile_detail::suppressed(state))return result;
  const auto sample=state->sample();
  Lock lock(*state);
  if(state->taskCount>=state->limits.tasks){state->add(state->drops.tasks);state->drops.incomplete=true;return result;}
  const auto slot=state->taskCount++;auto &task=state->tasks[slot];
  task.record.id=uint64_t(slot)+1;task.record.createdWallNs=sample.wallNs;
  if(!sample.wallAvailable)state->badClock();
  result.state=state;result.slot=slot;result.value=task.record.id;return result;
}
TaskProfileTask TaskProfileCollector::task(const TaskProfileInvocation &parent)noexcept{
  if(!state)return {};
  if(parent.state!=state||!parent.value){task_profile_detail::invalid(state);return {};}
  if(task_profile_detail::suppressed(state))return {};
  // Validate the authenticated owner before creating any record. Parent IDs are
  // local to a collector and are never accepted as cross-collector authority.
  const auto sample=state->sample();Lock lock(*state);
  if(!state->live(parent.slot,parent.value)||state->invocations[parent.slot].ending){state->invalid();return {};}
  if(state->taskCount>=state->limits.tasks){state->add(state->drops.tasks);state->drops.incomplete=true;return {};}
  const auto slot=state->taskCount++;auto &task=state->tasks[slot];
  task.record.id=uint64_t(slot)+1;task.record.spawningInvocationId=parent.value;task.record.createdWallNs=sample.wallNs;
  if(!sample.wallAvailable)state->badClock();
  TaskProfileTask result;result.state=state;result.slot=slot;result.value=task.record.id;return result;
}
TaskProfileResumeGuard TaskProfileCollector::resume(const TaskProfileTask &task)noexcept{
  return TaskProfileResumeGuard(task,state);
}
void TaskProfileResumeGuard::suppress()noexcept{
  if(!task_profile_detail::suppressionDepth&&current.segment)current.segment->pause();
  if(task_profile_detail::suppressionDepth==std::numeric_limits<size_t>::max()){
    Lock lock(*state);state->add(state->drops.counterOverflows);state->drops.incomplete=true;return;
  }
  ++task_profile_detail::suppressionDepth;suppressing=true;
}
TaskProfileResumeGuard::TaskProfileResumeGuard(const TaskProfileTask &input,const std::shared_ptr<State> &expected)noexcept{
  if(!expected)return;
  state=expected;
  if(input.state!=state||!input.value){task_profile_detail::invalid(state);suppress();return;}
  if(task_profile_detail::suppressionDepth||task_profile_detail::guardLimit(state)){
    if(task_profile_detail::suppressionDepth){Lock lock(*state);state->add(state->drops.guards);state->drops.incomplete=true;}
    suppress();return;
  }
  auto owner=state;const auto sample=owner->sample();bool rejected=false;
  {
    Lock lock(*owner);
    if(input.slot>=owner->taskCount||owner->tasks[input.slot].record.id!=input.value||owner->tasks[input.slot].attached||owner->tasks[input.slot].record.terminal||owner->tasks[input.slot].record.cancelledBeforeStart){owner->invalid();rejected=true;}
    else{
      auto &task=owner->tasks[input.slot];task.attached=true;
      owner->add(task.record.resumes);
      if(task.record.lastThreadId&&sample.threadId!=task.record.lastThreadId)owner->add(task.record.migrations);
      task.record.lastThreadId=sample.threadId;
      if(!sample.threadId)owner->badClock();
    }
  }
  if(rejected){suppress();return;}
  state=std::move(owner);slot=input.slot;task=input.value;thread=sample.threadId;
  priorState=current.state;priorSlot=current.slot;priorTask=current.task;priorGuard=current.guard;priorSegment=current.segment;
  if(priorSegment)priorSegment->pause();
  current={state.get(),slot,task,this,nullptr};attached=true;++task_profile_detail::guardDepth;
}
TaskProfileResumeGuard::~TaskProfileResumeGuard(){
  if(suppressing){
    --task_profile_detail::suppressionDepth;
    if(!task_profile_detail::suppressionDepth&&current.segment)current.segment->resume();
    return;
  }
  if(!attached)return;
  if(current.guard!=this){
    task_profile_detail::invalid(state);
    // Same-thread non-LIFO destruction must not leave a nested guard pointing
    // at this expired object. Its parked source chain belongs to this guard;
    // detach it, then restore our predecessor when the nested guard retires.
    auto *child=current.guard;
    while(child&&child->priorGuard!=this)child=child->priorGuard;
    if(!child)return; // Wrong-thread destruction is explicitly unsupported.
    for(auto *segment=child->priorSegment;segment;segment=segment->prior)if(segment->attached){segment->pause();segment->attached=false;--task_profile_detail::guardDepth;}
    child->priorState=priorState;child->priorSlot=priorSlot;child->priorTask=priorTask;
    child->priorGuard=priorGuard;child->priorSegment=priorSegment;
    {Lock lock(*state);state->tasks[slot].attached=false;}
    attached=false;--task_profile_detail::guardDepth;return;
  }
  // A source guard must be inside its resume guard. Defensive teardown keeps
  // live record storage until that source guard retires, without dangling TLS.
  if(current.segment){
    task_profile_detail::invalid(state);
    for(auto *segment=current.segment;segment;segment=segment->prior)if(segment->attached){segment->pause();segment->attached=false;--task_profile_detail::guardDepth;}
  }
  {Lock lock(*state);state->tasks[slot].attached=false;}
  current={priorState,priorSlot,priorTask,priorGuard,priorSegment};
  attached=false;--task_profile_detail::guardDepth;
  if(priorSegment)priorSegment->resume();
}
TaskProfileInvocation TaskProfileCollector::invocation(size_t site)noexcept{
  TaskProfileInvocation result;if(!state)return result;
  if(task_profile_detail::suppressed(state))return result;
  if(current.state!=state.get()||current.slot==none){task_profile_detail::invalid(state);return result;}
  const auto sample=state->sample();Lock lock(*state);
  if(site>=state->sites.size()||current.slot>=state->taskCount||state->tasks[current.slot].record.terminal){state->invalid();return result;}
  if(state->freeInvocation==none||state->nextInvocation==std::numeric_limits<uint64_t>::max()){
    state->add(state->drops.invocations);state->drops.incomplete=true;return result;
  }
  auto &task=state->tasks[current.slot];const auto index=state->freeInvocation;
  auto &entry=state->invocations[index];state->freeInvocation=entry.next;entry={};
  entry.used=true;entry.parent=task.top;entry.task=current.slot;
  auto &record=entry.record;record.id=state->nextInvocation++;record.taskId=task.record.id;record.site=site;record.startWallNs=sample.wallNs;
  record.lifetimeAvailable=sample.wallAvailable;
  if(!sample.wallAvailable)state->badClock();
  if(entry.parent!=none){auto &parent=state->invocations[entry.parent];record.parentId=parent.record.id;state->add(parent.children);}
  task.top=index;task.topId.store(record.id,std::memory_order_relaxed);task.record.started=true;state->add(task.record.activeInvocations);
  state->add(state->functions[site].calls);
  result.state=state;result.slot=index;result.value=record.id;result.task=record.taskId;return result;
}
void TaskProfileInvocation::finish(bool aborted)noexcept{
  if(!value)return;
  auto owner=state;const auto id=std::exchange(value,0);task=0;
  const auto sample=owner->sample();
  {
    Lock lock(*owner);
    if(!owner->live(slot,id)){owner->invalid();return;}
    auto &entry=owner->invocations[slot];auto &record=entry.record;
    if(entry.ending){owner->invalid();return;}
    entry.ending=true;entry.aborted=aborted;
    // A premature completion is not credited as a successful source return.
    // Descendant and segment records keep this slot alive until finalization.
    if((entry.children&&!aborted)||entry.segments){owner->invalid();entry.aborted=true;}
    record.endWallNs=sample.wallNs;
    if(!sample.wallAvailable||sample.wallNs<record.startWallNs){record.lifetimeAvailable=false;owner->badClock();}
    owner->refreshTop(owner->tasks[entry.task]);owner->finalize(slot);
  }
  state.reset();
}
TaskProfileInvocation::~TaskProfileInvocation(){finish(true);}
TaskProfileInvocation::TaskProfileInvocation(TaskProfileInvocation &&other)noexcept:state(std::move(other.state)),slot(other.slot),value(std::exchange(other.value,0)),task(std::exchange(other.task,0)){}
TaskProfileInvocation &TaskProfileInvocation::operator=(TaskProfileInvocation &&other)noexcept{
  if(this!=&other){finish(true);state=std::move(other.state);slot=other.slot;value=std::exchange(other.value,0);task=std::exchange(other.task,0);}return *this;
}
TaskProfileSourceSegment TaskProfileCollector::source(const TaskProfileInvocation &input)noexcept{
  if(input.state&&input.state!=state){task_profile_detail::invalid(state);return TaskProfileSourceSegment({});}
  if(state&&task_profile_detail::suppressed(state))return TaskProfileSourceSegment({});
  if(input.state!=state){task_profile_detail::invalid(state);return TaskProfileSourceSegment({});}
  return TaskProfileSourceSegment(input);
}
TaskProfileSourceSegment::TaskProfileSourceSegment(const TaskProfileInvocation &input)noexcept{
  if(!input.state||!input.value)return;
  if(task_profile_detail::guardLimit(input.state))return;
  if(current.state!=input.state.get()||current.task!=input.task){task_profile_detail::invalid(input.state);return;}
  {
    Lock lock(*input.state);
    if(!input.state->live(input.slot,input.value)||input.state->invocations[input.slot].ending||current.slot>=input.state->taskCount||input.state->tasks[current.slot].top!=input.slot){input.state->invalid();return;}
    input.state->add(input.state->invocations[input.slot].segments);
  }
  state=input.state;slot=input.slot;invocation=input.value;task=input.task;
  prior=current.segment;if(prior)prior->pause();
  current.segment=this;attached=true;++task_profile_detail::guardDepth;resume();
}
void TaskProfileSourceSegment::resume()noexcept{
  if(!attached||measuring||task_profile_detail::suppressionDepth)return;
  if(current.state!=state.get()||current.task!=task||current.segment!=this){task_profile_detail::invalid(state);return;}
  start=state->sample();measuring=true;
}
void TaskProfileSourceSegment::pause()noexcept{
  if(!measuring)return;
  measuring=false;const auto end=state->sample();
  TaskProfileSegmentRecord segment;segment.taskId=task;segment.invocationId=invocation;segment.threadId=start.threadId;segment.startWallNs=start.wallNs;
  segment.elapsedAvailable=start.wallAvailable&&end.wallAvailable&&end.wallNs>=start.wallNs;
  segment.cpuAvailable=start.cpuAvailable&&end.cpuAvailable&&start.threadId&&start.threadId==end.threadId&&end.cpuNs>=start.cpuNs;
  if(segment.elapsedAvailable)segment.elapsedNs=end.wallNs-start.wallNs;
  if(segment.cpuAvailable)segment.cpuNs=end.cpuNs-start.cpuNs;
  Lock lock(*state);
  if(!state->live(slot,invocation)){state->invalid();return;}
  auto &entry=state->invocations[slot];auto &record=entry.record;
  if(!segment.elapsedAvailable||!segment.cpuAvailable)state->badClock();
  record.cpuAvailable&=segment.cpuAvailable;record.elapsedAvailable&=segment.elapsedAvailable;
  state->add(record.selfCpuNs,segment.cpuNs);state->add(record.selfActiveElapsedNs,segment.elapsedNs);
  auto &owner=state->tasks[entry.task];state->add(owner.record.sourceCpuNs,segment.cpuNs);state->add(owner.record.sourceElapsedNs,segment.elapsedNs);
  if(entry.ending){record.endWallNs=std::max(record.endWallNs,end.wallNs);record.lifetimeAvailable&=end.wallAvailable;}
  state->event(segment);
}
TaskProfileSourceSegment::~TaskProfileSourceSegment(){
  if(!state)return;
  pause();
  if(attached){
    if(current.segment==this){current.segment=prior;attached=false;--task_profile_detail::guardDepth;if(prior)prior->resume();}
    else{
      task_profile_detail::invalid(state);
      // The current chain or a nested resume guard's parked chain can contain
      // this source interval. Reparent every reference before releasing it.
      auto unlink=[&](TaskProfileSourceSegment *&head){
        if(head==this){head=prior;return true;}
        for(auto *child=head;child;child=child->prior)if(child->prior==this){child->prior=prior;return true;}
        return false;
      };
      bool found=unlink(current.segment);
      for(auto *guard=current.guard;guard;guard=guard->priorGuard)found=unlink(guard->priorSegment)||found;
      if(!found)return; // Wrong-thread destruction is explicitly unsupported.
      attached=false;--task_profile_detail::guardDepth;
    }
  }
  {Lock lock(*state);if(!state->live(slot,invocation))state->invalid();else{auto &entry=state->invocations[slot];if(entry.segments)--entry.segments;else state->invalid();state->finalize(slot);}}
}
void TaskProfileCollector::cancelBeforeStart(const TaskProfileTask &input)noexcept{
  if(!state)return;
  if(input.state!=state||!input.value){task_profile_detail::invalid(state);return;}
  Lock lock(*state);
  if(input.slot>=state->taskCount||state->tasks[input.slot].record.id!=input.value){state->invalid();return;}
  auto &record=state->tasks[input.slot].record;
  if(record.started||record.terminal||state->tasks[input.slot].attached){state->invalid();return;}
  record.cancelledBeforeStart=true;
}
void TaskProfileCollector::terminal(const TaskProfileTask &input,TaskProfileTaskOutcome outcome)noexcept{
  if(!state)return;
  if(input.state!=state||!input.value){task_profile_detail::invalid(state);return;}
  const auto sample=state->sample();Lock lock(*state);
  if(input.slot>=state->taskCount||state->tasks[input.slot].record.id!=input.value){state->invalid();return;}
  auto &record=state->tasks[input.slot].record;
  if(record.terminal||record.activeInvocations||state->tasks[input.slot].attached||(record.cancelledBeforeStart&&outcome!=TaskProfileTaskOutcome::Cancelled)){state->invalid();return;}
  record.terminal=true;record.outcome=outcome;record.terminalWallNs=sample.wallNs;
  if(!sample.wallAvailable||sample.wallNs<record.createdWallNs)state->badClock();
}
uint64_t currentTaskProfileTask()noexcept{return task_profile_detail::suppressionDepth?0:current.task;}
uint64_t currentTaskProfileInvocation()noexcept{
  return !task_profile_detail::suppressionDepth&&current.state&&current.slot!=none?current.state->tasks[current.slot].topId.load(std::memory_order_relaxed):0;
}
TaskProfileSnapshot TaskProfileCollector::snapshot()const{
  TaskProfileSnapshot result;if(!state)return result;
  result.enabled=true;result.limits=state->limits;
  // Allocate before taking the recording lock. Only POD copies are made while
  // holding it; metadata conversion/strings and all user clock callbacks stay out.
  std::vector<TaskProfileFunctionRecord> functions(state->functions.size());
  std::vector<TaskProfileTaskRecord> tasks(state->limits.tasks);
  std::vector<TaskProfileInvocationRecord> active(state->limits.invocations);
  std::vector<task_profile_detail::Event> events(state->limits.events);
  size_t tasksUsed=0,activeUsed=0,eventsUsed=0;
  {
    Lock lock(*state);result.drops=state->drops;tasksUsed=state->taskCount;eventsUsed=state->eventCount;
    std::copy(state->functions.begin(),state->functions.end(),functions.begin());
    for(size_t i=0;i<tasksUsed;++i)tasks[i]=state->tasks[i].record;
    for(size_t i=0;i<state->limits.invocations;++i)if(state->invocations[i].used){
      const auto &entry=state->invocations[i];auto record=entry.record;
      auto sum=[&](uint64_t first,uint64_t second){
        if(second>std::numeric_limits<uint64_t>::max()-first){result.drops.incomplete=true;if(result.drops.counterOverflows!=std::numeric_limits<uint64_t>::max())++result.drops.counterOverflows;return std::numeric_limits<uint64_t>::max();}
        return first+second;
      };
      record.inclusiveCpuNs=sum(record.selfCpuNs,entry.childCpu);
      record.activeElapsedNs=sum(record.selfActiveElapsedNs,entry.childElapsed);
      active[activeUsed++]=record;
    }
    std::copy_n(state->events.get(),eventsUsed,events.begin());
  }
  result.collectorStorageBytes=state->storageBytes;result.siteTextStorageBytes=state->text.capacity();
  result.tasks.assign(tasks.begin(),tasks.begin()+tasksUsed);
  result.functions.reserve(functions.size());
  auto text=[&](task_profile_detail::Text value){return value.size?std::string(state->text.data()+value.offset,value.size):std::string{};};
  for(size_t i=0;i<functions.size();++i){
    TaskProfileFunctionSnapshot function;static_cast<TaskProfileFunctionRecord&>(function)=functions[i];
    const auto &site=state->sites[i];function.name=text(site.name);function.file=text(site.file);function.content=text(site.content);function.line=site.line;result.functions.push_back(std::move(function));
  }
  result.invocations.reserve(activeUsed+eventsUsed);result.segments.reserve(eventsUsed);
  for(size_t i=0;i<eventsUsed;++i)if(events[i].segment)result.segments.push_back(events[i].source);else result.invocations.push_back(events[i].invocation);
  result.invocations.insert(result.invocations.end(),active.begin(),active.begin()+activeUsed);
  return result;
}
}
