#include "nex_task_debug.h"
#include "nex_task_frame.h"
#include <algorithm>
#include <atomic>
#include <cstring>
#include <limits>
#include <memory>
#include <set>
#include <utility>
#ifdef __APPLE__
#include <pthread.h>
#elif defined(__linux__)
#include <sys/syscall.h>
#include <unistd.h>
#endif
extern "C" {nexrt::TaskDebugCatalog nex_task_debug_catalog_v1{};}
namespace nexrt {
namespace task_debug_detail {
static_assert(std::atomic_ref<uint64_t>::is_always_lock_free);
uint64_t get(const uint64_t &word)noexcept{return std::atomic_ref<uint64_t>(const_cast<uint64_t&>(word)).load(std::memory_order_acquire);}
void put(uint64_t &word,uint64_t value)noexcept{std::atomic_ref<uint64_t>(word).store(value,std::memory_order_release);}
bool add(uint64_t &word,uint64_t amount=1)noexcept{
  auto atomic=std::atomic_ref<uint64_t>(word);auto previous=atomic.load(std::memory_order_relaxed);
  for(;;){const bool overflow=amount>UINT64_MAX-previous;const auto next=overflow?UINT64_MAX:previous+amount;if(atomic.compare_exchange_weak(previous,next,std::memory_order_relaxed))return !overflow;}
}
void flags(uint64_t &word,uint64_t bits)noexcept{std::atomic_ref<uint64_t>(word).fetch_or(bits,std::memory_order_relaxed);}
uint64_t address(const void *pointer)noexcept{return reinterpret_cast<uintptr_t>(pointer);}
struct TaskInfo {std::atomic<void*> stack{nullptr};};
struct FrameInfo {uint64_t next=noTaskDebugIndex;bool used=false;};
struct State {
  const TaskDebugCodeSite *codes;size_t count;
  std::unique_ptr<TaskDebugTaskRecord[]> tasks=std::make_unique<TaskDebugTaskRecord[]>(maximumTaskDebugTasks);
  std::unique_ptr<TaskDebugFrameRecord[]> frames=std::make_unique<TaskDebugFrameRecord[]>(maximumTaskDebugFrames);
  std::unique_ptr<TaskInfo[]> taskInfo=std::make_unique<TaskInfo[]>(maximumTaskDebugTasks);
  std::unique_ptr<FrameInfo[]> frameInfo=std::make_unique<FrameInfo[]>(maximumTaskDebugFrames);
  std::unique_ptr<std::pair<uint64_t,uint64_t>[]> lookup;
  std::atomic_flag mutex=ATOMIC_FLAG_INIT;
  uint64_t taskCount=0,freeFrame=0,nextFrame=1;
  State(const TaskDebugCodeSite *codes,size_t count):codes(codes),count(count),lookup(std::make_unique<std::pair<uint64_t,uint64_t>[]>(count)){
    for(size_t i=0;i<count;++i)lookup[i]={address(codes[i].code),i};
    std::sort(lookup.get(),lookup.get()+count);
    for(size_t i=0;i<maximumTaskDebugFrames;++i)frameInfo[i].next=i+1<maximumTaskDebugFrames?i+1:noTaskDebugIndex;
  }
};
struct Lock {State &state;explicit Lock(State &state)noexcept:state(state){while(state.mutex.test_and_set(std::memory_order_acquire)){};}~Lock(){state.mutex.clear(std::memory_order_release);}};
std::unique_ptr<State> storage;
std::atomic<State*> published{nullptr};
thread_local TaskDebugTask current;
void invalid()noexcept{add(nex_task_debug_catalog_v1.invalid_transitions);}
bool valid(const TaskDebugTask &task)noexcept{return task.owner&&task.slot<maximumTaskDebugTasks&&task.id&&get(task.owner->tasks[task.slot].id)==task.id;}
uint64_t nativeThread()noexcept{
#ifdef __APPLE__
  uint64_t value=0;pthread_threadid_np(nullptr,&value);return value;
#elif defined(__linux__)
  return uint64_t(::syscall(SYS_gettid));
#else
  return 0;
#endif
}
bool begin(uint64_t &sequence)noexcept{const auto value=get(sequence);if(value>=UINT64_MAX-1){put(sequence,UINT64_MAX);invalid();return false;}if(!(value&1))put(sequence,value+1);return true;}
bool end(uint64_t &sequence)noexcept{const auto value=get(sequence);if(value>=UINT64_MAX-1){put(sequence,UINT64_MAX);invalid();return false;}put(sequence,(value&1)?value+1:value+2);return true;}
void validate(const TaskDebugCodeSite *codes,int64_t count){
  if(!codes||count<1||uint64_t(count)>maximumTaskDebugCodes)throw DataError("E_DEBUG_INIT","invalid task debugger code registry");
  size_t text=0,points=0,bindings=0,visible=0,bytes=size_t(count)*sizeof(TaskDebugCodeSite);
  auto string=[&](const char *value,bool required=true){if(!value)throw DataError("E_DEBUG_INIT","task debugger text is absent");const auto remaining=maximumTaskDebugTextBytes-text;const auto n=::strnlen(value,remaining);if(n>=remaining||(required&&!n))throw DataError("E_DEBUG_INIT","task debugger text exceeds its bound or is empty");text+=n+1;};
  std::set<const void*> descriptors;
  for(int64_t i=0;i<count;++i){const auto &code=codes[i];
    if(!code.code||!descriptors.insert(code.code).second||code.pointCount<1||code.bindingCount<0||code.visibleCount<0||code.slotCount<0||code.slotCount>65536||!code.points||(!code.bindings&&code.bindingCount)||(!code.visibleBindings&&code.visibleCount))throw DataError("E_DEBUG_INIT","invalid task debugger function metadata");
    const auto &descriptor=*static_cast<const TaskCodeDescriptor*>(code.code);
    if(descriptor.abi!=taskCodeABI||descriptor.slotCount!=code.slotCount)throw DataError("E_DEBUG_INIT","task debugger metadata differs from execution descriptor");
    if(uint64_t(code.pointCount)>maximumTaskDebugPoints-points||uint64_t(code.bindingCount)>maximumTaskDebugBindings-bindings||uint64_t(code.visibleCount)>maximumTaskDebugVisibleBindings-visible)throw DataError("E_DEBUG_INIT","task debugger metadata count exceeds its bound");
    points+=size_t(code.pointCount);bindings+=size_t(code.bindingCount);visible+=size_t(code.visibleCount);
    string(code.name);string(code.file);string(code.content);string(code.functionHash);
    std::set<int64_t> ids;
    for(int64_t j=0;j<code.bindingCount;++j){const auto &binding=code.bindings[j];string(binding.name);string(binding.type);
      if(binding.id<1||!ids.insert(binding.id).second||binding.slot< -1||binding.slot>=code.slotCount||binding.scope<0||(binding.slot<0&&std::strcmp(binding.type,"unit")))throw DataError("E_DEBUG_INIT","invalid task debugger binding metadata");}
    for(int64_t j=0;j<code.pointCount;++j){const auto &point=code.points[j];string(point.site);
      if(point.pc<0||point.pc>=int64_t(maximumTaskDebugPoints)||point.line<1||point.column<1||point.begin<0||point.end<point.begin||point.kind<0||point.kind>int64_t(TaskDebugPointKind::Return)||point.visibleBegin<0||point.visibleCount<0||point.visibleBegin>code.visibleCount||point.visibleCount>code.visibleCount-point.visibleBegin)throw DataError("E_DEBUG_INIT","invalid task debugger source point");
      std::set<int64_t> seen;for(int64_t k=0;k<point.visibleCount;++k){const auto index=code.visibleBindings[point.visibleBegin+k];if(index<0||index>=code.bindingCount||!seen.insert(index).second)throw DataError("E_DEBUG_INIT","invalid task debugger visible binding index");}
    }
  }
  bytes+=points*sizeof(TaskDebugPoint)+bindings*sizeof(TaskDebugBinding)+visible*sizeof(int64_t);
  if(bytes>maximumTaskDebugMetadataBytes||text>maximumTaskDebugMetadataBytes-bytes)throw DataError("E_DEBUG_INIT","task debugger metadata storage exceeds its bound");
}
}
using namespace task_debug_detail;
bool taskDebugEnabled()noexcept{return published.load(std::memory_order_acquire)!=nullptr;}
void taskDebugUnavailableCurrent()noexcept{if(valid(current)){invalid();flags(current.owner->tasks[current.slot].flags,taskDebugUnavailable);taskDebugInvalidate(current);}}
TaskDebugTask taskDebugCreateTask()noexcept{
  auto *state=published.load(std::memory_order_acquire);if(!state)return {};
  Lock lock(*state);if(state->taskCount>=maximumTaskDebugTasks){add(nex_task_debug_catalog_v1.dropped_tasks);return {};}
  const auto slot=state->taskCount++;auto &record=state->tasks[slot];const auto id=slot+1;
  put(record.id,id);put(record.generation,1);put(record.top_frame_slot,noTaskDebugIndex);put(record.flags,taskDebugNotStarted);
  if(valid(current)){put(record.origin_task_id,current.id);const auto &parent=current.owner->tasks[current.slot];const auto origin=get(parent.top_frame_id);put(record.origin_frame_id,origin);if(!origin)flags(record.flags,taskDebugOriginOmitted);}
  put(record.source_sequence,2);put(record.scheduler_sequence,2);put(nex_task_debug_catalog_v1.task_count,state->taskCount);return {state,slot,id};
}
TaskDebugTask taskDebugCurrentTask()noexcept{return current;}
void taskDebugInvalidate(const TaskDebugTask &task)noexcept{
  if(!valid(task))return;auto &record=task.owner->tasks[task.slot];if(!begin(record.source_sequence))flags(record.flags,taskDebugUnavailable);
  std::atomic_ref<uint64_t>(record.flags).fetch_and(~(taskDebugAtCheckpoint|taskDebugParked),std::memory_order_relaxed);
}
void taskDebugKernelState(const TaskDebugTask &task,TaskDebugState value,TaskDebugWait wait,uint64_t target)noexcept{
  if(!valid(task))return;auto &record=task.owner->tasks[task.slot];if(!begin(record.scheduler_sequence)){flags(record.flags,taskDebugUnavailable);taskDebugInvalidate(task);return;}
  put(record.state,uint64_t(value));put(record.wait_kind,uint64_t(wait));put(record.wait_target,target);
  if(value==TaskDebugState::Running&&!add(record.run_epoch)){flags(record.flags,taskDebugUnavailable);taskDebugInvalidate(task);}
  if(value==TaskDebugState::Terminal)flags(record.flags,taskDebugTerminal);
  end(record.scheduler_sequence);
}
TaskDebugTurn::TaskDebugTurn(const TaskDebugTask &task)noexcept:previous(current){current=valid(task)?task:TaskDebugTask{};if(current){taskDebugInvalidate(current);put(current.owner->tasks[current.slot].worker_id,nativeThread());}}
TaskDebugTurn::~TaskDebugTurn(){current=previous;}
TaskDebugStackRegistration::TaskDebugStackRegistration(void *stack)noexcept:task(current){if(valid(task))task.owner->taskInfo[task.slot].stack.store(stack,std::memory_order_release);}
TaskDebugStackRegistration::~TaskDebugStackRegistration(){if(valid(task)){taskDebugInvalidate(task);task.owner->taskInfo[task.slot].stack.store(nullptr,std::memory_order_release);Lock lock(*task.owner);auto &record=task.owner->tasks[task.slot];put(record.frame_count,0);put(record.top_frame_slot,noTaskDebugIndex);put(record.top_frame_id,0);}}
void *taskDebugCurrentStack()noexcept{return valid(current)?current.owner->taskInfo[current.slot].stack.load(std::memory_order_acquire):nullptr;}
uint64_t taskDebugCodeIndex(const void *descriptor)noexcept{
  auto *state=published.load(std::memory_order_acquire);if(!state)return noTaskDebugIndex;
  const auto key=address(descriptor);size_t first=0,last=state->count;
  while(first<last){const auto middle=first+(last-first)/2;if(state->lookup[middle].first<key)first=middle+1;else last=middle;}
  return first<state->count&&state->lookup[first].first==key?state->lookup[first].second:noTaskDebugIndex;
}
TaskDebugFrame::TaskDebugFrame(size_t codeIndex)noexcept{
  if(!valid(current))return;auto *state=current.owner;taskDebugInvalidate(current);Lock lock(*state);
  if(codeIndex>=state->count){invalid();flags(state->tasks[current.slot].flags,taskDebugUnavailable);return;}
  if(state->freeFrame==noTaskDebugIndex||state->nextFrame==std::numeric_limits<uint64_t>::max()){add(nex_task_debug_catalog_v1.dropped_frames);flags(state->tasks[current.slot].flags,taskDebugUnavailable);return;}
  owner=state;slot=state->freeFrame;id=state->nextFrame++;taskId=current.id;auto &info=state->frameInfo[slot];state->freeFrame=info.next;info.used=true;
  auto &record=state->frames[slot];if(!begin(record.sequence)){info.used=false;owner=nullptr;slot=noTaskDebugIndex;id=taskId=0;add(nex_task_debug_catalog_v1.dropped_frames);flags(state->tasks[current.slot].flags,taskDebugUnavailable);return;}put(record.id,id);put(record.task_id,taskId);put(record.parent_slot,noTaskDebugIndex);put(record.parent_id,0);put(record.code_index,codeIndex);put(record.frame_address,0);put(record.point_index,noTaskDebugIndex);put(record.depth,0);put(record.flags,1);end(record.sequence);add(nex_task_debug_catalog_v1.live_frames);
}
void TaskDebugFrame::retire()noexcept{
  if(!owner||!id)return;auto *state=owner;const auto taskSlot=taskId-1;TaskDebugTask task{state,taskSlot,taskId};taskDebugInvalidate(task);Lock lock(*state);
  auto &record=state->frames[slot];if(!state->frameInfo[slot].used||get(record.id)!=id){invalid();}else{begin(record.sequence);put(record.frame_address,0);put(record.flags,1);put(record.id,0);end(record.sequence);state->frameInfo[slot].used=false;state->frameInfo[slot].next=state->freeFrame;state->freeFrame=slot;std::atomic_ref<uint64_t>(nex_task_debug_catalog_v1.live_frames).fetch_sub(1,std::memory_order_relaxed);}
  owner=nullptr;slot=noTaskDebugIndex;id=taskId=0;
}
TaskDebugFrame::TaskDebugFrame(TaskDebugFrame &&other)noexcept:owner(std::exchange(other.owner,nullptr)),slot(std::exchange(other.slot,noTaskDebugIndex)),id(std::exchange(other.id,0)),taskId(std::exchange(other.taskId,0)){}
TaskDebugFrame &TaskDebugFrame::operator=(TaskDebugFrame &&other)noexcept{if(this!=&other){retire();owner=std::exchange(other.owner,nullptr);slot=std::exchange(other.slot,noTaskDebugIndex);id=std::exchange(other.id,0);taskId=std::exchange(other.taskId,0);}return *this;}
void taskDebugPublish(std::span<const TaskDebugFrameView> views,bool checkpoint)noexcept{
  if(!valid(current))return;auto *state=current.owner;taskDebugInvalidate(current);TaskDebugStop stop{};bool marker=false;
  {
    Lock lock(*state);auto &task=state->tasks[current.slot];
    if(views.size()>maximumTaskDebugStack||get(task.flags)&taskDebugUnavailable){flags(task.flags,taskDebugUnavailable);return;}
    for(const auto &view:views)if(!view.address||!view.frame||view.frame->owner!=state||view.frame->taskId!=current.id||!view.frame->id||!state->frameInfo[view.frame->slot].used||get(state->frames[view.frame->slot].id)!=view.frame->id){invalid();flags(task.flags,taskDebugUnavailable);return;}
    for(size_t i=0;i<views.size();++i){const auto &view=views[i];const auto &frame=*view.frame;auto &record=state->frames[frame.slot];const auto code=get(record.code_index);
      if(view.point!=noTaskDebugIndex&&view.point>=uint64_t(state->codes[code].pointCount)){invalid();flags(task.flags,taskDebugUnavailable);return;}
      if(!begin(record.sequence)){flags(task.flags,taskDebugUnavailable);return;}put(record.parent_slot,i?views[i-1].frame->slot:noTaskDebugIndex);put(record.parent_id,i?views[i-1].frame->id:0);put(record.frame_address,address(view.address));put(record.point_index,view.point);put(record.depth,i+1);put(record.flags,view.flags);end(record.sequence);
    }
    put(task.frame_count,views.size());put(task.top_frame_slot,views.empty()?noTaskDebugIndex:views.back().frame->slot);put(task.top_frame_id,views.empty()?0:views.back().frame->id);
    const auto base=get(task.flags)&(taskDebugUnavailable|taskDebugTerminal|taskDebugOriginOmitted);
    put(task.flags,base|(checkpoint?taskDebugAtCheckpoint:taskDebugParked));
    if(checkpoint&&!add(task.checkpoint_sequence)){invalid();flags(task.flags,taskDebugUnavailable);return;}
    if(!end(task.source_sequence)){flags(task.flags,taskDebugUnavailable);return;}
    if(checkpoint&&!views.empty()&&views.back().point!=noTaskDebugIndex){const auto &frame=*views.back().frame;stop={address(&nex_task_debug_catalog_v1),current.slot,current.id,frame.slot,frame.id,views.back().point,get(task.checkpoint_sequence),get(task.source_sequence)};marker=true;}
  }
  if(marker)nex_task_debug_stop_marker(&stop);
  if(checkpoint)taskDebugInvalidate(current);
}
}
extern "C" void nex_task_debug_prepare(const nexrt::TaskDebugCodeSite *codes,int64_t count){
  using namespace nexrt;using namespace nexrt::task_debug_detail;
  try{
    if(auto *old=published.load(std::memory_order_acquire)){if(old->codes==codes&&old->count==uint64_t(count))return;throw DataError("E_DEBUG_INIT","task debugger registry cannot change during execution");}
    validate(codes,count);auto prepared=std::make_unique<State>(codes,size_t(count));auto *state=prepared.get();auto &catalog=nex_task_debug_catalog_v1;
    put(catalog.abi,taskDebugCatalogABI);put(catalog.header_size,sizeof(catalog));put(catalog.task_record_size,sizeof(TaskDebugTaskRecord));put(catalog.frame_record_size,sizeof(TaskDebugFrameRecord));put(catalog.code_record_size,sizeof(TaskDebugCodeSite));put(catalog.point_record_size,sizeof(TaskDebugPoint));put(catalog.binding_record_size,sizeof(TaskDebugBinding));put(catalog.codes_address,address(codes));put(catalog.code_count,count);put(catalog.tasks_address,address(state->tasks.get()));put(catalog.task_capacity,maximumTaskDebugTasks);put(catalog.frames_address,address(state->frames.get()));put(catalog.frame_capacity,maximumTaskDebugFrames);put(catalog.maximum_stack_depth,maximumTaskDebugStack);put(catalog.maximum_locals,maximumTaskDebugLocals);
    storage=std::move(prepared);published.store(state,std::memory_order_release);put(catalog.magic,taskDebugCatalogMagic);
  }catch(const DataError &error){throw Trap(error.code,error.what(),0);}catch(...){throw Trap("E_DEBUG_INIT","task debugger initialization failed before source execution",0);}
}
extern "C" __attribute__((weak,noinline,used)) void nex_task_debug_stop_marker(const nexrt::TaskDebugStop *stop)noexcept{
  asm volatile("" : : "r"(stop) : "memory");
}
