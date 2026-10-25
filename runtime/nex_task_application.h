#pragma once
#include "nex_task_frame.h"
#include "nex_task_limits.h"

namespace nexrt {
// One standalone image owns every descriptor until its joined executor and all
// retained values are destroyed. No compiler, AST or TaskIR participates here.
int64_t executeTaskApplication(const TaskCodeDescriptor &,SourceLocation);
int64_t executeTaskApplication(const TaskCodeDescriptor &,const TaskExecutionLimits &,SourceLocation);
// Trusted experimental HTTP host boundary. The caller owns the active request,
// its budget/cancellation and the borrowed Request handle. This creates no new
// RequestScope or ambient file/foreign grants. Completion joins all admitted work
// before publishing an owned Response handle in the caller's request.
// Public compiler HTTP/task integration and async network/DB remain pending.
Handle *executeTaskHttpRequest(const TaskCodeDescriptor &,Handle *request,
    std::shared_ptr<const TaskFrameHostContext> host={},unsigned workers=2);
}
extern "C" {
int64_t nex_task_application_execute(const nexrt::TaskCodeDescriptor *);
int64_t nex_task_application_execute_at(const nexrt::TaskCodeDescriptor *,const nexrt::NativeSite *);
int64_t nex_task_application_execute_limits(const nexrt::TaskCodeDescriptor *,int64_t,const char *const *,int64_t,int64_t,int64_t);
int64_t nex_task_application_execute_limits_at(const nexrt::TaskCodeDescriptor *,int64_t,const char *const *,int64_t,int64_t,int64_t,const nexrt::NativeSite *);
}
