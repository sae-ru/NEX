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
  // Unarchived private source context, present only for the private debug emitter.
  std::string debugContext;
  int64_t descriptorABI=0;
};
TaskNativeStep emitTaskNativeStep(const Program &,const std::string &entry);
TaskNativeStep emitSourceExceptionTasksPrototypeNative(const Program &,const std::string &entry="main",bool optimized=false);
TaskNativeStep emitSourceExceptionTasksPrototypeNativeHttp(const Program &,const std::string &entry="handle",bool optimized=false);
TaskNativeStep emitSourceExceptionTasksPrototypeNativeProfile(const Program &,const std::string &entry="main",bool optimized=false);
TaskNativeStep emitSourceExceptionTasksPrototypeNativeDebug(const Program &,const std::string &entry="main",bool optimized=false,uint64_t timeoutMs=5000);
}
