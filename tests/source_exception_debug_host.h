#pragma once
#include "nex_task_debug.h"
#include <atomic>
#include <deque>
#include <fstream>
#include <sstream>
// Functional host: inspect non-owning runtime records while their source worker
// is actually paused. No source expression is evaluated or frame value written.
namespace source_debug_test {
using namespace nexrt;
std::mutex debugMutex;
std::condition_variable debugChanged;
struct Pending {TaskDebugStop stop;bool resumed=false;};
std::deque<Pending*> pending;
std::map<uint64_t,unsigned> wanted,hits;
std::ofstream output;
std::thread controller;
bool closing=false;
std::atomic<bool> failed{false};
std::atomic<unsigned> pauses{0},resumes{0};
uint64_t load(const uint64_t &value){return std::atomic_ref<uint64_t>(const_cast<uint64_t&>(value)).load(std::memory_order_acquire);}
void require(bool yes,const char *message){if(!yes)throw std::runtime_error(message);}
std::string watchBindings(const TaskDebugCodeSite &code,const TaskDebugPoint &point,const NativeTaskFrame *native){
  std::map<std::string,std::string> values,types;
  for(int64_t index=0;index<point.visibleCount;++index){
    auto bindingIndex=code.visibleBindings[point.visibleBegin+index];require(bindingIndex>=0&&bindingIndex<code.bindingCount,"private visible binding missing");
    const auto &binding=code.bindings[bindingIndex];std::string type=binding.type;types[binding.name]=type;
    if(binding.slot<0){values[binding.name]="null";continue;}
    require(size_t(binding.slot)<native->slots.size()&&native->slots[binding.slot].has_value(),"private visible binding is uninitialized");
    if(type=="task_scope"||type.starts_with("task<")||type.starts_with("channel<")||type.find("fn(")!=std::string::npos){values[binding.name]="{\"opaque\":true}";continue;}
    auto value=*native->slots[binding.slot];values[binding.name]=representation(value);
  }
  std::ostringstream record;record<<"\"values\":{";bool first=true;
  for(const auto &[name,value]:values){if(!first)record<<',';first=false;record<<quoted(name)<<':'<<value;}record<<"},\"types\":{";first=true;
  for(const auto &[name,type]:types){if(!first)record<<',';first=false;record<<quoted(name)<<':'<<quoted(type);}record<<'}';return record.str();
}
std::string inspect(const TaskDebugStop &stop){
  auto &catalog=nex_task_debug_catalog_v1;
  require(stop.catalog_address==reinterpret_cast<uintptr_t>(&catalog)&&load(catalog.magic)==taskDebugCatalogMagic,"private debug catalog mismatch");
  require(stop.task_slot<load(catalog.task_count)&&stop.frame_slot<load(catalog.frame_capacity),"private stop index out of bounds");
  auto *tasks=reinterpret_cast<const TaskDebugTaskRecord*>(load(catalog.tasks_address));
  auto *frames=reinterpret_cast<const TaskDebugFrameRecord*>(load(catalog.frames_address));
  auto *codes=reinterpret_cast<const TaskDebugCodeSite*>(load(catalog.codes_address));
  auto &task=tasks[stop.task_slot];auto sequence=load(task.source_sequence);
  require(!(sequence&1)&&sequence==stop.source_sequence&&load(task.id)==stop.task_id&&(load(task.flags)&taskDebugAtCheckpoint),"private source is not stably stopped");
  auto &frame=frames[stop.frame_slot];auto codeIndex=load(frame.code_index);
  require(load(frame.id)==stop.frame_id&&load(frame.task_id)==stop.task_id&&codeIndex<load(catalog.code_count),"private frame identity mismatch");
  const auto &code=codes[codeIndex];require(stop.point_index<uint64_t(code.pointCount),"private point missing");const auto &point=code.points[stop.point_index];
  auto *native=reinterpret_cast<const NativeTaskFrame*>(load(frame.frame_address));require(native&&native->debugActivation.activation()==stop.frame_id,"private native frame mismatch");
  std::ostringstream record;record<<"{\"line\":"<<point.line<<",\"column\":"<<point.column<<",\"site\":"<<quoted(point.site)<<",\"function\":"<<quoted(code.name)
    <<",\"function_hash\":"<<quoted(code.functionHash)<<",\"source_hash\":"<<quoted(code.content)<<",\"task_id\":"<<stop.task_id<<",\"frame_id\":"<<stop.frame_id<<",\"depth\":"<<load(frame.depth)<<",\"frames\":"<<load(task.frame_count)<<','<<watchBindings(code,point,native)<<",\"stack\":[";
  uint64_t slot=stop.frame_slot,id=stop.frame_id,count=0;
  while(slot!=noTaskDebugIndex){
    require(slot<load(catalog.frame_capacity)&&count<maximumTaskDebugStack,"private caller chain out of bounds");const auto &caller=frames[slot];
    require(load(caller.id)==id&&load(caller.task_id)==stop.task_id,"private caller identity mismatch");auto index=load(caller.code_index);require(index<load(catalog.code_count),"private caller code missing");
    const auto &callerCode=codes[index];auto pointIndex=load(caller.point_index);require(pointIndex<uint64_t(callerCode.pointCount),"private caller point missing");auto *callerNative=reinterpret_cast<const NativeTaskFrame*>(load(caller.frame_address));require(callerNative&&callerNative->debugActivation.activation()==id,"private caller native frame mismatch");
    if(count++)record<<',';record<<"{\"function\":"<<quoted(callerCode.name)<<",\"frame_id\":"<<id<<','<<watchBindings(callerCode,callerCode.points[pointIndex],callerNative)<<'}';
    slot=load(caller.parent_slot);id=load(caller.parent_id);
  }
  require(count==load(task.frame_count),"private caller chain count differs from task");record<<"]}";
  require(load(task.source_sequence)==sequence&&load(frame.id)==stop.frame_id,"source advanced while controller inspected it");
  return record.str();
}
void start(){
  auto *path=std::getenv("NEX_PRIVATE_DEBUG_OUTPUT");auto *lines=std::getenv("NEX_PRIVATE_DEBUG_LINES");require(path&&lines,"private debugger host configuration absent");
  output.open(path);require(bool(output),"private debug output could not be opened");std::stringstream input(lines);std::string value;
  while(std::getline(input,value,',')){auto split=value.find(':');auto line=std::stoull(value.substr(0,split));wanted[line]=split==std::string::npos?1:std::stoul(value.substr(split+1));}
  controller=std::thread([]{
    for(;;){Pending *current;
      {std::unique_lock lock(debugMutex);debugChanged.wait(lock,[]{return closing||!pending.empty();});if(pending.empty()&&closing)return;current=pending.front();pending.pop_front();}
      try{auto record=inspect(current->stop);std::this_thread::sleep_for(std::chrono::milliseconds(2));require(inspect(current->stop)==record,"source variables changed while paused");output<<record<<'\n';output.flush();}
      catch(const std::exception &e){failed=true;output<<"{\"debug_error\":"<<quoted(e.what())<<"}\n";output.flush();}
      {std::lock_guard lock(debugMutex);current->resumed=true;++resumes;}debugChanged.notify_all();
    }
  });
}
void finish(){
  {std::lock_guard lock(debugMutex);closing=true;}debugChanged.notify_all();controller.join();output.close();require(!failed&&pauses==resumes,"private debugger observation/pause failed");
  auto &catalog=nex_task_debug_catalog_v1;require(load(catalog.live_frames)==0&&load(catalog.dropped_frames)==0&&load(catalog.dropped_tasks)==0&&load(catalog.invalid_transitions)==0,"private debug catalog did not retire cleanly");
  auto *tasks=reinterpret_cast<const TaskDebugTaskRecord*>(load(catalog.tasks_address));for(size_t i=0;i<load(catalog.task_count);++i)require(load(tasks[i].state)==uint64_t(TaskDebugState::Terminal)&&load(tasks[i].frame_count)==0,"terminal private task retained readable source frames");
  std::fprintf(stderr,"NEX_PRIVATE_DEBUG {\"pauses\":%u,\"resumes\":%u,\"live_frames\":0,\"nonowning\":true}\n",pauses.load(),resumes.load());
}
}
extern "C" void nex_task_debug_stop_marker(const nexrt::TaskDebugStop *stop)noexcept{
  using namespace source_debug_test;
  try{
    if(!stop)return;auto &catalog=nex_task_debug_catalog_v1;auto *frames=reinterpret_cast<const TaskDebugFrameRecord*>(load(catalog.frames_address));auto *codes=reinterpret_cast<const TaskDebugCodeSite*>(load(catalog.codes_address));
    if(stop->frame_slot>=load(catalog.frame_capacity))return;auto index=load(frames[stop->frame_slot].code_index);if(index>=load(catalog.code_count)||stop->point_index>=uint64_t(codes[index].pointCount))return;
    const auto &point=codes[index].points[stop->point_index];if(point.kind!=int64_t(TaskDebugPointKind::Statement))return;
    std::unique_lock lock(debugMutex);auto found=wanted.find(point.line);if(found==wanted.end()||hits[point.line]>=found->second)return;++hits[point.line];
    Pending state{*stop};pending.push_back(&state);++pauses;debugChanged.notify_all();debugChanged.wait(lock,[&]{return state.resumed;});
  }catch(...){failed=true;}
}
