#pragma once
#include <cstddef>
#include <cstdint>
#ifdef NEX_TASK_PROFILE_ENABLED
#include "nex_task_profile.h"
#include "nex_task_profile_site.h"
#include "nex_task_limits.h"
#include <optional>
#endif

// Hooks are absent from ordinary builds and from the reference interpreter.
extern "C" {
void nex_profile_enter(const char *name,const char *file,int64_t line,const char *content);
void nex_profile_leave();
void nex_profile_unwind();
void nex_profile_allocation(const void *pointer,size_t size,int pool);
void nex_profile_free(const void *pointer);
}
namespace nexrt {
#ifdef NEX_TASK_PROFILE_ENABLED
TaskProfileCollector *taskProfileCollector()noexcept;
std::optional<size_t> taskProfileSiteIndex(const TaskProfileCodeSite*)noexcept;
void taskProfileLimits(const TaskExecutionLimits&,const TaskExecutionLimits&)noexcept;
void taskProfileEffectiveLimits(const TaskExecutionLimits&)noexcept;
class TaskProfileSourceScope {
  alignas(TaskProfileSourceSegment) std::byte storage[sizeof(TaskProfileSourceSegment)];size_t baseline=0;bool active=false,disabled=false;
public:
  explicit TaskProfileSourceScope(const TaskProfileInvocation&)noexcept;
  ~TaskProfileSourceScope();
  TaskProfileSourceScope(const TaskProfileSourceScope&)=delete;
  TaskProfileSourceScope &operator=(const TaskProfileSourceScope&)=delete;
};
class TaskProfileTurnScope {
  alignas(TaskProfileResumeGuard) std::byte storage[sizeof(TaskProfileResumeGuard)];
  TaskProfileCollector *collector=nullptr;const TaskProfileTask *task=nullptr;
  TaskProfileClockSample start;size_t baseline=0,priorBaseline=0;bool active=false;
public:
  explicit TaskProfileTurnScope(const TaskProfileTask&,bool countResume=true)noexcept;
  ~TaskProfileTurnScope();
  TaskProfileTurnScope(const TaskProfileTurnScope&)=delete;
  TaskProfileTurnScope &operator=(const TaskProfileTurnScope&)=delete;
};
// Deferred Value/result destruction is executor housekeeping, not another
// source resume. A completed future can retain its payload until observation.
// Active executors already account for nested cleanup; detached cleanup does
// not reactivate a terminal task or invocation.
class TaskProfileRetirementScope {
  TaskProfileCollector *collector=nullptr;const TaskProfileTask *task=nullptr;
  TaskProfileClockSample start;
public:
  explicit TaskProfileRetirementScope(const TaskProfileTask&)noexcept;
  ~TaskProfileRetirementScope();
  TaskProfileRetirementScope(const TaskProfileRetirementScope&)=delete;
  TaskProfileRetirementScope &operator=(const TaskProfileRetirementScope&)=delete;
};
#endif
inline void profileAllocate(const void *pointer,size_t size,int pool){
#ifdef NEX_PROFILE_ENABLED
  nex_profile_allocation(pointer,size,pool);
#else
  (void)pointer;(void)size;(void)pool;
#endif
}
inline void profileFree(const void *pointer){
#ifdef NEX_PROFILE_ENABLED
  nex_profile_free(pointer);
#else
  (void)pointer;
#endif
}
inline void profileUnwind(){
#ifdef NEX_PROFILE_ENABLED
  nex_profile_unwind();
#endif
}
}
