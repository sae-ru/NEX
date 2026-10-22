#pragma once
#include "nex/task_ir.h"
namespace nex {
// Private compiled continuation stage. This is not a public build entry point.
// Current steps support cooperative yield; other scheduler requests are rejected.
struct TaskNativeStep {
  std::string mlir,symbol;
  std::vector<int64_t> slotKinds;
  std::vector<TaskSlotId> parameters;
};
TaskNativeStep emitTaskNativeStep(const Program &,const std::string &entry);
}
