#include "nex_profile.h"
#include "third_party/tracy/public/tracy/TracyC.h"
#include "third_party/tracy/public/client/TracyProfiler.hpp"
#include <algorithm>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <fstream>
#include <iomanip>
#include <map>
#include <mutex>
#include <sstream>
#include <string>
#include <thread>
#include <unordered_map>
#include <vector>
#include <atomic>
#include <array>
#include <limits>
#include <new>
#include <set>
#include <optional>
#ifdef NEX_TASK_PROFILE_ENABLED
#include "nex_host.h"
#endif

// A final NEX executable supplies the strong exact build identity. A trusted
// native host may omit it; do not fabricate a graph revision for that process.
// Keep this weak default preemptible when the runtime lives in a shared image.
#ifdef NEX_SHARED_PROFILE_RUNTIME
#ifdef NEX_SHARED_WINDOWS_RUNTIME
#include <windows.h>
extern "C" const char *nex_profile_build_info(){
  thread_local bool resolving=false;if(resolving)return nullptr;
  auto function=reinterpret_cast<const char *(*)()>(GetProcAddress(GetModuleHandleW(nullptr),"nex_profile_build_info"));
  if(!function||function==nex_profile_build_info)return nullptr;
  resolving=true;auto result=function();resolving=false;return result;
}
#else
extern "C" __attribute__((weak)) const char *nex_profile_build_info(){return nullptr;}
#endif
#else
// Legacy profile archives retain their strong archived build identity. A weak
// definition here could stop an archive linker extracting that identity unit.
extern "C" const char *nex_profile_build_info();
#endif

