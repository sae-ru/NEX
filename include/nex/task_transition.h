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
}
