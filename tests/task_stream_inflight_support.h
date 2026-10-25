#pragma once
#include "nex_files.h"
#include "nex_host.h"
#include "nex_task_limits.h"
#include <chrono>
#include <condition_variable>
#include <future>
#include <iostream>
#include <map>
#include <mutex>
#include <stop_token>
#include <thread>

namespace inflight_test {
using namespace nexrt;
using Clock=std::chrono::steady_clock;
inline void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
inline FileIOOperation operation(const std::string &name){
  static const std::map<std::string,FileIOOperation> names={{"open_read",FileIOOperation::OpenRead},{"open_write",FileIOOperation::OpenWrite},
    {"open_append",FileIOOperation::OpenAppend},{"read",FileIOOperation::Read},{"write",FileIOOperation::Write},{"seek",FileIOOperation::Seek},
    {"size",FileIOOperation::Size},{"flush",FileIOOperation::Flush}};
  return names.at(name);
}
struct Gate {
  const FileIOOperation selected;
  const size_t occurrence;
  const bool sourceCancel;
  const bool hostFailure;
  std::mutex mutex;
  std::condition_variable changed;
  bool reached=false,released=false,issued=false,cancelSeen=false,distinctThread=false;
  size_t matches=0;
  FileIOEvent selectedEvent{FileIOOperation::Read,FileIOPhase::Before};
  std::vector<FileIOEvent> trace;
  Clock::time_point deadline;
  std::thread::id coordinator;
  std::function<void()> cancel;
  std::function<std::pair<size_t,size_t>()> sample;
  Gate(FileIOOperation selected,size_t occurrence,bool sourceCancel,bool hostFailure):selected(selected),occurrence(occurrence),sourceCancel(sourceCancel),hostFailure(hostFailure){}
  void setup(Clock::time_point until,std::function<void()> stop,std::function<std::pair<size_t,size_t>()> statistics={}){
    std::lock_guard lock(mutex);deadline=until;coordinator=std::this_thread::get_id();cancel=std::move(stop);sample=std::move(statistics);
  }
  void observe(const FileIOEvent &event){
    std::unique_lock lock(mutex);trace.push_back(event);
    if(event.operation!=selected||event.phase!=FileIOPhase::After||event.error||event.result<0||++matches!=occurrence)return;
    require(!reached,"physical gate reached twice");selectedEvent=event;distinctThread=std::this_thread::get_id()!=coordinator;reached=true;changed.notify_all();
    changed.wait(lock,[&]{return released;});
    if(hostFailure)throw std::runtime_error("explicit trusted file observer failure");
  }
  void waitReached(){std::unique_lock lock(mutex);require(changed.wait_for(lock,std::chrono::seconds(10),[&]{return reached;}),"actual file IO did not reach its gate");}
  void beforeSourceCancel(){if(!sourceCancel)return;waitReached();std::lock_guard lock(mutex);cancelSeen=true;}
  void afterSourceCancel(){if(!sourceCancel)return;std::lock_guard lock(mutex);if(cancelSeen){issued=true;changed.notify_all();}}
  void waitIssued(){std::unique_lock lock(mutex);require(changed.wait_for(lock,std::chrono::seconds(10),[&]{return issued;}),"source task_cancel did not complete");}
  void stop(){std::function<void()> callback;{std::lock_guard lock(mutex);callback=cancel;}require(bool(callback),"host cancellation unavailable");callback();}
  std::pair<size_t,size_t> stats(){std::function<std::pair<size_t,size_t>()> callback;{std::lock_guard lock(mutex);callback=sample;}return callback?callback():std::pair<size_t,size_t>{0,0};}
  void release()noexcept{{std::lock_guard lock(mutex);released=true;}changed.notify_all();}
};
struct Execution {std::string error;int64_t value=0;bool physicalSettlement=false;size_t retiredTasks=0;};
struct Outcome {
  Execution execution;
  FileIOEvent actual{FileIOOperation::Read,FileIOPhase::Before};
  std::vector<FileIOEvent> trace;
  bool sourceCancel=false,distinctIOThread=false,pendingBeforeControl=false,pendingAfterControl=false;
  size_t quotaDuring=0,quotaAfter=0,externalTickets=0,externalRunning=0;
  std::string quotaError;
};
template<class Runner>
Outcome exercise(const std::string &root,const std::string &mode,FileIOOperation selected,size_t occurrence,Runner runner){
  require(mode=="none"||mode=="cancel"||mode=="deadline"||mode=="revoke"||mode=="source_cancel"||mode=="host_error","invalid inflight mode");
  require(occurrence>0,"invalid inflight occurrence");const auto baseline=liveObjects.load();Outcome result;
  auto gate=std::make_shared<Gate>(selected,occurrence,mode=="source_cancel",mode=="host_error");
  TextFiles files(root,true,[gate](const FileIOEvent &event){gate->observe(event);});auto domain=files.resourceScope(1);
  auto execution=std::async(std::launch::async,[&]{
    RequestScope request(maximumTaskExecutionSteps,mode=="deadline"?1000:30000);FileScope scope(files,domain);
    auto reads=captureFileReadGrant(false);auto writes=captureFileWriteGrant(false);
    return runner(*gate,request,reads,writes);
  });
  // Release before future destruction even when a test assertion throws.
  struct Release {std::shared_ptr<Gate> gate;~Release(){gate->release();}} release{gate};
  gate->waitReached();result.pendingBeforeControl=execution.wait_for(std::chrono::milliseconds(1))==std::future_status::timeout;
  require(result.pendingBeforeControl&&domain.used()==1,"physical IO published or returned its quota before release");
  if(mode=="cancel")gate->stop();
  else if(mode=="deadline")std::this_thread::sleep_until(gate->deadline+std::chrono::milliseconds(1));
  else if(mode=="revoke")domain.revoke();
  else if(mode=="source_cancel")gate->waitIssued();
  result.quotaDuring=domain.used();require(result.quotaDuring==1,"control prematurely released the physical file quota");
  try{auto extra=domain.make<int>([](const ResourcePermit &){return std::make_unique<int>(1);});}
  catch(const DataError &error){result.quotaError=error.code;}
  require(result.quotaError==(mode=="revoke"?"E_RESOURCE_SCOPE":"E_RESOURCE_LIMIT"),"physical quota could be reused while IO retained it");
  result.pendingAfterControl=execution.wait_for(std::chrono::milliseconds(30))==std::future_status::timeout;
  require(result.pendingAfterControl,"source execution completed before physical IO retirement");
  auto stats=gate->stats();result.externalTickets=stats.first;result.externalRunning=stats.second;
  gate->release();require(execution.wait_for(std::chrono::seconds(10))==std::future_status::ready,"source execution did not drain after physical release");
  result.execution=execution.get();result.quotaAfter=domain.used();require(result.quotaAfter==0&&result.execution.physicalSettlement,"file quota/finalizers outlived source completion");
  {std::lock_guard lock(gate->mutex);result.actual=gate->selectedEvent;result.trace=gate->trace;result.sourceCancel=gate->issued;result.distinctIOThread=gate->distinctThread;}
  require(result.distinctIOThread,"file syscall ran on the source coordinator");require(liveObjects.load()==baseline,"source execution retained owned values");return result;
}
inline void print(const Outcome &result){
  std::cout<<"{\"ok\":true,\"control_error\":\""<<result.execution.error<<"\",\"value\":"<<result.execution.value
    <<",\"actual_operation\":"<<int(result.actual.operation)<<",\"actual_argument\":"<<result.actual.argument<<",\"actual_result\":"<<result.actual.result
    <<",\"source_cancel_issued\":"<<(result.sourceCancel?"true":"false")<<",\"IO_thread_distinct\":"<<(result.distinctIOThread?"true":"false")
    <<",\"pending_before_control\":"<<(result.pendingBeforeControl?"true":"false")<<",\"pending_after_control\":"<<(result.pendingAfterControl?"true":"false")
    <<",\"quota_during_gate\":"<<result.quotaDuring<<",\"quota_after\":"<<result.quotaAfter<<",\"quota_reuse_error\":\""<<result.quotaError
    <<"\",\"external_tickets_during_gate\":"<<result.externalTickets<<",\"external_running_during_gate\":"<<result.externalRunning
    <<",\"physical_file_settlement\":true,\"live_objects_restored\":true,\"trace\":[";
  bool comma=false;for(const auto &event:result.trace){if(comma)std::cout<<',';comma=true;std::cout<<'['<<int(event.operation)<<','<<int(event.phase)<<','<<event.argument<<','<<event.result<<','<<event.error<<']';}
  std::cout<<"]}\n";
}
}