namespace {
using Clock=std::chrono::steady_clock;
std::atomic<uint64_t> hookFailures{0};
#ifdef NEX_TASK_PROFILE_ENABLED
std::atomic<bool> taskRoute{false};
std::atomic<nexrt::TaskProfileCollector*> taskCollectorPointer{nullptr};
struct AtomicPool {std::atomic<uint64_t> allocations{0},frees{0},live{0},peak{0},bytes{0},peakBytes{0};};
struct TaskAllocation {std::atomic<uintptr_t> key{0};size_t size=0,site=0;int pool=0;};
struct SiteAllocations {std::atomic<uint64_t> count{0},bytes{0};};
struct TaskMetadata {std::string name,file,content;int64_t line=0;};
constexpr size_t allocationSlots=2097152;
void taskEnter(const char*,const char*,int64_t,const char*)noexcept;
void taskLeave(bool)noexcept;
void taskUnwind(size_t)noexcept;
void taskAllocate(const void*,size_t,int)noexcept;
void taskFree(const void*)noexcept;
#endif
const char *poolName(int pool){return pool?"NEX objects (shallow)":"NEX handles";}
uint64_t limit(const char *key,uint64_t fallback,uint64_t maximum){
  const char *text=std::getenv(key);if(!text||!*text)return fallback;
  uint64_t value=0;for(const char *p=text;*p;++p){if(*p<'0'||*p>'9'||value>(maximum-(*p-'0'))/10)return fallback;value=value*10+(*p-'0');}
  return value<=maximum?value:fallback;
}
std::string quoted(const std::string &text){
  static const char *hex="0123456789abcdef";std::string out="\"";
  for(unsigned char c:text){if(c=='"'||c=='\\'){out+='\\';out+=char(c);}else if(c<32){out+="\\u00";out+=hex[c>>4];out+=hex[c&15];}else out+=char(c);}
  return out+'"';
}
struct Stats {
  std::string name,file,content;int64_t line=0;
  uint64_t calls=0,completed=0,aborted=0,inclusive=0,self=0,maximum=0,allocations=0,allocatedBytes=0;
};
struct Event {Stats *function;uint64_t start,duration,thread;bool aborted;};
struct Pool {uint64_t allocations=0,frees=0,live=0,peak=0,bytes=0,peakBytes=0;};
struct Allocation {size_t size;int pool;uint64_t connection=0;bool sent=false;};
struct State {
  std::mutex mutex;
  std::map<std::string,Stats> functions;
  std::vector<Event> events;
  std::unordered_map<const void*,Allocation> allocations;
  Pool pools[2];
  std::string output,identity;bool enabled=false,tracy=false;
  Clock::time_point origin=Clock::now();
  uint64_t eventLimit=100000,droppedEvents=0,droppedFunctions=0,droppedFrames=0,droppedAllocations=0,untrackedFrees=0,nextThread=0;
#ifdef NEX_TASK_PROFILE_ENABLED
  std::unique_ptr<nexrt::TaskProfileCollector> collector;
  struct ProfileRange {uintptr_t begin=0,end=0;size_t first=0,count=0;std::string component;};
  std::vector<ProfileRange> ranges;size_t siteCount=0;bool providerProfile=false;
  std::vector<TaskMetadata> metadata;std::vector<size_t> siteLookup;
  std::unique_ptr<TaskAllocation[]> taskAllocations;
  std::unique_ptr<SiteAllocations[]> siteAllocations;
  AtomicPool taskPools[2];
  std::atomic<uint64_t> taskAllocationCount{0},taskDroppedAllocations{0},taskUntrackedFrees{0},taskDroppedFunctions{0},taskDroppedFrames{0};
  std::atomic<uint64_t> taskMemoryOverflows{0};
  nexrt::TaskExecutionLimits configured,effective;bool limitsConfigured=false;
  void finishTasks();
#endif
  State();
  uint64_t now()const{return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-origin).count();}
  void finish();
};
State &state(){static auto *value=new State;return *value;}
struct Frame {Stats *function;uint64_t start,children=0;TracyCZoneCtx zone{};};
struct Thread {std::vector<Frame> frames;uint64_t skipped=0,id=0;};
thread_local Thread thread;
void shutdown(){try{state().finish();}catch(...){std::fprintf(stderr,"NEX_PROFILE: could not finish bounded profile report\n");}}
State::State(){
  const char *build=nex_profile_build_info();
  identity=build?build:"null";
  if(auto *path=std::getenv("NEX_PROFILE_OUTPUT"))output=path;
  auto *request=std::getenv("NEX_TRACY");tracy=request&&std::strcmp(request,"1")==0;
  enabled=!output.empty()||tracy;
  eventLimit=limit("NEX_PROFILE_EVENTS",100000,1000000);
  if(tracy){
    ___tracy_startup_profiler();
    auto deadline=Clock::now()+std::chrono::milliseconds(limit("NEX_TRACY_WAIT_MS",5000,60000));
    while(!TracyCIsConnected&&Clock::now()<deadline)std::this_thread::sleep_for(std::chrono::milliseconds(5));
    if(!TracyCIsConnected)std::fprintf(stderr,"NEX_PROFILE: Tracy collector did not connect within the configured wait\n");
    TracyCAppInfo(identity.data(),identity.size());
  }
  origin=Clock::now();
  if(enabled)std::atexit(shutdown);
}
void State::finish(){
#ifdef NEX_TASK_PROFILE_ENABLED
  if(collector){finishTasks();return;}
#endif
  if(!output.empty()){
    std::lock_guard lock(mutex);std::ofstream out(output,std::ios::binary|std::ios::trunc);out<<std::setprecision(17);
    out<<"{\"schema\":\"nex.profile-runtime/1\",\"build\":"<<identity<<",\"clock\":\"steady_wall_nanoseconds\",\"duration_ns\":"<<now()
       <<",\"tracy\":"<<(tracy?"true":"false")<<",\"dropped_events\":"<<droppedEvents<<",\"dropped_functions\":"<<droppedFunctions
       <<",\"dropped_frames\":"<<droppedFrames+hookFailures.load(std::memory_order_relaxed)<<",\"dropped_allocations\":"<<droppedAllocations<<",\"untracked_frees\":"<<untrackedFrees<<",\"functions\":[";
    bool comma=false;for(const auto &[key,f]:functions){
      if(comma)out<<',';comma=true;
      out<<"{\"name\":"<<quoted(f.name)<<",\"file\":"<<quoted(f.file)<<",\"content_hash\":"<<quoted(f.content)<<",\"line\":"<<f.line
         <<",\"calls\":"<<f.calls<<",\"completed\":"<<f.completed<<",\"aborted\":"<<f.aborted<<",\"inclusive_ns\":"<<f.inclusive
         <<",\"self_ns\":"<<f.self<<",\"max_ns\":"<<f.maximum<<",\"allocations\":"<<f.allocations<<",\"allocated_shallow_bytes\":"<<f.allocatedBytes<<'}';
    }
    out<<"],\"memory\":[";
    for(int i=0;i<2;++i){const auto &p=pools[i];if(i)out<<',';
      out<<"{\"pool\":"<<quoted(poolName(i))<<",\"allocations\":"<<p.allocations<<",\"frees\":"<<p.frees<<",\"live\":"<<p.live
         <<",\"peak_live\":"<<p.peak<<",\"live_shallow_bytes\":"<<p.bytes<<",\"peak_shallow_bytes\":"<<p.peakBytes<<'}';
    }
    out<<"],\"traceEvents\":[";comma=false;
    for(const auto &e:events){
      if(comma)out<<',';comma=true;
      out<<"{\"name\":"<<quoted(e.function->name)<<",\"cat\":\"nex.function\",\"ph\":\"X\",\"pid\":1,\"tid\":"<<e.thread
         <<",\"ts\":"<<double(e.start)/1000.0<<",\"dur\":"<<double(e.duration)/1000.0<<",\"args\":{\"content_hash\":"<<quoted(e.function->content)
         <<",\"aborted\":"<<(e.aborted?"true":"false")<<"}}";
    }
    out<<"]}\n";out.flush();if(!out)std::fprintf(stderr,"NEX_PROFILE: could not write profile report\n");
  }
  if(tracy)___tracy_shutdown_profiler();
}
void leave(bool aborted){
  auto &s=state();if(!s.enabled)return;
  if(thread.skipped){--thread.skipped;return;}
  if(thread.frames.empty())return;
  auto end=s.now();auto frame=thread.frames.back();thread.frames.pop_back();auto elapsed=end-frame.start;
  if(!thread.frames.empty())thread.frames.back().children+=elapsed;
  if(s.tracy)TracyCZoneEnd(frame.zone);
  std::lock_guard lock(s.mutex);auto &f=*frame.function;
  ++(aborted?f.aborted:f.completed);f.inclusive+=elapsed;f.self+=elapsed-std::min(elapsed,frame.children);f.maximum=std::max(f.maximum,elapsed);
  if(s.events.size()<s.eventLimit)s.events.push_back({&f,frame.start,elapsed,thread.id,aborted});else ++s.droppedEvents;
}
}
extern "C" void nex_profile_enter(const char *name,const char *file,int64_t line,const char *content){
#ifdef NEX_TASK_PROFILE_ENABLED
  if(taskRoute.load(std::memory_order_acquire)){taskEnter(name,file,line,content);return;}
#endif
  try{
  auto &s=state();if(!s.enabled)return;
  if(thread.skipped||thread.frames.size()>=4096){++thread.skipped;std::lock_guard lock(s.mutex);++s.droppedFrames;return;}
  Stats *function;
  {std::lock_guard lock(s.mutex);
    auto key=std::string(name)+'\n'+file+'\n'+content;
    auto found=s.functions.find(key);
    if(found==s.functions.end()){
      if(s.functions.size()>=16384){++thread.skipped;++s.droppedFunctions;return;}
      found=s.functions.emplace(key,Stats{name,file,content,line}).first;
    }
    function=&found->second;++function->calls;if(!thread.id)thread.id=++s.nextThread;
  }
  TracyCZoneCtx zone{};
  if(s.tracy&&TracyCIsConnected){
    auto source=___tracy_alloc_srcloc_name(uint32_t(line),file,std::strlen(file),name,std::strlen(name),name,std::strlen(name),0);
    zone=___tracy_emit_zone_begin_alloc(source,1);TracyCZoneText(zone,content,std::strlen(content));
  }
  thread.frames.push_back({function,s.now(),0,zone});
  }catch(...){++thread.skipped;hookFailures.fetch_add(1,std::memory_order_relaxed);}
}
extern "C" void nex_profile_leave(){
#ifdef NEX_TASK_PROFILE_ENABLED
  if(taskRoute.load(std::memory_order_acquire)){taskLeave(false);return;}
#endif
  try{leave(false);}catch(...){hookFailures.fetch_add(1,std::memory_order_relaxed);}
}
extern "C" void nex_profile_unwind(){
#ifdef NEX_TASK_PROFILE_ENABLED
  if(taskRoute.load(std::memory_order_acquire)){taskUnwind(std::numeric_limits<size_t>::max());return;}
#endif
  try{thread.skipped=0;while(!thread.frames.empty())leave(true);}catch(...){hookFailures.fetch_add(1,std::memory_order_relaxed);}
}
extern "C" void nex_profile_allocation(const void *pointer,size_t size,int pool){
#ifdef NEX_TASK_PROFILE_ENABLED
  if(taskRoute.load(std::memory_order_acquire)){taskAllocate(pointer,size,pool);return;}
#endif
  try{
  auto &s=state();if(!s.enabled)return;std::lock_guard lock(s.mutex);
  if(s.allocations.size()>=1000000){++s.droppedAllocations;return;}
  uint64_t connection=0;bool sent=s.tracy&&TracyCIsConnected;
  if(sent){connection=tracy::GetProfiler().ConnectionId();TracyCAllocN(pointer,size,poolName(pool));}
  s.allocations.emplace(pointer,Allocation{size,pool,connection,sent});auto &p=s.pools[pool];++p.allocations;++p.live;p.bytes+=size;p.peak=std::max(p.peak,p.live);p.peakBytes=std::max(p.peakBytes,p.bytes);
  if(!thread.frames.empty()){auto &f=*thread.frames.back().function;++f.allocations;f.allocatedBytes+=size;}
  }catch(...){hookFailures.fetch_add(1,std::memory_order_relaxed);}
}
extern "C" void nex_profile_free(const void *pointer){
#ifdef NEX_TASK_PROFILE_ENABLED
  if(taskRoute.load(std::memory_order_acquire)){taskFree(pointer);return;}
#endif
  try{
  auto &s=state();if(!s.enabled)return;std::lock_guard lock(s.mutex);auto found=s.allocations.find(pointer);
  if(found==s.allocations.end()){++s.untrackedFrees;return;}
  const auto allocation=found->second;
  if(allocation.sent&&TracyCIsConnected&&allocation.connection==tracy::GetProfiler().ConnectionId())TracyCFreeN(pointer,poolName(allocation.pool));
  auto &p=s.pools[allocation.pool];++p.frees;--p.live;p.bytes-=allocation.size;s.allocations.erase(found);
  }catch(...){hookFailures.fetch_add(1,std::memory_order_relaxed);}
}

