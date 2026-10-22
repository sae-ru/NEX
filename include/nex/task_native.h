#pragma once
#include "nex/task_ir.h"
namespace nex {
// Private compiled continuation stage. This is not a public build entry point.
// Steps support logical direct/indirect calls and cooperative yield.
// Owned scope/task/channel requests use the private coroutine bridge.
struct TaskNativeStep {
  std::string mlir,symbol,descriptorSymbol;
  std::vector<int64_t> slotKinds;
  std::vector<TaskSlotId> parameters;
};
TaskNativeStep emitTaskNativeStep(const Program &,const std::string &entry);
}
