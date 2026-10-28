#pragma once
#include "nex_task_frame.h"
#include "nex_task_limits.h"

namespace nexrt {
// One standalone image owns every descriptor until its joined executor and all
// retained values are destroyed. No compiler, AST or TaskIR participates here.
int64_t executeTaskApplication(const TaskCodeDescriptor &,SourceLocation);
int64_t executeTaskApplication(const TaskCodeDescriptor &,const TaskExecutionLimits &,SourceLocation);
int64_t executeSourceExceptionTaskApplication(const TaskCodeDescriptor &,const TaskExecutionLimits &,SourceLocation);
// Trusted experimental HTTP host boundary. The caller owns the active request,
// its budget/cancellation and the borrowed Request handle. This creates no new
// RequestScope or ambient file/foreign grants. Completion joins all admitted work
// before publishing an owned Response handle in the caller's request.
// The native HTTP adapter uses the configured entry below. Async network/DB
// and task HTTP provider-image/debug/profile integration remain pending.
Handle *executeTaskHttpRequest(const TaskCodeDescriptor &,Handle *request,
    std::shared_ptr<const TaskFrameHostContext> host={},unsigned workers=2);
// Compiler HTTP adapter: explicitly captures operator-configured file/foreign
// grants in the existing request; the lower-level API above captures none.
Handle *executeConfiguredTaskHttpRequest(const TaskCodeDescriptor &,Handle *request,unsigned workers);
// Explicit nonpublic025 HTTP channel. Source errors propagate after the joined
// executor drains; the embedding HTTP boundary chooses its response policy.
Handle *executeSourceExceptionTaskHttpRequest(const TaskCodeDescriptor &,Handle *request,
    std::shared_ptr<const TaskFrameHostContext> host={},unsigned workers=2);
Handle *executeConfiguredSourceExceptionTaskHttpRequest(const TaskCodeDescriptor &,Handle *request,unsigned workers);
}
extern "C" {
int64_t nex_task_application_execute(const nexrt::TaskCodeDescriptor *);
int64_t nex_task_application_execute_at(const nexrt::TaskCodeDescriptor *,const nexrt::NativeSite *);
int64_t nex_task_application_execute_limits(const nexrt::TaskCodeDescriptor *,int64_t,const char *const *,int64_t,int64_t,int64_t);
int64_t nex_task_application_execute_limits_at(const nexrt::TaskCodeDescriptor *,int64_t,const char *const *,int64_t,int64_t,int64_t,const nexrt::NativeSite *);
}
