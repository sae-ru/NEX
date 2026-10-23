#pragma once
#include "nex/language.h"
#include "nex_task_external.h"
#include <chrono>
#include <optional>
#include <stop_token>

namespace nex {
// Experimental trusted-host transport. These tickets contain no source value,
// capability or frame address. Every field is authenticated against a live
// coordinator-owned slot before an operation can affect a source continuation.
struct TaskReferenceExternalTicket {
  uint64_t scheduler=0,generation=0;
  size_t slot=size_t(-1),owner=size_t(-1);
  bool operator==(const TaskReferenceExternalTicket &)const=default;
};
struct TaskReferenceExternalStats {
  size_t pending=0,reservedBytes=0,running=0,ready=0,maximumRunning=0;
  uint64_t submitted=0,retired=0,consumed=0,cancelRequests=0;
};
class TaskReferenceExternalMailbox {
  struct Impl;
  std::unique_ptr<Impl> impl;
public:
  using Clock=std::chrono::steady_clock;
  explicit TaskReferenceExternalMailbox(Clock::time_point deadline,
      std::stop_token cancellation={},nexrt::TaskExternalLimits limits={});
  ~TaskReferenceExternalMailbox();
  TaskReferenceExternalMailbox(const TaskReferenceExternalMailbox &)=delete;
  TaskReferenceExternalMailbox &operator=(const TaskReferenceExternalMailbox &)=delete;
  TaskReferenceExternalTicket submit(size_t owner,
      std::shared_ptr<nexrt::TaskExternalOperation>,size_t reservedBytes);
  bool cancel(const TaskReferenceExternalTicket &);
  std::optional<TaskReferenceExternalTicket> ready()const;
  nexrt::TaskExternalResult take(const TaskReferenceExternalTicket &);
  // Root cancellation/deadline closes admission. Physical operations retain
  // their reservation until retirement; neither cancellation nor take releases
  // a still-running lease. Only this creating coordinator may use the API.
  void close();
  void wait();
  //020 coordinator controls may be callback-driven rather than stop_token.
  // Wake to poll them without spinning; sealed physical drain stays blocking.
  void waitForControl(std::chrono::milliseconds maximumPause);
  void drain();
  TaskReferenceExternalStats stats()const;
};
struct TaskReferenceExternalRequest {
  std::shared_ptr<nexrt::TaskExternalOperation> operation;
  size_t reservedBytes=0;
};
struct TaskReferenceExternalHost {
  std::stop_token cancellation;
  nexrt::TaskExternalLimits limits;
  virtual ~TaskReferenceExternalHost()=default;
  // Invoked only by the source coordinator for a checked task_yield. Returning
  // nullopt keeps ordinary yield semantics. A returned operation can retain
  // explicit host leases and owned raw data only, never Values or task caps.
  virtual std::optional<TaskReferenceExternalRequest> prepare(size_t owner,Span)=0;
  // Coordinator-only unit admission, after physical retirement. This private
  // hook may validate host leases; the source response is always unit. There
  // is deliberately no public filesystem/source-IO bridge in this interface.
  virtual void admit(size_t,const nexrt::TaskExternalResult &){}
  // Private lifecycle observation after logical close, outside mailbox locks.
  // Coordinator-only and non-reentrant; it promises no source authority API.
  virtual void scopeRetired(size_t)noexcept{}
};
}
