#pragma once
#include "nex_error.h"
#include <cstddef>
#include <cstdint>
#include <functional>
#include <memory>

namespace nexrt {
namespace resource_executor_detail {struct State;struct Completion;}

// Trusted host execution only. Source values, C invocation tokens and source
// callbacks must never be retained by an operation. Returning from run means
// that the actual device fence/IPC operation has physically settled.
class ResourceExecutionControl {
  std::shared_ptr<resource_executor_detail::Completion> completion;
  friend struct resource_executor_detail::State;
  explicit ResourceExecutionControl(std::shared_ptr<resource_executor_detail::Completion>);
public:
  bool cancelled()const noexcept;
  void checkpoint()const;
};
class ResourceExecutionOperation {
public:
  virtual ~ResourceExecutionOperation()=default;
  virtual void run(const ResourceExecutionControl&)=0;
};
class ResourceExecution {
  std::shared_ptr<resource_executor_detail::Completion> completion;
  friend class ResourceExecutor;
  explicit ResourceExecution(std::shared_ptr<resource_executor_detail::Completion>);
public:
  ResourceExecution()=default;
  void cancel()const noexcept;
  bool ready()const noexcept;
  // Completion is published after run and the operation's destructor. A cancel
  // request does not recycle storage or promise early physical completion.
  void wait()const;
};
class ResourceCleanupTicket {
  std::shared_ptr<resource_executor_detail::State> state;
  size_t slot=0;
  friend class ResourceExecutor;
  ResourceCleanupTicket(std::shared_ptr<resource_executor_detail::State>,size_t);
public:
  ResourceCleanupTicket()=default;
  ResourceCleanupTicket(ResourceCleanupTicket&&)noexcept;
  ResourceCleanupTicket &operator=(ResourceCleanupTicket&&)noexcept;
  ResourceCleanupTicket(const ResourceCleanupTicket&)=delete;
  ResourceCleanupTicket &operator=(const ResourceCleanupTicket&)=delete;
  ~ResourceCleanupTicket();
  // Consumes a pre-reserved slot. No allocation or admission is needed at the
  // last release, including after the executor stops accepting new operations.
  void retire(void*,void(*destroy)(void*)noexcept)noexcept;
};
struct ResourceExecutorLimits {
  size_t resources=64,operations=64;
  uint64_t reservedBytes=8*1024*1024;
};
struct ResourceExecutorStats {
  size_t resources=0,operations=0,queued=0,running=0;
  uint64_t reservedBytes=0;
  bool accepting=false;
};
class ResourceExecutor {
  std::shared_ptr<resource_executor_detail::State> state;
public:
  explicit ResourceExecutor(ResourceExecutorLimits={});
  ~ResourceExecutor();
  ResourceExecutor(const ResourceExecutor&)=delete;
  ResourceExecutor &operator=(const ResourceExecutor&)=delete;
  ResourceCleanupTicket reserveCleanup();
  ResourceExecution submit(std::unique_ptr<ResourceExecutionOperation>,uint64_t reservedBytes=0);
  // Host construction and admission. Re-entry on the owning executor runs
  // inline; waiting for another queued operation on that same thread is refused.
  void invoke(std::function<void()>);
  bool onThread()const noexcept;
  void close()noexcept;
  void drain();
  // Caller must first release idle owners/borrows. Joins the worker only after
  // every reserved cleanup and operation has physically completed.
  void finish();
  ResourceExecutorStats stats()const;
};
}
