#pragma once
#include "nex/task_ir.h"
namespace nex {
// Private compiled continuation stage. This is not a public build entry point.
// Steps support logical direct/indirect calls and cooperative yield.
// Scope/channel scheduler requests remain rejected.
struct TaskNativeStep {
  std::string mlir,symbol,descriptorSymbol;
  std::vector<int64_t> slotKinds;
  std::vector<TaskSlotId> parameters;
};
TaskNativeStep emitTaskNativeStep(const Program &,const std::string &entry);
}
