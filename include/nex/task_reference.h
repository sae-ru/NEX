#pragma once
#include "nex/task_ast.h"
#include "nex/task_reference_external.h"
#include "nex_task_limits.h"
#include <functional>

namespace nexrt {class FileReadGrant;class FileWriteGrant;}
namespace nex {
struct TaskReferenceResult {
  nexrt::Value value;
  std::string output;
  uint64_t steps=0;
  size_t tasks=0,scopes=0,channels=0;
  nexrt::TaskExecutionLimits limits;
  unsigned executionWorkers=1; // Independent reference scheduling is serial.
  TaskReferenceExternalStats external;
};
// Independent cooperative scheduler over checked AST machines. It creates no
// source CPU worker, native TaskGroup, TaskIR or compiled frame. An optional
// private external host uses a separate bounded IO pool. The observer sees owned
// transition snapshots for diagnostics; it must not mutate them or reenter.
using TaskReferenceObserver=std::function<void(size_t,const TaskTransition&)>;
TaskReferenceResult evaluateTaskReference(const Program &,const std::string &entry="main",
    const std::vector<nexrt::Value> &arguments={},uint64_t limit=1000000,
    TaskReferenceObserver observer={},const nexrt::TaskExecutionLimits *taskLimits=nullptr,
    TaskReferenceExternalHost *externalHost=nullptr,
    // Trusted hosts capture this under their root RequestScope/FileScope.
    // Without it,020 owns an evaluation scope and captures current authority.
    const nexrt::FileReadGrant *fileGrant=nullptr,
    const nexrt::FileWriteGrant *writeGrant=nullptr);
// Private TaskIR-machine experiment. It reuses the serial coordinator's owned
// capability protocol, but executes explicit continuation instructions instead
// of AST actions. The ordinary reference above remains AST-only. No native code
// or physical CPU worker is exercised by this entry point.
TaskReferenceResult evaluateSourceExceptionTaskIRPrototype(const Program &,
    const std::string &entry="main",const std::vector<nexrt::Value> &arguments={},
    uint64_t limit=1000000,TaskReferenceObserver observer={},
    const nexrt::TaskExecutionLimits *taskLimits=nullptr);
}
