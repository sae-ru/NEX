#pragma once
#include "nex_error.h"
#include <atomic>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <vector>

namespace nexrt {
// Private host transport, deliberately independent of source Values, Handles,
// coroutine/frame addresses, FileScope TLS and provider/FFI callbacks.
struct TaskExternalResult {
  std::vector<uint8_t> bytes;
  std::string errorCode,errorMessage;
};
inline constexpr size_t taskExternalErrorCodeCapacity=128,taskExternalErrorMessageCapacity=4096;
// Classify raw storage/protocol failures before a later cancellation checkpoint
// can replace them. Both the request wrapper and the transport enforce this.
inline void validateTaskExternalResult(const TaskExternalResult &result,size_t reservation,size_t maximumResultBytes){
  if(result.bytes.capacity()>maximumResultBytes||result.bytes.capacity()>reservation||result.errorCode.capacity()>taskExternalErrorCodeCapacity||result.errorMessage.capacity()>taskExternalErrorMessageCapacity)
    throw DataError("E_LIMIT","external result exceeds its reserved payload or protocol limit");
  if(result.errorCode=="E_MEMORY"||result.errorCode=="E_LIMIT"||result.errorCode=="E_TIMEOUT")throw DataError(result.errorCode,result.errorMessage);
}
class TaskExternalControl {
  std::function<void()> check;
public:
  explicit TaskExternalControl(std::function<void()> checkpoint={}):check(std::move(checkpoint)){}
  void checkpoint()const{if(check)check();}
};
class TaskExternalOperation {
public:
  virtual ~TaskExternalOperation()=default;
  // Trusted fixed host adapters retain explicit revocable leases and owned
  // bounded bytes/path data only. Source values never cross this boundary.
  virtual TaskExternalResult run(const TaskExternalControl &)=0;
};
struct TaskExternalLimits {
  size_t workers=2,tickets=64,reservedBytes=8*1024*1024,maximumResultBytes=1024*1024;
};
inline bool validTaskExternalLimits(const TaskExternalLimits &limits)noexcept{
  return limits.workers&&limits.workers<=2&&limits.tickets&&limits.tickets<=64&&limits.reservedBytes&&limits.reservedBytes<=8*1024*1024&&limits.maximumResultBytes&&limits.maximumResultBytes<=1024*1024;
}
namespace task_external_detail {struct State;}
class TaskExternalTicket {
  friend class TaskExternalPool;
  std::weak_ptr<task_external_detail::State> state;
  size_t slot=0;uint64_t generation=0,task=0;
  TaskExternalTicket(const std::shared_ptr<task_external_detail::State>&,size_t,uint64_t,uint64_t);
public:
  TaskExternalTicket()=default;
  uint64_t owner()const noexcept{return task;}
  bool operator==(const TaskExternalTicket &other)const noexcept{
    return !state.owner_before(other.state)&&!other.state.owner_before(state)&&slot==other.slot&&generation==other.generation&&task==other.task;
  }
};
struct TaskExternalStats {size_t tickets=0,reservedBytes=0,running=0,queued=0,maximumRunning=0;};
class TaskExternalPool {
  std::shared_ptr<task_external_detail::State> state;
public:
  // Notification publishes a physically finished ticket, outside all kernel
  // locks and after the operation/lease destructor. It never resumes source.
  using Notification=std::function<void(const TaskExternalTicket &)>;
  explicit TaskExternalPool(TaskExternalLimits={},Notification={});
  ~TaskExternalPool();
  TaskExternalPool(const TaskExternalPool&)=delete;
  TaskExternalPool &operator=(const TaskExternalPool&)=delete;
  TaskExternalTicket submit(uint64_t owner,std::shared_ptr<TaskExternalOperation>,size_t reservedBytes,TaskExternalControl=TaskExternalControl{});
  void cancel(const TaskExternalTicket &);
  bool ready(const TaskExternalTicket &)const;
  TaskExternalResult take(const TaskExternalTicket &);
  void discard(const TaskExternalTicket &);
  TaskExternalStats stats()const;
  void drain(bool cancel=false);
};
}
