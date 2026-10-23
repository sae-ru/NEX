#pragma once
#include "nex/language.h"
#include "nex_value.h"
#include <functional>

namespace nex {
// A scheduler-owned poll preserves one root control boundary through nested
// source calls and atom helpers. It must not resume or reenter the machine.
using TaskControlPoll=std::function<void(Span)>;
struct TaskAtomResult {nexrt::Value value;uint64_t steps=0;std::string output;};
// Internal semantic harness for continuation lowering. This is not a scheduler
// or public reference-task backend. Host resource effects require a later bridge.
TaskAtomResult evaluateTaskAtom(const Program &,E,
    const std::map<std::string,nexrt::Value> &,uint64_t limit,unsigned outerDepth=0,const TaskControlPoll *controlPoll=nullptr);
struct TaskTransition {
  enum Kind { Waiting,Done } kind=Done;
  std::string operation;std::vector<nexrt::Value> arguments;
  nexrt::Value value;Span span;Type result;
  uint64_t ticket=0;size_t callDepth=0,pc=0;
};
// Existing whole-file calls use a distinct typed host boundary in020; these
// are not additional scheduling intrinsics or a general host-operation API.
inline bool taskFileReadOperation(const std::string &operation){
  return operation=="file_read_text"||operation=="file_read_bytes";
}
inline bool taskFileBuiltin(const std::string &operation){
  return taskFileReadOperation(operation)||operation=="file_write_text"||
    operation=="file_write_bytes"||operation=="file"||streamFileBuiltins().contains(operation);
}
}
