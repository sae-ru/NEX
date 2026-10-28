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

// A final NEX executable supplies the strong exact build identity. A trusted
// native host may omit it; do not fabricate a graph revision for that process.
// Keep this weak default preemptible when the runtime lives in a shared image.
#ifdef NEX_SHARED_PROFILE_RUNTIME
extern "C" __attribute__((weak)) const char *nex_profile_build_info(){return nullptr;}
#else
// Legacy profile archives retain their strong archived build identity. A weak
// definition here could stop an archive linker extracting that identity unit.
extern "C" const char *nex_profile_build_info();
#endif

namespace {
using Clock=std::chrono::steady_clock;
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
  State();
  uint64_t now()const{return std::chrono::duration_cast<std::chrono::nanoseconds>(Clock::now()-origin).count();}
  void finish();
};
State &state(){static auto *value=new State;return *value;}
struct Frame {Stats *function;uint64_t start,children=0;TracyCZoneCtx zone{};};
struct Thread {std::vector<Frame> frames;uint64_t skipped=0,id=0;};
thread_local Thread thread;
void shutdown(){state().finish();}
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
  if(!output.empty()){
    std::lock_guard lock(mutex);std::ofstream out(output,std::ios::binary|std::ios::trunc);out<<std::setprecision(17);
    out<<"{\"schema\":\"nex.profile-runtime/1\",\"build\":"<<identity<<",\"clock\":\"steady_wall_nanoseconds\",\"duration_ns\":"<<now()
       <<",\"tracy\":"<<(tracy?"true":"false")<<",\"dropped_events\":"<<droppedEvents<<",\"dropped_functions\":"<<droppedFunctions
       <<",\"dropped_frames\":"<<droppedFrames<<",\"dropped_allocations\":"<<droppedAllocations<<",\"untracked_frees\":"<<untrackedFrees<<",\"functions\":[";
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
}
extern "C" void nex_profile_leave(){leave(false);}
extern "C" void nex_profile_unwind(){thread.skipped=0;while(!thread.frames.empty())leave(true);}
extern "C" void nex_profile_allocation(const void *pointer,size_t size,int pool){
  auto &s=state();if(!s.enabled)return;std::lock_guard lock(s.mutex);
  if(s.allocations.size()>=1000000){++s.droppedAllocations;return;}
  uint64_t connection=0;bool sent=s.tracy&&TracyCIsConnected;
  if(sent){connection=tracy::GetProfiler().ConnectionId();TracyCAllocN(pointer,size,poolName(pool));}
  s.allocations.emplace(pointer,Allocation{size,pool,connection,sent});auto &p=s.pools[pool];++p.allocations;++p.live;p.bytes+=size;p.peak=std::max(p.peak,p.live);p.peakBytes=std::max(p.peakBytes,p.bytes);
  if(!thread.frames.empty()){auto &f=*thread.frames.back().function;++f.allocations;f.allocatedBytes+=size;}
}
extern "C" void nex_profile_free(const void *pointer){
  auto &s=state();if(!s.enabled)return;std::lock_guard lock(s.mutex);auto found=s.allocations.find(pointer);
  if(found==s.allocations.end()){++s.untrackedFrees;return;}
  const auto allocation=found->second;
  if(allocation.sent&&TracyCIsConnected&&allocation.connection==tracy::GetProfiler().ConnectionId())TracyCFreeN(pointer,poolName(allocation.pool));
  auto &p=s.pools[allocation.pool];++p.frees;--p.live;p.bytes-=allocation.size;s.allocations.erase(found);
}
