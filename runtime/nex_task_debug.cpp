#include "nex_task_debug.h"
#include "nex_task_frame.h"
#ifdef _WIN32
#include "nex_platform.h"
#endif
#include <algorithm>
#include <array>
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
extern "C" {nexrt::TaskDebugCatalog nex_task_debug_catalog_v1{};nexrt::TaskDebugProviderCatalog nex_task_debug_catalog_v2{};}
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
  TaskDebugCatalog &catalog;
  size_t registryCount=0;
  std::unique_ptr<TaskDebugRegistryRef[]> registries;
  std::unique_ptr<TaskDebugCodeRef[]> references;
  std::array<const TaskDebugCodeSite*,maximumTaskDebugRegistries> bases{};
  std::array<std::array<char,65>,maximumTaskDebugRegistries> components{};
  std::unique_ptr<TaskDebugTaskRecord[]> tasks=std::make_unique<TaskDebugTaskRecord[]>(maximumTaskDebugTasks);
  std::unique_ptr<TaskDebugFrameRecord[]> frames=std::make_unique<TaskDebugFrameRecord[]>(maximumTaskDebugFrames);
  std::unique_ptr<TaskInfo[]> taskInfo=std::make_unique<TaskInfo[]>(maximumTaskDebugTasks);
  std::unique_ptr<FrameInfo[]> frameInfo=std::make_unique<FrameInfo[]>(maximumTaskDebugFrames);
  std::unique_ptr<std::pair<uint64_t,uint64_t>[]> lookup;
  std::atomic_flag mutex=ATOMIC_FLAG_INIT;
  uint64_t taskCount=0,freeFrame=0,nextFrame=1;
  const TaskDebugCodeSite &code(size_t index)const noexcept{return references?*reinterpret_cast<const TaskDebugCodeSite*>(references[index].site_address):codes[index];}
  State(const TaskDebugCodeSite *codes,size_t count,std::span<const TaskDebugCodeRegistry *const> rows={}):codes(codes),count(count),catalog(rows.empty()?nex_task_debug_catalog_v1:nex_task_debug_catalog_v2.base),registryCount(rows.size()),lookup(std::make_unique<std::pair<uint64_t,uint64_t>[]>(count)){
    if(!rows.empty()){
      registries=std::make_unique<TaskDebugRegistryRef[]>(rows.size());references=std::make_unique<TaskDebugCodeRef[]>(count);
      size_t first=0;for(size_t i=0;i<rows.size();++i){const auto &r=*rows[i];registries[i]={address(rows[i]),first,r.count};bases[i]=r.codes;std::memcpy(components[i].data(),r.component,std::strlen(r.component)+1);
        for(size_t j=0;j<r.count;++j)references[first+j]={address(r.codes+j),i};first+=r.count;}
    }
    for(size_t i=0;i<count;++i)lookup[i]={address(code(i).code),i};
    std::sort(lookup.get(),lookup.get()+count);
    for(size_t i=0;i<maximumTaskDebugFrames;++i)frameInfo[i].next=i+1<maximumTaskDebugFrames?i+1:noTaskDebugIndex;
  }
};
struct Lock {State &state;explicit Lock(State &state)noexcept:state(state){while(state.mutex.test_and_set(std::memory_order_acquire)){};}~Lock(){state.mutex.clear(std::memory_order_release);}};
std::unique_ptr<State> storage;
std::atomic<State*> published{nullptr};
thread_local TaskDebugTask current;
void invalid()noexcept{if(auto *state=published.load(std::memory_order_acquire))add(state->catalog.invalid_transitions);}
bool valid(const TaskDebugTask &task)noexcept{return task.owner&&task.slot<maximumTaskDebugTasks&&task.id&&get(task.owner->tasks[task.slot].id)==task.id;}
uint64_t nativeThread()noexcept{
#ifdef __APPLE__
  uint64_t value=0;pthread_threadid_np(nullptr,&value);return value;
#elif defined(__linux__)
  return uint64_t(::syscall(SYS_gettid));
#elif defined(_WIN32)
  return uint64_t(::GetCurrentThreadId());
#else
  return 0;
#endif
}
bool begin(uint64_t &sequence)noexcept{const auto value=get(sequence);if(value>=UINT64_MAX-1){put(sequence,UINT64_MAX);invalid();return false;}if(!(value&1))put(sequence,value+1);return true;}
bool end(uint64_t &sequence)noexcept{const auto value=get(sequence);if(value>=UINT64_MAX-1){put(sequence,UINT64_MAX);invalid();return false;}put(sequence,(value&1)?value+1:value+2);return true;}
struct MetadataBudget {
  size_t text=0,points=0,bindings=0,visible=0,bytes=0,codes=0;
  std::set<const void*> descriptors;
  std::set<std::string> names;
  void string(const char *value,bool required=true){
    if(!value)throw DataError("E_DEBUG_INIT","task debugger text is absent");const auto remaining=maximumTaskDebugTextBytes-text;const auto n=::strnlen(value,remaining);
    if(n>=remaining||(required&&!n))throw DataError("E_DEBUG_INIT","task debugger text exceeds its bound or is empty");text+=n+1;
  }
  void finish(){if(bytes>maximumTaskDebugMetadataBytes||text>maximumTaskDebugMetadataBytes-bytes)throw DataError("E_DEBUG_INIT","task debugger metadata storage exceeds its bound");}
};
void validateCodes(const TaskDebugCodeSite *codes,uint64_t count,MetadataBudget &budget,bool namesUnique=false){
  if(!codes||!count||count>maximumTaskDebugCodes-budget.codes||address(codes)%alignof(TaskDebugCodeSite)||count>(UINTPTR_MAX-address(codes))/sizeof(TaskDebugCodeSite))throw DataError("E_DEBUG_INIT","invalid task debugger code registry");
  budget.codes+=count;budget.bytes+=size_t(count)*sizeof(TaskDebugCodeSite);
  for(uint64_t i=0;i<count;++i){const auto &code=codes[i];
    if(!code.code||address(code.code)%alignof(TaskCodeDescriptor)||!budget.descriptors.insert(code.code).second||code.pointCount<1||code.bindingCount<0||code.visibleCount<0||code.slotCount<0||code.slotCount>65536||!code.points||(!code.bindings&&code.bindingCount)||(!code.visibleBindings&&code.visibleCount))throw DataError("E_DEBUG_INIT","invalid task debugger function metadata");
    const auto &descriptor=*static_cast<const TaskCodeDescriptor*>(code.code);
    if(!validTaskCodeRequirements(descriptor.abi,descriptor.requirements)||descriptor.slotCount!=code.slotCount)throw DataError("E_DEBUG_INIT","task debugger metadata differs from execution descriptor");
    if(uint64_t(code.pointCount)>maximumTaskDebugPoints-budget.points||uint64_t(code.bindingCount)>maximumTaskDebugBindings-budget.bindings||uint64_t(code.visibleCount)>maximumTaskDebugVisibleBindings-budget.visible)throw DataError("E_DEBUG_INIT","task debugger metadata count exceeds its bound");
    budget.points+=size_t(code.pointCount);budget.bindings+=size_t(code.bindingCount);budget.visible+=size_t(code.visibleCount);
    budget.string(code.name);budget.string(code.file);budget.string(code.content);budget.string(code.functionHash);
    if(namesUnique&&!budget.names.insert(code.name).second)throw DataError("E_DEBUG_INIT","duplicate task debugger source function");
    std::set<int64_t> ids;
    for(int64_t j=0;j<code.bindingCount;++j){const auto &binding=code.bindings[j];budget.string(binding.name);budget.string(binding.type);
      if(binding.id<1||!ids.insert(binding.id).second||binding.slot< -1||binding.slot>=code.slotCount||binding.scope<0||(binding.slot<0&&std::strcmp(binding.type,"unit")))throw DataError("E_DEBUG_INIT","invalid task debugger binding metadata");}
    for(int64_t j=0;j<code.pointCount;++j){const auto &point=code.points[j];budget.string(point.site);
      if(point.pc<0||point.pc>=int64_t(maximumTaskDebugPoints)||point.line<1||point.column<1||point.begin<0||point.end<point.begin||point.kind<0||point.kind>int64_t(TaskDebugPointKind::Return)||point.visibleBegin<0||point.visibleCount<0||point.visibleBegin>code.visibleCount||point.visibleCount>code.visibleCount-point.visibleBegin)throw DataError("E_DEBUG_INIT","invalid task debugger source point");
      std::set<int64_t> seen;for(int64_t k=0;k<point.visibleCount;++k){const auto index=code.visibleBindings[point.visibleBegin+k];if(index<0||index>=code.bindingCount||!seen.insert(index).second)throw DataError("E_DEBUG_INIT","invalid task debugger visible binding index");}
    }
  }
}
void finishBudget(MetadataBudget &budget){budget.bytes+=budget.points*sizeof(TaskDebugPoint)+budget.bindings*sizeof(TaskDebugBinding)+budget.visible*sizeof(int64_t);budget.finish();}
void validate(const TaskDebugCodeSite *codes,int64_t count){
  if(count<1)throw DataError("E_DEBUG_INIT","invalid task debugger code registry");MetadataBudget budget;validateCodes(codes,uint64_t(count),budget);finishBudget(budget);
}
std::vector<const TaskDebugCodeRegistry*> validateRegistries(const TaskDebugCodeRegistry *const *rows,int64_t count){
  if(!rows||count<1||uint64_t(count)>maximumTaskDebugRegistries)throw DataError("E_DEBUG_INIT","task debugger accepts at most128 total registries including root");
  std::vector<const TaskDebugCodeRegistry*> result;result.reserve(size_t(count));MetadataBudget budget;budget.bytes=size_t(count)*(sizeof(TaskDebugCodeRegistry)+sizeof(TaskDebugRegistryRef));
  for(int64_t i=0;i<count;++i){const auto *r=rows[i];if(!r||address(r)%alignof(TaskDebugCodeRegistry)||r->abi!=taskDebugRegistryABI||!r->component||::strnlen(r->component,65)>64||!r->component[0]||r->count>maximumTaskDebugCodes||(!r->count&&r->codes))throw DataError("E_DEBUG_INIT","invalid task debugger component registry");
    for(size_t j=0;r->component[j];++j){auto c=r->component[j];if(!((c>='A'&&c<='Z')||(c>='a'&&c<='z')||c=='_'||(j&&c>='0'&&c<='9')))throw DataError("E_DEBUG_INIT","invalid task debugger component identity");}
    budget.string(r->component);if(r->count)validateCodes(r->codes,r->count,budget,true);result.push_back(r);
  }
  std::sort(result.begin(),result.end(),[](auto *a,auto *b){return std::strcmp(a->component,b->component)<0;});
  for(size_t i=0;i<result.size();++i){if(i&&!std::strcmp(result[i-1]->component,result[i]->component))throw DataError("E_DEBUG_INIT","duplicate task debugger component registry");
    if(!result[i]->count)continue;auto first=address(result[i]->codes),last=first+result[i]->count*sizeof(TaskDebugCodeSite);
    for(size_t j=0;j<i;++j)if(result[j]->count){auto from=address(result[j]->codes),to=from+result[j]->count*sizeof(TaskDebugCodeSite);if(first<to&&from<last)throw DataError("E_DEBUG_INIT","overlapping task debugger original site ranges");}
  }
  if(!budget.codes)throw DataError("E_DEBUG_INIT","task debugger application has no retained code");budget.bytes+=budget.codes*sizeof(TaskDebugCodeRef);finishBudget(budget);return result;
}
}
using namespace task_debug_detail;
bool taskDebugEnabled()noexcept{return published.load(std::memory_order_acquire)!=nullptr;}
void taskDebugUnavailableCurrent()noexcept{if(valid(current)){invalid();flags(current.owner->tasks[current.slot].flags,taskDebugUnavailable);taskDebugInvalidate(current);}}
TaskDebugTask taskDebugCreateTask()noexcept{
  auto *state=published.load(std::memory_order_acquire);if(!state)return {};
  Lock lock(*state);if(state->taskCount>=maximumTaskDebugTasks){add(state->catalog.dropped_tasks);return {};}
  const auto slot=state->taskCount++;auto &record=state->tasks[slot];const auto id=slot+1;
  put(record.id,id);put(record.generation,1);put(record.top_frame_slot,noTaskDebugIndex);put(record.flags,taskDebugNotStarted);
  if(valid(current)){put(record.origin_task_id,current.id);const auto &parent=current.owner->tasks[current.slot];const auto origin=get(parent.top_frame_id);put(record.origin_frame_id,origin);if(!origin)flags(record.flags,taskDebugOriginOmitted);}
  put(record.source_sequence,2);put(record.scheduler_sequence,2);put(state->catalog.task_count,state->taskCount);return {state,slot,id};
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
void taskDebugComplete(const TaskDebugTask &task)noexcept{
  if(!valid(task))return;TaskDebugCompletionStop stop{};
  {Lock lock(*task.owner);auto &record=task.owner->tasks[task.slot];
    if(get(record.state)!=uint64_t(TaskDebugState::Terminal)||!(get(record.flags)&taskDebugTerminal)||get(record.frame_count)||get(record.top_frame_id)){invalid();return;}
    end(record.source_sequence);
    stop={address(&task.owner->catalog),task.slot,task.id,get(record.generation)};
  }
  nex_task_debug_completion_marker(&stop);
}
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
  if(state->freeFrame==noTaskDebugIndex||state->nextFrame==std::numeric_limits<uint64_t>::max()){add(state->catalog.dropped_frames);flags(state->tasks[current.slot].flags,taskDebugUnavailable);return;}
  owner=state;slot=state->freeFrame;id=state->nextFrame++;taskId=current.id;auto &info=state->frameInfo[slot];state->freeFrame=info.next;info.used=true;
  auto &record=state->frames[slot];if(!begin(record.sequence)){info.used=false;owner=nullptr;slot=noTaskDebugIndex;id=taskId=0;add(state->catalog.dropped_frames);flags(state->tasks[current.slot].flags,taskDebugUnavailable);return;}put(record.id,id);put(record.task_id,taskId);put(record.parent_slot,noTaskDebugIndex);put(record.parent_id,0);put(record.code_index,codeIndex);put(record.frame_address,0);put(record.point_index,noTaskDebugIndex);put(record.depth,0);put(record.flags,1);end(record.sequence);add(state->catalog.live_frames);
}
void TaskDebugFrame::retire()noexcept{
  if(!owner||!id)return;auto *state=owner;const auto taskSlot=taskId-1;TaskDebugTask task{state,taskSlot,taskId};taskDebugInvalidate(task);Lock lock(*state);
  auto &record=state->frames[slot];if(!state->frameInfo[slot].used||get(record.id)!=id){invalid();}else{begin(record.sequence);put(record.frame_address,0);put(record.flags,1);put(record.id,0);end(record.sequence);state->frameInfo[slot].used=false;state->frameInfo[slot].next=state->freeFrame;state->freeFrame=slot;std::atomic_ref<uint64_t>(state->catalog.live_frames).fetch_sub(1,std::memory_order_relaxed);}
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
      if(view.point!=noTaskDebugIndex&&view.point>=uint64_t(state->code(code).pointCount)){invalid();flags(task.flags,taskDebugUnavailable);return;}
      if(!begin(record.sequence)){flags(task.flags,taskDebugUnavailable);return;}put(record.parent_slot,i?views[i-1].frame->slot:noTaskDebugIndex);put(record.parent_id,i?views[i-1].frame->id:0);put(record.frame_address,address(view.address));put(record.point_index,view.point);put(record.depth,i+1);put(record.flags,view.flags);end(record.sequence);
    }
    put(task.frame_count,views.size());put(task.top_frame_slot,views.empty()?noTaskDebugIndex:views.back().frame->slot);put(task.top_frame_id,views.empty()?0:views.back().frame->id);
    const auto base=get(task.flags)&(taskDebugUnavailable|taskDebugTerminal|taskDebugOriginOmitted);
    put(task.flags,base|(checkpoint?taskDebugAtCheckpoint:taskDebugParked));
    if(checkpoint&&!add(task.checkpoint_sequence)){invalid();flags(task.flags,taskDebugUnavailable);return;}
    if(!end(task.source_sequence)){flags(task.flags,taskDebugUnavailable);return;}
    if(checkpoint&&!views.empty()&&views.back().point!=noTaskDebugIndex){const auto &frame=*views.back().frame;stop={address(&state->catalog),current.slot,current.id,frame.slot,frame.id,views.back().point,get(task.checkpoint_sequence),get(task.source_sequence)};marker=true;}
  }
  if(marker)nex_task_debug_stop_marker(&stop);
  if(checkpoint)taskDebugInvalidate(current);
}
}
namespace nexrt::task_debug_detail {
void publish(std::unique_ptr<State> prepared){
  auto *state=prepared.get();auto &catalog=state->catalog;const bool provider=state->registryCount!=0;
  put(catalog.abi,provider?taskDebugProviderCatalogABI:taskDebugCatalogABI);put(catalog.header_size,provider?sizeof(TaskDebugProviderCatalog):sizeof(TaskDebugCatalog));put(catalog.task_record_size,sizeof(TaskDebugTaskRecord));put(catalog.frame_record_size,sizeof(TaskDebugFrameRecord));put(catalog.code_record_size,sizeof(TaskDebugCodeSite));put(catalog.point_record_size,sizeof(TaskDebugPoint));put(catalog.binding_record_size,sizeof(TaskDebugBinding));put(catalog.codes_address,provider?address(state->references.get()):address(state->codes));put(catalog.code_count,state->count);put(catalog.tasks_address,address(state->tasks.get()));put(catalog.task_capacity,maximumTaskDebugTasks);put(catalog.frames_address,address(state->frames.get()));put(catalog.frame_capacity,maximumTaskDebugFrames);put(catalog.maximum_stack_depth,maximumTaskDebugStack);put(catalog.maximum_locals,maximumTaskDebugLocals);
  if(provider){auto &extra=nex_task_debug_catalog_v2;put(extra.registries_address,address(state->registries.get()));put(extra.registry_count,state->registryCount);put(extra.registry_record_size,sizeof(TaskDebugRegistryRef));put(extra.code_ref_record_size,sizeof(TaskDebugCodeRef));}
  storage=std::move(prepared);published.store(state,std::memory_order_release);put(catalog.magic,provider?taskDebugProviderCatalogMagic:taskDebugCatalogMagic);
}
}
extern "C" void nex_task_debug_prepare(const nexrt::TaskDebugCodeSite *codes,int64_t count){
  using namespace nexrt;using namespace nexrt::task_debug_detail;
  try{
    if(auto *old=published.load(std::memory_order_acquire)){if(!old->registryCount&&old->codes==codes&&old->count==uint64_t(count))return;throw DataError("E_DEBUG_INIT","task debugger registry cannot change during execution");}
    validate(codes,count);publish(std::make_unique<State>(codes,size_t(count)));
  }catch(const DataError &error){throw Trap(error.code,error.what(),0);}catch(...){throw Trap("E_DEBUG_INIT","task debugger initialization failed before source execution",0);}
}
extern "C" void nex_task_debug_prepare_registries(const nexrt::TaskDebugCodeRegistry *const *rows,int64_t count){
  using namespace nexrt;using namespace nexrt::task_debug_detail;
  try{
    auto registries=validateRegistries(rows,count);size_t total=0;for(auto *r:registries)total+=r->count;
    if(auto *old=published.load(std::memory_order_acquire)){
      bool same=old->registryCount==registries.size();if(same)for(size_t i=0;i<registries.size();++i){const auto &r=*registries[i];same&=old->registries[i].registry_address==address(registries[i])&&old->bases[i]==r.codes&&old->registries[i].code_count==r.count&&!std::strcmp(old->components[i].data(),r.component);}
      if(same)return;throw DataError("E_DEBUG_INIT","task debugger registry batch cannot change during execution");
    }
    publish(std::make_unique<State>(nullptr,total,std::span<const TaskDebugCodeRegistry *const>(registries.data(),registries.size())));
  }catch(const DataError &error){throw Trap(error.code,error.what(),0);}catch(...){throw Trap("E_DEBUG_INIT","task debugger registry initialization failed before source execution",0);}
}
extern "C" __attribute__((weak,noinline,used)) void nex_task_debug_stop_marker(const nexrt::TaskDebugStop *stop)noexcept{
#ifdef _WIN32
  // PE does not preempt a DLL definition with the startup host export.
  // Preserve the weak marker observer contract using that explicit export.
  using Observer=void(*)(const nexrt::TaskDebugStop *)noexcept;
  static const auto observer=reinterpret_cast<Observer>(GetProcAddress(GetModuleHandleW(nullptr),"nex_task_debug_stop_marker"));
  if(observer&&observer!=&nex_task_debug_stop_marker)observer(stop);
#endif
  asm volatile("" : : "r"(stop) : "memory");
}
extern "C" __attribute__((weak,noinline,used)) void nex_task_debug_completion_marker(const nexrt::TaskDebugCompletionStop *stop)noexcept{
#ifdef _WIN32
  // PE does not preempt a DLL definition with the startup host export.
  // Preserve the weak marker observer contract using that explicit export.
  using Observer=void(*)(const nexrt::TaskDebugCompletionStop *)noexcept;
  static const auto observer=reinterpret_cast<Observer>(GetProcAddress(GetModuleHandleW(nullptr),"nex_task_debug_completion_marker"));
  if(observer&&observer!=&nex_task_debug_completion_marker)observer(stop);
#endif
  asm volatile("" : : "r"(stop) : "memory");
}
