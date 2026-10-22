#pragma once
#include "nex/task_ast.h"
#include "nex_task_limits.h"
#include <functional>

namespace nex {
struct TaskReferenceResult {
  nexrt::Value value;
  std::string output;
  uint64_t steps=0;
  size_t tasks=0,scopes=0,channels=0;
  nexrt::TaskExecutionLimits limits;
  unsigned executionWorkers=1; // Independent reference scheduling is serial.
};
// Independent cooperative scheduler over checked AST machines. It creates no
// OS worker, native TaskGroup, TaskIR or compiled frame. The observer sees owned
// transition snapshots for diagnostics; it must not mutate them or reenter.
using TaskReferenceObserver=std::function<void(size_t,const TaskTransition&)>;
TaskReferenceResult evaluateTaskReference(const Program &,const std::string &entry="main",
    const std::vector<nexrt::Value> &arguments={},uint64_t limit=1000000,
    TaskReferenceObserver observer={},const nexrt::TaskExecutionLimits *taskLimits=nullptr);
}