#ifdef NEX_TASK_PROFILE_ENABLED
namespace {
struct HelperFrame {
  nexrt::TaskProfileInvocation invocation;
  alignas(nexrt::TaskProfileSourceSegment) std::byte storage[sizeof(nexrt::TaskProfileSourceSegment)];bool active=false;
  nexrt::TaskProfileSourceSegment *segment()noexcept{return reinterpret_cast<nexrt::TaskProfileSourceSegment*>(storage);}
  ~HelperFrame(){if(active)std::destroy_at(segment());}
};
// Raw TLS slots have no dynamic initialization/destructor registration on the
// first source hook. A turn/source guard closes every constructed helper frame.
// Token/segment construction uses only the already-preallocated collector.
struct HelperSlot {alignas(HelperFrame) std::byte bytes[sizeof(HelperFrame)];};
struct Helpers {
  std::array<HelperSlot,256> frames;size_t depth=0,skipped=0,baseline=0,disabled=0;
  HelperFrame &frame(size_t index)noexcept{return *std::launder(reinterpret_cast<HelperFrame*>(frames[index].bytes));}
};
thread_local Helpers helpers;
uint64_t siteHash(const char *name,const char *file,const char *content)noexcept{
  uint64_t value=UINT64_C(1469598103934665603);
  for(auto *text:{name,file,content}){for(auto *p=reinterpret_cast<const unsigned char*>(text);*p;++p){value^=*p;value*=UINT64_C(1099511628211);}value^=255;value*=UINT64_C(1099511628211);}
  return value;
}
std::optional<size_t> lookupSite(State &s,const char *name,const char *file,const char *content)noexcept{
  if(!name||!file||!content||s.siteLookup.empty())return {};
  const auto mask=s.siteLookup.size()-1;auto at=size_t(siteHash(name,file,content))&mask;
  for(size_t probes=0;probes<s.siteLookup.size();++probes,at=(at+1)&mask){
    const auto value=s.siteLookup[at];if(!value)return {};
    const auto &site=s.metadata[value-1];if(site.name==name&&site.file==file&&site.content==content)return value-1;
  }return {};
}
void taskEnter(const char *name,const char *file,int64_t,const char *content)noexcept{
  auto *collector=taskCollectorPointer.load(std::memory_order_acquire);if(!collector||helpers.disabled)return;
  auto &s=state();
  if(helpers.skipped||helpers.depth>=helpers.frames.size()){++helpers.skipped;s.taskDroppedFrames.fetch_add(1,std::memory_order_relaxed);return;}
  auto &frame=*new(helpers.frames[helpers.depth++].bytes)HelperFrame;const auto site=lookupSite(s,name,file,content);
  if(!site){s.taskDroppedFunctions.fetch_add(1,std::memory_order_relaxed);return;}
  frame.invocation=collector->invocation(*site);
  if(frame.invocation){new(frame.storage)nexrt::TaskProfileSourceSegment(collector->source(frame.invocation));frame.active=true;}
}
void taskLeave(bool aborted)noexcept{
  if(!taskCollectorPointer.load(std::memory_order_acquire)||helpers.disabled)return;
  if(helpers.skipped){--helpers.skipped;return;}if(!helpers.depth)return;
  auto &frame=helpers.frame(--helpers.depth);
  if(frame.active){std::destroy_at(frame.segment());frame.active=false;}
  if(aborted)frame.invocation.abort();else frame.invocation.complete();
  std::destroy_at(&frame);
}
void taskUnwind(size_t baseline)noexcept{
  if(!taskCollectorPointer.load(std::memory_order_acquire))return;
  if(baseline==std::numeric_limits<size_t>::max())baseline=helpers.baseline;
  helpers.skipped=0;
  const auto disabled=std::exchange(helpers.disabled,0);
  while(helpers.depth>baseline)taskLeave(true);
  helpers.disabled=disabled;
}
void peak(std::atomic<uint64_t> &destination,uint64_t value)noexcept{
  auto previous=destination.load(std::memory_order_relaxed);while(previous<value&&!destination.compare_exchange_weak(previous,value,std::memory_order_relaxed)){}
}
uint64_t memoryAdd(State &s,std::atomic<uint64_t> &destination,uint64_t amount=1)noexcept{
  auto previous=destination.load(std::memory_order_relaxed);
  for(;;){const bool overflow=amount>std::numeric_limits<uint64_t>::max()-previous;
    const auto next=overflow?std::numeric_limits<uint64_t>::max():previous+amount;
    if(destination.compare_exchange_weak(previous,next,std::memory_order_relaxed)){
      if(overflow)s.taskMemoryOverflows.fetch_add(1,std::memory_order_relaxed);return next;
    }
  }
}
void memorySubtract(State &s,std::atomic<uint64_t> &destination,uint64_t amount)noexcept{
  auto previous=destination.load(std::memory_order_relaxed);
  for(;;){const bool overflow=previous<amount;const auto next=overflow?0:previous-amount;
    if(destination.compare_exchange_weak(previous,next,std::memory_order_relaxed)){
      if(overflow)s.taskMemoryOverflows.fetch_add(1,std::memory_order_relaxed);return;
    }
  }
}
size_t addressHash(uintptr_t key)noexcept{key^=key>>33;key*=UINT64_C(0xff51afd7ed558ccd);key^=key>>33;return size_t(key)&(allocationSlots-1);}
void taskAllocate(const void *pointer,size_t bytes,int pool)noexcept{
  if(!taskCollectorPointer.load(std::memory_order_acquire))return;
  auto &s=state();const auto key=reinterpret_cast<uintptr_t>(pointer);
  if(key<=2||pool<0||pool>1){s.taskDroppedAllocations.fetch_add(1,std::memory_order_relaxed);return;}
  if(s.taskAllocationCount.fetch_add(1,std::memory_order_relaxed)>=1000000){s.taskAllocationCount.fetch_sub(1,std::memory_order_relaxed);s.taskDroppedAllocations.fetch_add(1,std::memory_order_relaxed);return;}
  auto at=addressHash(key);
  for(size_t probes=0;probes<allocationSlots;++probes,at=(at+1)&(allocationSlots-1)){
    auto &entry=s.taskAllocations[at];auto previous=entry.key.load(std::memory_order_acquire);
    if(previous<=1&&entry.key.compare_exchange_strong(previous,2,std::memory_order_acq_rel)){
      entry.size=bytes;entry.pool=pool;entry.site=helpers.disabled?std::numeric_limits<size_t>::max():nexrt::currentTaskProfileSite();
      auto &p=s.taskPools[pool];memoryAdd(s,p.allocations);
      peak(p.peak,memoryAdd(s,p.live));peak(p.peakBytes,memoryAdd(s,p.bytes,bytes));
      if(entry.site<s.siteCount){memoryAdd(s,s.siteAllocations[entry.site].count);memoryAdd(s,s.siteAllocations[entry.site].bytes,bytes);}
      entry.key.store(key,std::memory_order_release);return;
    }
  }
  s.taskAllocationCount.fetch_sub(1,std::memory_order_relaxed);s.taskDroppedAllocations.fetch_add(1,std::memory_order_relaxed);
}
void taskFree(const void *pointer)noexcept{
  if(!taskCollectorPointer.load(std::memory_order_acquire))return;
  auto &s=state();const auto key=reinterpret_cast<uintptr_t>(pointer);auto at=addressHash(key);
  for(size_t probes=0;probes<allocationSlots;++probes,at=(at+1)&(allocationSlots-1)){
    auto &entry=s.taskAllocations[at];auto found=entry.key.load(std::memory_order_acquire);
    if(found==0)break;
    if(found==key&&entry.key.compare_exchange_strong(found,2,std::memory_order_acq_rel)){
      auto &p=s.taskPools[entry.pool];memoryAdd(s,p.frees);memorySubtract(s,p.live,1);memorySubtract(s,p.bytes,entry.size);
      s.taskAllocationCount.fetch_sub(1,std::memory_order_relaxed);entry.key.store(1,std::memory_order_release);return;
    }
  }
  s.taskUntrackedFrees.fetch_add(1,std::memory_order_relaxed);
}
}
namespace {
void prepareTaskProfiles(const nexrt::TaskProfileCodeRegistry *const *registries,int64_t registryCount,bool providers){
  taskRoute.store(true,std::memory_order_release);
  if(auto *tracy=std::getenv("NEX_TRACY");tracy&&std::strcmp(tracy,"1")==0)throw nexrt::DataError("E_TASK_PROFILE","task Tracy capture remains pending; use a local task profile report");
  if(registryCount<=0||registryCount>int64_t(nexrt::maximumTaskProfileRegistries)||!registries)throw nexrt::DataError("E_PROFILE_INIT","invalid task profile registry count");
  std::array<const nexrt::TaskProfileCodeRegistry*,nexrt::maximumTaskProfileRegistries> ordered{};size_t total=0;
  for(int64_t i=0;i<registryCount;++i){const auto *r=registries[i];
    if(!r||r->abi!=nexrt::taskProfileRegistryABI||r->count<=0||size_t(r->count)>nexrt::maximumTaskProfileCodeSites-total||!r->sites||reinterpret_cast<uintptr_t>(r->sites)%alignof(nexrt::TaskProfileCodeSite)||!r->component)throw nexrt::DataError("E_PROFILE_INIT","invalid task profile registry ABI/range");
    size_t n=0;for(;n<65&&r->component[n];++n){const auto c=r->component[n];if(!((c>='a'&&c<='z')||(c>='A'&&c<='Z')||c=='_'||(n&&c>='0'&&c<='9')))throw nexrt::DataError("E_PROFILE_INIT","invalid task profile component");}
    if(!n||n>64)throw nexrt::DataError("E_PROFILE_INIT","invalid task profile component length");
    const auto begin=reinterpret_cast<uintptr_t>(r->sites);const auto bytes=size_t(r->count)*sizeof(nexrt::TaskProfileCodeSite);
    if(bytes>std::numeric_limits<uintptr_t>::max()-begin)throw nexrt::DataError("E_PROFILE_INIT","task profile range overflows");
    for(int64_t j=0;j<i;++j){const auto *q=ordered[j];const auto other=reinterpret_cast<uintptr_t>(q->sites);const auto end=other+size_t(q->count)*sizeof(nexrt::TaskProfileCodeSite);
      if(!std::strcmp(q->component,r->component)||(begin<end&&other<begin+bytes))throw nexrt::DataError("E_PROFILE_INIT","duplicate or overlapping task profile registry");}
    ordered[i]=r;total+=size_t(r->count);
  }
  std::sort(ordered.begin(),ordered.begin()+registryCount,[](auto *a,auto *b){return std::strcmp(a->component,b->component)<0;});
  const auto *output=std::getenv("NEX_PROFILE_OUTPUT");if(!output||!*output)return;
  try{
    auto &s=state();if(s.collector){
      if(s.providerProfile!=providers||s.ranges.size()!=size_t(registryCount))throw nexrt::DataError("E_PROFILE_INIT","task profile registry cannot change during execution");
      for(int64_t i=0;i<registryCount;++i)if(s.ranges[i].begin!=reinterpret_cast<uintptr_t>(ordered[i]->sites)||s.ranges[i].count!=size_t(ordered[i]->count)||s.ranges[i].component!=ordered[i]->component)throw nexrt::DataError("E_PROFILE_INIT","task profile registry cannot change during execution");return;
    }
    // Build temporary metadata first. A failed initialization cannot leave a
    // partially appended catalog that a later attempt mistakes for complete.
    std::vector<TaskMetadata> metadata;metadata.reserve(total);std::vector<State::ProfileRange> ranges;ranges.reserve(registryCount);size_t textBytes=0;std::set<std::string> names;
    for(int64_t r=0;r<registryCount;++r){const auto &registry=*ordered[r];auto begin=reinterpret_cast<uintptr_t>(registry.sites);
      ranges.push_back({begin,begin+size_t(registry.count)*sizeof(nexrt::TaskProfileCodeSite),metadata.size(),size_t(registry.count),registry.component});
      for(int64_t i=0;i<registry.count;++i){const auto &source=registry.sites[i];TaskMetadata site;
        auto copy=[&](const char *text){if(!text)throw nexrt::DataError("E_PROFILE_INIT","task profile site string is absent");size_t n=0;while(n<nexrt::maximumTaskProfileCodeTextBytes-textBytes&&text[n])++n;if(n==nexrt::maximumTaskProfileCodeTextBytes-textBytes)throw nexrt::DataError("E_PROFILE_INIT","task profile site text exceeds its bound");textBytes+=n+1;return std::string(text,n);};
        site.name=copy(source.name);site.file=copy(source.file);site.content=copy(source.content);site.line=source.line;
        if(site.name.empty()||site.content.empty()||site.line<0||!names.insert(site.name).second)throw nexrt::DataError("E_PROFILE_INIT","invalid or duplicate task profile source identity");metadata.push_back(std::move(site));
      }
    }
    size_t lookupSize=1;while(lookupSize<total*2)lookupSize*=2;std::vector<size_t> lookup(lookupSize);
    std::vector<nexrt::TaskProfileSite> registration;registration.reserve(total);
    for(size_t i=0;i<total;++i){const auto &site=metadata[i];auto at=size_t(siteHash(site.name.c_str(),site.file.c_str(),site.content.c_str()))&(lookupSize-1);while(lookup[at])at=(at+1)&(lookupSize-1);lookup[at]=i+1;registration.push_back({site.name,site.file,site.content,site.line});}
    auto allocations=std::make_unique<TaskAllocation[]>(allocationSlots);auto siteAllocations=std::make_unique<SiteAllocations[]>(total);
    nexrt::TaskProfileOptions options;options.limits.events=s.eventLimit;auto collector=std::make_unique<nexrt::TaskProfileCollector>(options,registration);
    s.metadata=std::move(metadata);s.ranges=std::move(ranges);s.siteLookup=std::move(lookup);s.taskAllocations=std::move(allocations);s.siteAllocations=std::move(siteAllocations);s.siteCount=total;s.providerProfile=providers;s.collector=std::move(collector);
    taskCollectorPointer.store(s.collector.get(),std::memory_order_release);
  }catch(const nexrt::DataError&){throw;}catch(...){throw nexrt::DataError("E_PROFILE_INIT","task profiler preallocation failed before source execution");}
}
}
extern "C" void nex_task_profile_prepare(const nexrt::TaskProfileCodeSite *sites,int64_t count){
  // This executes inside the application wrapper but before its root request.
  // Preserve the specific initialization diagnostic at that C ABI boundary;
  // an escaping DataError would be reduced to generic E_RUNTIME by the wrapper.
  const nexrt::TaskProfileCodeRegistry registry{nexrt::taskProfileRegistryABI,sites,count,"standalone"};const auto *pointer=&registry;
  try{prepareTaskProfiles(&pointer,1,false);}
  catch(const nexrt::DataError &error){throw nexrt::Trap(error.code,error.what(),0);}
}
extern "C" void nex_task_profile_prepare_registries(const nexrt::TaskProfileCodeRegistry *const *registries,int64_t count){
  try{prepareTaskProfiles(registries,count,true);}
  catch(const nexrt::DataError &error){throw nexrt::Trap(error.code,error.what(),0);}
}
namespace nexrt {
TaskProfileCollector *taskProfileCollector()noexcept{return taskCollectorPointer.load(std::memory_order_acquire);}
std::optional<size_t> taskProfileSiteIndex(const TaskProfileCodeSite *site)noexcept{
  if(!taskProfileCollector()||!site)return {};
  const auto at=reinterpret_cast<uintptr_t>(site);
  for(const auto &range:state().ranges)if(at>=range.begin&&at-range.begin<range.end-range.begin&&(at-range.begin)%sizeof(TaskProfileCodeSite)==0)return range.first+(at-range.begin)/sizeof(TaskProfileCodeSite);
  return {};
}
void taskProfileLimits(const TaskExecutionLimits &configured,const TaskExecutionLimits &effective)noexcept{if(taskProfileCollector()){auto &s=state();s.configured=configured;s.effective=effective;s.limitsConfigured=true;}}
void taskProfileEffectiveLimits(const TaskExecutionLimits &effective)noexcept{if(taskProfileCollector()){auto &s=state();s.effective=effective;if(!s.limitsConfigured)s.configured=effective;}}
TaskProfileSourceScope::TaskProfileSourceScope(const TaskProfileInvocation &invocation)noexcept{
  if(auto *collector=taskProfileCollector()){
    baseline=helpers.depth;
    if(invocation){new(storage)TaskProfileSourceSegment(collector->source(invocation));active=true;}
    else{++helpers.disabled;disabled=true;}
  }
}
TaskProfileSourceScope::~TaskProfileSourceScope(){
  if(active||disabled)taskUnwind(baseline);
  if(active)std::destroy_at(reinterpret_cast<TaskProfileSourceSegment*>(storage));
  if(disabled)--helpers.disabled;
}
TaskProfileTurnScope::TaskProfileTurnScope(const TaskProfileTask &input,bool countResume)noexcept{
  collector=taskProfileCollector();if(!collector)return;
  task=&input;baseline=helpers.depth;priorBaseline=helpers.baseline;helpers.baseline=baseline;
  new(storage)TaskProfileResumeGuard(collector->resume(input,countResume));active=true;start=collector->sample();
}
TaskProfileTurnScope::~TaskProfileTurnScope(){
  if(!active)return;
  taskUnwind(baseline);helpers.baseline=priorBaseline;
  if(*task)collector->executor(*task,start,collector->sample());
  std::destroy_at(reinterpret_cast<TaskProfileResumeGuard*>(storage));
}
TaskProfileRetirementScope::TaskProfileRetirementScope(const TaskProfileTask &input)noexcept{
  if(!input||currentTaskProfileTask())return;
  collector=taskProfileCollector();if(!collector)return;
  task=&input;start=collector->sample();
}
TaskProfileRetirementScope::~TaskProfileRetirementScope(){
  if(task)collector->executor(*task,start,collector->sample());
}
}
namespace {
const char *boolean(bool value){return value?"true":"false";}
const char *invocationOutcome(nexrt::TaskProfileInvocationOutcome value){return value==nexrt::TaskProfileInvocationOutcome::Completed?"completed":value==nexrt::TaskProfileInvocationOutcome::Aborted?"aborted":"active";}
const char *taskOutcome(nexrt::TaskProfileTaskOutcome value){return value==nexrt::TaskProfileTaskOutcome::Completed?"completed":value==nexrt::TaskProfileTaskOutcome::Aborted?"aborted":"cancelled";}
void limitsJSON(std::ostream &out,const nexrt::TaskExecutionLimits &limits){out<<"{\"steps\":"<<limits.steps<<",\"timeout_ms\":"<<limits.timeoutMs<<",\"workers\":"<<limits.workers<<'}';}
}
void State::finishTasks(){
  if(output.empty())return;
  const auto snapshot=collector->snapshot();
  constexpr size_t byteLimit=64*1024*1024;
  uint64_t extraDrops=0,serializationOverflows=0;bool numericOverflow=false;
  // Inspect every exported scalar before deriving flags. Serialization below is
  // pure: a late memory field cannot invalidate an already-written clean flag.
  auto inspect=[&](uint64_t value){if(value>uint64_t(std::numeric_limits<int64_t>::max())){numericOverflow=true;++serializationOverflows;}};
  auto number=[](uint64_t value){return std::min(value,uint64_t(std::numeric_limits<int64_t>::max()));};
  const auto functionsDropped=taskDroppedFunctions.load(),framesDropped=taskDroppedFrames.load();
  const auto allocationsDropped=taskDroppedAllocations.load()+hookFailures.load(),freesUntracked=taskUntrackedFrees.load(),memoryOverflows=taskMemoryOverflows.load();
  const uint64_t duration=now();inspect(duration);
  std::array<Pool,2> memoryPools;
  for(size_t i=0;i<2;++i){const auto &p=taskPools[i];memoryPools[i]={p.allocations.load(),p.frees.load(),p.live.load(),p.peak.load(),p.bytes.load(),p.peakBytes.load()};for(auto value:{memoryPools[i].allocations,memoryPools[i].frees,memoryPools[i].live,memoryPools[i].peak,memoryPools[i].bytes,memoryPools[i].peakBytes})inspect(value);}
  for(auto value:{snapshot.drops.tasks,snapshot.drops.invocations,snapshot.drops.events,snapshot.drops.guards,snapshot.drops.suppressedHooks,snapshot.drops.invalidTransitions,snapshot.drops.clockFailures,snapshot.drops.counterOverflows,functionsDropped,framesDropped,allocationsDropped,freesUntracked,memoryOverflows})inspect(value);
  for(size_t i=0;i<snapshot.functions.size();++i){const auto &f=snapshot.functions[i];for(auto value:{f.calls,f.completed,f.aborted,f.inclusiveCpuNs,f.selfCpuNs,f.activeElapsedNs,f.selfActiveElapsedNs,f.lifetimeNs,f.maxLifetimeNs,siteAllocations[i].count.load(),siteAllocations[i].bytes.load()})inspect(value);}
  for(const auto &t:snapshot.tasks)for(auto value:{t.id,t.spawningInvocationId,t.createdWallNs,t.terminalWallNs,t.resumes,t.migrations,t.lastThreadId,t.sourceCpuNs,t.sourceElapsedNs,t.activeInvocations,t.readyNs,t.blockedFutureNs,t.blockedSendNs,t.blockedReceiveNs,t.blockedScopeNs,t.blockedExternalNs,t.drainNs,t.executorCpuNs,t.executorElapsedNs})inspect(value);
  for(const auto &f:snapshot.invocations)for(auto value:{f.id,f.taskId,f.parentId,f.startWallNs,f.endWallNs,f.inclusiveCpuNs,f.selfCpuNs,f.activeElapsedNs,f.selfActiveElapsedNs,f.lifetimeNs})inspect(value);
  for(const auto &f:snapshot.segments)for(auto value:{f.taskId,f.invocationId,f.threadId,f.startWallNs,f.elapsedNs,f.cpuNs})inspect(value);
  // Adapter backing capacities are separate gauges, not an additive RAM
  // total. Text capacity may include inline string storage already represented
  // in a shallow record. Keep standalone schema2's memory object unchanged.
  std::array<uint64_t,6> adapterCapacity{};
  if(providerProfile){
    auto product=[](size_t count,size_t width){return width&&count>std::numeric_limits<uint64_t>::max()/width?std::numeric_limits<uint64_t>::max():uint64_t(count)*width;};
    auto add=[](uint64_t &to,size_t value){to=value>std::numeric_limits<uint64_t>::max()-to?std::numeric_limits<uint64_t>::max():to+value;};
    adapterCapacity[0]=ranges.capacity();adapterCapacity[1]=product(ranges.capacity(),sizeof(ProfileRange));
    for(const auto &r:ranges){add(adapterCapacity[2],r.component.capacity());add(adapterCapacity[2],1);}
    adapterCapacity[3]=product(metadata.capacity(),sizeof(TaskMetadata));
    for(const auto &m:metadata)for(const auto *text:{&m.name,&m.file,&m.content}){add(adapterCapacity[4],text->capacity());add(adapterCapacity[4],1);}
    adapterCapacity[5]=product(siteLookup.capacity(),sizeof(size_t));for(auto value:adapterCapacity)inspect(value);
  }
  bool aggregates=!snapshot.drops.tasks&&!snapshot.drops.invocations&&!snapshot.drops.guards&&!snapshot.drops.suppressedHooks&&!snapshot.drops.invalidTransitions&&!snapshot.drops.counterOverflows&&!functionsDropped&&!framesDropped&&!hookFailures.load()&&!memoryOverflows;
  bool memory=!allocationsDropped&&!freesUntracked&&!memoryOverflows,cpu=!snapshot.drops.counterOverflows,elapsed=cpu,lifetime=cpu;
  std::ostringstream functionText;functionText<<'[';
  for(size_t i=0;i<snapshot.functions.size();++i){const auto &f=snapshot.functions[i];if(i)functionText<<',';
    aggregates&=f.calls==f.completed+f.aborted;cpu&=f.cpuAvailable;elapsed&=f.elapsedAvailable;lifetime&=f.lifetimeAvailable;
    functionText<<"{\"name\":"<<quoted(f.name)<<",\"file\":"<<quoted(f.file)<<",\"content_hash\":"<<quoted(f.content)<<",\"line\":"<<f.line
      <<",\"calls\":"<<number(f.calls)<<",\"completed\":"<<number(f.completed)<<",\"aborted\":"<<number(f.aborted)
      <<",\"inclusive_cpu_ns\":"<<number(f.inclusiveCpuNs)<<",\"self_cpu_ns\":"<<number(f.selfCpuNs)
      <<",\"active_elapsed_ns\":"<<number(f.activeElapsedNs)<<",\"self_active_elapsed_ns\":"<<number(f.selfActiveElapsedNs)
      <<",\"lifetime_ns\":"<<number(f.lifetimeNs)<<",\"max_lifetime_ns\":"<<number(f.maxLifetimeNs)
      <<",\"cpu_available\":"<<boolean(f.cpuAvailable)<<",\"elapsed_available\":"<<boolean(f.elapsedAvailable)<<",\"lifetime_available\":"<<boolean(f.lifetimeAvailable)
      <<",\"allocations\":"<<number(siteAllocations[i].count.load())<<",\"allocated_shallow_bytes\":"<<number(siteAllocations[i].bytes.load())<<'}';
  }functionText<<']';const auto functionsJSON=functionText.str();
  // Conservative fixed record allowance keeps trace serialization below its
  // byte bound before producing any JSON. Metadata is never silently truncated.
  size_t estimatedBase=functionsJSON.size()+snapshot.tasks.size()*1024+identity.size()+16384;
  if(estimatedBase>=byteLimit)throw std::runtime_error("task profile metadata exceeds bounded report size");
  const size_t keepInvocations=std::min({snapshot.invocations.size(),size_t(65536),(byteLimit-estimatedBase)/1024});
  if(keepInvocations<snapshot.invocations.size()){extraDrops+=snapshot.invocations.size()-keepInvocations;serializationOverflows+=keepInvocations< std::min(snapshot.invocations.size(),size_t(65536));}
  std::set<uint64_t> retained;
  for(size_t i=0;i<keepInvocations;++i)retained.insert(snapshot.invocations[i].id);
  std::ostringstream invocationText;invocationText<<'[';
  for(size_t i=0;i<keepInvocations;++i){const auto &f=snapshot.invocations[i];if(i)invocationText<<',';const bool omit=f.parentId&&!retained.contains(f.parentId);if(omit)++extraDrops;
    invocationText<<"{\"id\":"<<number(f.id)<<",\"task_id\":"<<number(f.taskId)<<",\"parent_id\":"<<number(omit?0:f.parentId)<<",\"parent_omitted\":"<<boolean(omit)
      <<",\"site\":"<<f.site<<",\"outcome\":"<<quoted(invocationOutcome(f.outcome))<<",\"start_wall_ns\":"<<number(f.startWallNs)<<",\"end_wall_ns\":"<<number(f.endWallNs)
      <<",\"inclusive_cpu_ns\":"<<number(f.inclusiveCpuNs)<<",\"self_cpu_ns\":"<<number(f.selfCpuNs)<<",\"active_elapsed_ns\":"<<number(f.activeElapsedNs)
      <<",\"self_active_elapsed_ns\":"<<number(f.selfActiveElapsedNs)<<",\"lifetime_ns\":"<<number(f.lifetimeNs)
      <<",\"cpu_available\":"<<boolean(f.cpuAvailable)<<",\"elapsed_available\":"<<boolean(f.elapsedAvailable)<<",\"lifetime_available\":"<<boolean(f.lifetimeAvailable)<<'}';
  }invocationText<<']';const auto invocationsJSON=invocationText.str();
  std::ostringstream taskText;taskText<<'[';uint64_t origin=0;
  for(size_t i=0;i<snapshot.tasks.size();++i){const auto &t=snapshot.tasks[i];if(i)taskText<<',';const bool omit=t.spawningInvocationId&&!retained.contains(t.spawningInvocationId);if(omit)++extraDrops;
    if(!origin||t.createdWallNs<origin)origin=t.createdWallNs;
    aggregates&=t.terminal&&!t.activeInvocations;cpu&=t.executorCpuAvailable;elapsed&=t.schedulerElapsedAvailable;
    taskText<<"{\"id\":"<<number(t.id)<<",\"spawning_invocation_id\":"<<number(omit?0:t.spawningInvocationId)<<",\"spawn_origin_omitted\":"<<boolean(omit)
      <<",\"created_wall_ns\":"<<number(t.createdWallNs)<<",\"terminal_wall_ns\":"<<number(t.terminalWallNs)<<",\"resumes\":"<<number(t.resumes)<<",\"migrations\":"<<number(t.migrations)
      <<",\"last_thread_id\":"<<number(t.lastThreadId)<<",\"source_cpu_ns\":"<<number(t.sourceCpuNs)<<",\"source_elapsed_ns\":"<<number(t.sourceElapsedNs)<<",\"active_invocations\":"<<number(t.activeInvocations)
      <<",\"started\":"<<boolean(t.started)<<",\"cancelled_before_start\":"<<boolean(t.cancelledBeforeStart)<<",\"terminal\":"<<boolean(t.terminal)<<",\"outcome\":"<<quoted(taskOutcome(t.outcome))
      <<",\"ready_ns\":"<<number(t.readyNs)<<",\"blocked_future_ns\":"<<number(t.blockedFutureNs)<<",\"blocked_send_ns\":"<<number(t.blockedSendNs)<<",\"blocked_receive_ns\":"<<number(t.blockedReceiveNs)
      <<",\"blocked_scope_ns\":"<<number(t.blockedScopeNs)<<",\"blocked_external_ns\":"<<number(t.blockedExternalNs)<<",\"drain_ns\":"<<number(t.drainNs)
      <<",\"executor_cpu_ns\":"<<number(t.executorCpuNs)<<",\"executor_elapsed_ns\":"<<number(t.executorElapsedNs)<<",\"executor_cpu_available\":"<<boolean(t.executorCpuAvailable)<<",\"scheduler_elapsed_available\":"<<boolean(t.schedulerElapsedAvailable)<<'}';
  }taskText<<']';const auto tasksJSON=taskText.str();
  const size_t used=functionsJSON.size()+invocationsJSON.size()+tasksJSON.size()+identity.size()+16384;
  const size_t available=used<byteLimit?byteLimit-used:0;
  const size_t segmentLimit=std::min(size_t(1000000),available/512);
  std::ostringstream segmentText;segmentText<<'[';size_t segmentCount=0;
  for(const auto &f:snapshot.segments){
    if(!retained.contains(f.invocationId)||segmentCount>=segmentLimit){++extraDrops;continue;}
    if(segmentCount++)segmentText<<',';
    segmentText<<"{\"task_id\":"<<number(f.taskId)<<",\"invocation_id\":"<<number(f.invocationId)<<",\"thread_id\":"<<number(f.threadId)
      <<",\"start_wall_ns\":"<<number(f.startWallNs)<<",\"elapsed_ns\":"<<number(f.elapsedNs)<<",\"cpu_ns\":"<<number(f.cpuNs)
      <<",\"elapsed_available\":"<<boolean(f.elapsedAvailable)<<",\"cpu_available\":"<<boolean(f.cpuAvailable)<<'}';
  }segmentText<<']';if(segmentCount>=segmentLimit&&segmentCount<snapshot.segments.size())++serializationOverflows;
  const auto segmentsJSON=segmentText.str();
  if(numericOverflow){aggregates=false;memory=false;cpu=false;elapsed=false;lifetime=false;}
  const bool timeline=!snapshot.drops.events&&!extraDrops&&!serializationOverflows&&aggregates;
  std::ostringstream out;out<<"{\"schema\":"<<quoted(providerProfile?"nex.profile-runtime/3":"nex.profile-runtime/2")<<",\"kind\":\"native_tasks\",\"build\":"<<identity<<",\"clock\":\"steady_wall_and_thread_cpu_nanoseconds\",\"duration_ns\":"<<number(duration)
    <<",\"origin_wall_ns\":"<<number(origin)<<",\"tracy\":false,\"incomplete\":"<<boolean(!(aggregates&&timeline&&memory&&cpu&&elapsed&&lifetime))
    <<",\"completeness\":{\"aggregates\":"<<boolean(aggregates)<<",\"timeline\":"<<boolean(timeline)<<",\"memory\":"<<boolean(memory)<<",\"cpu\":"<<boolean(cpu)<<",\"elapsed\":"<<boolean(elapsed)<<",\"lifetime\":"<<boolean(lifetime)<<'}'
    <<",\"dropped_events\":"<<number(snapshot.drops.events+extraDrops)<<",\"dropped_functions\":"<<number(functionsDropped)<<",\"dropped_frames\":"<<number(framesDropped)
    <<",\"dropped_allocations\":"<<number(allocationsDropped)<<",\"untracked_frees\":"<<number(freesUntracked)<<",\"dropped_tasks\":"<<number(snapshot.drops.tasks)
    <<",\"dropped_invocations\":"<<number(snapshot.drops.invocations)<<",\"dropped_guards\":"<<number(snapshot.drops.guards)<<",\"suppressed_hooks\":"<<number(snapshot.drops.suppressedHooks)
    <<",\"invalid_transitions\":"<<number(snapshot.drops.invalidTransitions)<<",\"clock_failures\":"<<number(snapshot.drops.clockFailures)<<",\"counter_overflows\":"<<number(snapshot.drops.counterOverflows+memoryOverflows)
    <<",\"serialization_overflows\":"<<number(serializationOverflows)
    <<",\"limits\":{\"events\":"<<eventLimit<<",\"sites\":16384,\"tasks\":4096,\"active_invocations\":65536,\"guards_per_thread\":4096,\"live_allocations\":1000000,\"report_bytes\":"<<byteLimit<<'}'
    <<",\"collector_memory\":{\"storage_bytes\":"<<snapshot.collectorStorageBytes<<",\"site_text_storage_bytes\":"<<snapshot.siteTextStorageBytes<<",\"address_slots\":"<<allocationSlots<<",\"address_storage_bytes\":"<<allocationSlots*sizeof(TaskAllocation);
  if(providerProfile){const char *keys[]={"registry_record_capacity","registry_record_capacity_bytes","registry_component_text_capacity_bytes","metadata_record_capacity_bytes","metadata_text_capacity_bytes","site_lookup_capacity_bytes"};for(size_t i=0;i<adapterCapacity.size();++i)out<<','<<quoted(keys[i])<<':'<<number(adapterCapacity[i]);}
  out<<'}'<<",\"task_execution\":{\"configured\":";limitsJSON(out,configured);out<<",\"effective\":";limitsJSON(out,effective);out<<",\"executor_workers\":"<<effective.workers<<'}'
    <<",\"functions\":"<<functionsJSON<<",\"tasks\":"<<tasksJSON<<",\"invocations\":"<<invocationsJSON<<",\"segments\":"<<segmentsJSON<<",\"memory\":[";
  for(size_t i=0;i<2;++i){const auto &p=memoryPools[i];if(i)out<<',';out<<"{\"pool\":"<<quoted(poolName(i))<<",\"allocations\":"<<number(p.allocations)<<",\"frees\":"<<number(p.frees)<<",\"live\":"<<number(p.live)<<",\"peak_live\":"<<number(p.peak)<<",\"live_shallow_bytes\":"<<number(p.bytes)<<",\"peak_shallow_bytes\":"<<number(p.peakBytes)<<'}';}
  out<<']';if(providerProfile){out<<",\"catalog\":{\"schema\":\"nex.task-profile-runtime-catalog/1\",\"registries\":[";bool comma=false;for(const auto &r:ranges){if(comma)out<<',';comma=true;out<<"{\"component\":"<<quoted(r.component)<<",\"first_site\":"<<r.first<<",\"site_count\":"<<r.count<<'}';}out<<"]}";}
  out<<",\"traceEvents\":[]}\n";const auto report=out.str();if(report.size()>byteLimit)throw std::runtime_error("task profile report exceeds bounded output size");
  std::ofstream file(output,std::ios::binary|std::ios::trunc);file<<report;file.flush();if(!file)std::fprintf(stderr,"NEX_PROFILE: could not write task profile report\n");
}
#endif
