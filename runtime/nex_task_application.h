#pragma once
#include "nex_task_frame.h"
#include "nex_task_limits.h"

namespace nexrt {
// One standalone image owns every descriptor until its joined executor and all
// retained values are destroyed. No compiler, AST or TaskIR participates here.
int64_t executeTaskApplication(const TaskCodeDescriptor &,SourceLocation);
int64_t executeTaskApplication(const TaskCodeDescriptor &,const TaskExecutionLimits &,SourceLocation);
}
extern "C" {
int64_t nex_task_application_execute(const nexrt::TaskCodeDescriptor *);
int64_t nex_task_application_execute_at(const nexrt::TaskCodeDescriptor *,const nexrt::NativeSite *);
int64_t nex_task_application_execute_limits(const nexrt::TaskCodeDescriptor *,int64_t,const char *const *,int64_t,int64_t,int64_t);
int64_t nex_task_application_execute_limits_at(const nexrt::TaskCodeDescriptor *,int64_t,const char *const *,int64_t,int64_t,int64_t,const nexrt::NativeSite *);
}
