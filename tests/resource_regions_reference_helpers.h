#pragma once
#include "nex/task_reference.h"
#include "nex_external_resource.h"
#include <array>
#include <atomic>
#include <chrono>
#include <condition_variable>
#include <iostream>
#include <mutex>
#include <thread>

using namespace nex;
using namespace nexrt;
using namespace std::chrono_literals;
namespace {
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
template<class F>void rejected(const char *code,F action){
  try{action();}catch(const DataError &e){require(e.code==code,"unexpected region error");return;}
  throw std::runtime_error(std::string("missing ")+code);
}
template<class F>void sourceRejected(const char *code,F action){
  try{action();}catch(const Error &e){if(e.code!=code)throw std::runtime_error(std::string("expected ")+code+", got "+e.code+": "+e.what());return;}
  throw std::runtime_error(std::string("missing ")+code);
}
struct Gate {
  std::mutex mutex;std::condition_variable changed;bool entered=false,released=false;
  void enter(){std::unique_lock lock(mutex);entered=true;changed.notify_all();changed.wait(lock,[&]{return released;});}
  bool wait(){std::unique_lock lock(mutex);return changed.wait_for(lock,5s,[&]{return entered;});}
  bool reached(){std::lock_guard lock(mutex);return entered;}
  void open(){{std::lock_guard lock(mutex);released=true;}changed.notify_all();}
};
struct Box {
  std::shared_ptr<std::atomic<int>> destroyed;
  std::shared_ptr<Gate> cleanup;
  int value=42;
  ~Box(){if(cleanup)cleanup->enter();++*destroyed;}
};
struct Host:TaskReferenceExternalHost {
  ResourceDomain physical{16};ResourceAccess access=physical.access();
  std::array<ResourceByteBudget,1> budgets{ResourceByteBudget(64)};
  ExternalResourceType<Box> key{"reference::Buffer",std::string(64,'c')};
  std::shared_ptr<std::atomic<int>> destroyed=std::make_shared<std::atomic<int>>(0);
  std::shared_ptr<std::atomic<int>> pins=std::make_shared<std::atomic<int>>(0);
  std::shared_ptr<ResourceExecutor> executor;
  std::vector<ExternalResource> aliases;
  std::vector<ResourceRegionAuthority> authorities;
  std::function<std::optional<TaskReferenceExternalRequest>(size_t,const ResourceRegionAuthority&)> action;
  std::function<void(size_t,const ResourceRegionAuthority&)> admission;
  std::atomic<size_t> retired{0};size_t legacy=0,prepared=0,admitted=0;
  std::atomic<size_t> taskRetirements{0};std::function<void(size_t)> taskRetirement;
  Host(){resourceRegions=true;}
  std::optional<TaskReferenceExternalRequest> prepare(size_t,Span)override{++legacy;return {};}
  std::optional<TaskReferenceExternalRequest> prepareInRegion(size_t owner,Span,const ResourceRegionAuthority &authority)override{
    require(authority.family()==ResourceRegionFamily::Reference,"native authority reached independent reference scheduler");
    ++prepared;return action?action(owner,authority):std::nullopt;
  }
  void admitInRegion(size_t owner,const TaskExternalResult &,const ResourceRegionAuthority &authority)override{
    authority.check();++admitted;if(admission)admission(owner,authority);
  }
  void scopeRetired(size_t)noexcept override{++retired;}
  void taskRetired(size_t owner)noexcept override{++taskRetirements;if(taskRetirement)taskRetirement(owner);}
  ExternalResource make(const ResourceRegionAuthority &authority,std::shared_ptr<Gate> cleanup={}){
    auto pin=std::shared_ptr<void>(new int(1),[pins=pins](void *p){delete static_cast<int*>(p);++*pins;});
    return ExternalResource::makeInRegion(access,authority,key,budgets,4,std::move(pin),executor,
      [counter=destroyed,cleanup](const auto&){return std::unique_ptr<Box>(new Box{counter,cleanup});});
  }
  void empty(){require(physical.used()==0&&budgets[0].used()==0,"evaluation returned before physical quota release");}
};
struct Operation:TaskExternalOperation {
  std::shared_ptr<Gate> gate;
  ExternalResourceBorrow borrow;
  Operation(std::shared_ptr<Gate> gate,ExternalResourceBorrow borrow):gate(std::move(gate)),borrow(std::move(borrow)){}
  TaskExternalResult run(const TaskExternalControl &)override{gate->enter();return {};}
};
Program source(const std::string &body){auto p=parse("module reference_regions;\n"+body,"reference_regions.nex");check(p);return p;}
auto evaluate(const Program &p,Host &host,TaskReferenceObserver observer={},const TaskExecutionLimits *limits=nullptr){
  return evaluateTaskReference(p,"main",{},1000000,std::move(observer),limits,&host);
}
const std::string once="fn main()->i64 !{task}{task_yield();return 42;}";
const std::string scoped="fn main()->i64 !{task}{return with_tasks(1,fn(scope:task_scope)->i64 !{task}{task_yield();return 42;});}";
}
