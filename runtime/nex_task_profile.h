#pragma once
#include <cstddef>
#include <cstdint>
#include <memory>
#include <span>
#include <string>
#include <string_view>
#include <vector>

namespace nexrt {
// Bounded logical invocation collector. Native driver integration and report
// serialization live separately in nex_profile.cpp; clocks grant no source
// execution or resource authority.
struct TaskProfileSite {std::string_view name,file,content;int64_t line=0;};
struct TaskProfileClockSample {
  uint64_t wallNs=0,cpuNs=0,threadId=0;
  bool wallAvailable=true,cpuAvailable=true;
};
struct TaskProfileClock {
  using Sample=TaskProfileClockSample (*)(void *) noexcept;
  Sample sample=nullptr;void *context=nullptr;
};
struct TaskProfileLimits {size_t tasks=4096,invocations=65536,events=100000;};
struct TaskProfileOptions {bool enabled=true;TaskProfileLimits limits;};
inline constexpr size_t maximumTaskProfileGuardDepth=4096;
enum class TaskProfileTaskOutcome {Completed,Aborted,Cancelled};
enum class TaskProfileInvocationOutcome {Active,Completed,Aborted};
struct TaskProfileDrops {
  uint64_t tasks=0,invocations=0,events=0,guards=0,suppressedHooks=0,invalidTransitions=0,clockFailures=0,counterOverflows=0;
  bool incomplete=false;
};
struct TaskProfileFunctionRecord {
  uint64_t calls=0,completed=0,aborted=0;
  uint64_t inclusiveCpuNs=0,selfCpuNs=0,activeElapsedNs=0,selfActiveElapsedNs=0,lifetimeNs=0,maxLifetimeNs=0;
  bool cpuAvailable=true,elapsedAvailable=true,lifetimeAvailable=true;
};
struct TaskProfileFunctionSnapshot : TaskProfileFunctionRecord {
  std::string name,file,content;int64_t line=0;
};
struct TaskProfileTaskRecord {
  uint64_t id=0,spawningInvocationId=0,createdWallNs=0,terminalWallNs=0;
  uint64_t resumes=0,migrations=0,lastThreadId=0,sourceCpuNs=0,sourceElapsedNs=0,activeInvocations=0;
  bool started=false,cancelledBeforeStart=false,terminal=false;
  TaskProfileTaskOutcome outcome=TaskProfileTaskOutcome::Completed;
  uint64_t readyNs=0,blockedFutureNs=0,blockedSendNs=0,blockedReceiveNs=0,blockedScopeNs=0,blockedExternalNs=0,drainNs=0;
  uint64_t executorCpuNs=0,executorElapsedNs=0;
  // Detached deferred-result retirement may occur after the logical terminal
  // event. It adds executor work, not source CPU, resumes or logical lifetime.
  bool executorCpuAvailable=true,schedulerElapsedAvailable=true;
};
struct TaskProfileSchedulerTotals {
  uint64_t readyNs=0,blockedFutureNs=0,blockedSendNs=0,blockedReceiveNs=0,blockedScopeNs=0,blockedExternalNs=0,drainNs=0;
  bool elapsedAvailable=true;
};
struct TaskProfileInvocationRecord {
  uint64_t id=0,taskId=0,parentId=0;size_t site=0;
  TaskProfileInvocationOutcome outcome=TaskProfileInvocationOutcome::Active;
  uint64_t startWallNs=0,endWallNs=0,inclusiveCpuNs=0,selfCpuNs=0;
  uint64_t activeElapsedNs=0,selfActiveElapsedNs=0,lifetimeNs=0;
  bool cpuAvailable=true,elapsedAvailable=true,lifetimeAvailable=true;
};
struct TaskProfileSegmentRecord {
  uint64_t taskId=0,invocationId=0,threadId=0,startWallNs=0,elapsedNs=0,cpuNs=0;
  bool elapsedAvailable=true,cpuAvailable=true;
};
struct TaskProfileSnapshot {
  bool enabled=false;TaskProfileLimits limits;TaskProfileDrops drops;
  std::vector<TaskProfileFunctionSnapshot> functions;
  std::vector<TaskProfileTaskRecord> tasks;
  // Completed records share the bounded event budget with segments. Active
  // logical invocations are always included, independently of timeline drops.
  std::vector<TaskProfileInvocationRecord> invocations;
  std::vector<TaskProfileSegmentRecord> segments;
  size_t collectorStorageBytes=0,siteTextStorageBytes=0;
  // These are collector-owned backing capacities/shallow records only, not
  // managed Value/Handle memory, coroutine memory, transport quota or total RAM.
};
namespace task_profile_detail {struct State;}
class TaskProfileCollector;
class TaskProfileResumeGuard;
class TaskProfileSourceSegment;
class TaskProfileTask {
  std::shared_ptr<task_profile_detail::State> state;size_t slot=0;uint64_t value=0;
  friend class TaskProfileCollector;friend class TaskProfileResumeGuard;
public:
  uint64_t id()const noexcept{return value;}
  explicit operator bool()const noexcept{return value!=0;}
};
class TaskProfileInvocation {
  std::shared_ptr<task_profile_detail::State> state;size_t slot=0;uint64_t value=0,task=0;
  friend class TaskProfileCollector;friend class TaskProfileSourceSegment;
  void finish(bool)noexcept;
public:
  TaskProfileInvocation()noexcept=default;
  ~TaskProfileInvocation();
  TaskProfileInvocation(const TaskProfileInvocation&)=delete;
  TaskProfileInvocation &operator=(const TaskProfileInvocation&)=delete;
  TaskProfileInvocation(TaskProfileInvocation&&)noexcept;
  TaskProfileInvocation &operator=(TaskProfileInvocation&&)noexcept;
  uint64_t id()const noexcept{return value;}
  uint64_t taskId()const noexcept{return task;}
  explicit operator bool()const noexcept{return value!=0;}
  // Idempotent; reset ownership. Destruction aborts an unfinished invocation.
  // A parent abort can retire after its child tokens (e.g. vector unwinding).
  // Premature complete/live-source teardown is rejected as an incomplete abort.
  void complete()noexcept{finish(false);}
  void abort()noexcept{finish(true);}
};
class TaskProfileResumeGuard {
  std::shared_ptr<task_profile_detail::State> state;size_t slot=0;uint64_t task=0;
  task_profile_detail::State *priorState=nullptr;size_t priorSlot=0;uint64_t priorTask=0;
  TaskProfileResumeGuard *priorGuard=nullptr;
  TaskProfileSourceSegment *priorSegment=nullptr;
  uint64_t thread=0;bool attached=false,suppressing=false;
  explicit TaskProfileResumeGuard(const TaskProfileTask&,const std::shared_ptr<task_profile_detail::State>&,bool)noexcept;
  void suppress()noexcept;
  friend class TaskProfileCollector;
  friend class TaskProfileSourceSegment;
public:
  ~TaskProfileResumeGuard();
  TaskProfileResumeGuard(const TaskProfileResumeGuard&)=delete;
  TaskProfileResumeGuard &operator=(const TaskProfileResumeGuard&)=delete;
  TaskProfileResumeGuard(TaskProfileResumeGuard&&)=delete;
  TaskProfileResumeGuard &operator=(TaskProfileResumeGuard&&)=delete;
  bool active()const noexcept{return attached;}
};
class TaskProfileSourceSegment {
  std::shared_ptr<task_profile_detail::State> state;size_t slot=0;uint64_t invocation=0,task=0;
  TaskProfileClockSample start;
  TaskProfileSourceSegment *prior=nullptr;
  bool attached=false,measuring=false;
  explicit TaskProfileSourceSegment(const TaskProfileInvocation&)noexcept;
  void pause()noexcept;void resume()noexcept;
  friend class TaskProfileCollector;friend class TaskProfileResumeGuard;
public:
  ~TaskProfileSourceSegment();
  TaskProfileSourceSegment(const TaskProfileSourceSegment&)=delete;
  TaskProfileSourceSegment &operator=(const TaskProfileSourceSegment&)=delete;
  TaskProfileSourceSegment(TaskProfileSourceSegment&&)=delete;
  TaskProfileSourceSegment &operator=(TaskProfileSourceSegment&&)=delete;
  bool active()const noexcept{return attached;}
};
class TaskProfileCollector {
  std::shared_ptr<task_profile_detail::State> state;
public:
  // Construction/registration/preallocation and snapshot may allocate/throw.
  // Clock callback context must outlive all tokens/guards; callbacks are sampled
  // outside collector locks. All execution hooks below are bounded and noexcept.
  explicit TaskProfileCollector(TaskProfileOptions={},std::span<const TaskProfileSite> sites={},TaskProfileClock={});
  bool enabled()const noexcept{return bool(state);}
  TaskProfileTask task()noexcept;
  TaskProfileTask task(const TaskProfileInvocation &spawningInvocation)noexcept;
  TaskProfileTask taskFromCurrent()noexcept;
  TaskProfileResumeGuard resume(const TaskProfileTask &task,bool countResume=true)noexcept;
  TaskProfileInvocation invocation(size_t site)noexcept;
  TaskProfileSourceSegment source(const TaskProfileInvocation &invocation)noexcept;
  void cancelBeforeStart(const TaskProfileTask&)noexcept;
  void terminal(const TaskProfileTask&,TaskProfileTaskOutcome)noexcept;
  TaskProfileClockSample sample()const noexcept;
  void executor(const TaskProfileTask&,TaskProfileClockSample,TaskProfileClockSample)noexcept;
  void scheduler(const TaskProfileTask&,const TaskProfileSchedulerTotals&)noexcept;
  TaskProfileSnapshot snapshot()const;
};
// TLS access is allocation/clock/lock free. Nested guards restore the prior
// logical context; segments pause while another task is attached. Guards and
// segments are thread-affine: destruction on another thread is unsupported.
// Same-thread non-LIFO teardown is repaired and flagged incomplete. Attached
// resume/source guards share a fixed4096-per-thread bound across collectors;
// overflow drops instrumentation only (drops.guards), never execution work.
// A rejected enabled resume suppresses logical recording/IDs and pauses the
// parent source interval until that failed guard retires; helpers cannot fall
// back to an unrelated parent task. Suppression uses a scalar nesting count.
// Normally
// guards/segments are strictly nested, while invocation/task tokens can
// migrate after detaching. No live invocation is unwound merely by detachment.
uint64_t currentTaskProfileTask()noexcept;
uint64_t currentTaskProfileInvocation()noexcept;
size_t currentTaskProfileSite()noexcept;
}
