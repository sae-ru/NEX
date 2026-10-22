#pragma once
#include "nex_task_frame.h"

namespace nexrt {
// One standalone image owns every descriptor until its joined executor and all
// retained values are destroyed. No compiler, AST or TaskIR participates here.
int64_t executeTaskApplication(const TaskCodeDescriptor &,SourceLocation);
}
extern "C" {
int64_t nex_task_application_execute(const nexrt::TaskCodeDescriptor *);
int64_t nex_task_application_execute_at(const nexrt::TaskCodeDescriptor *,const nexrt::NativeSite *);
}
