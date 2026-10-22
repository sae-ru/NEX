#pragma once
#include "nex/task_ir.h"
#include "nex_value.h"

namespace nex {
struct TaskAtomResult {nexrt::Value value;uint64_t steps=0;std::string output;};
// Internal semantic harness for continuation lowering. This is not a scheduler
// or public reference-task backend. Host resource effects require a later bridge.
TaskAtomResult evaluateTaskAtom(const Program &,E,
    const std::map<std::string,nexrt::Value> &,uint64_t limit,unsigned outerDepth=0);
struct TaskTransition {
  enum Kind { Waiting,Done } kind=Done;
  std::string operation;std::vector<nexrt::Value> arguments;
  nexrt::Value value;Span span;Type result;
  uint64_t ticket=0;size_t callDepth=0,pc=0;
};
class TaskMachine {
  struct Impl;std::unique_ptr<Impl> impl;
public:
  TaskMachine(const Program &,const std::string &entry,
    const std::vector<nexrt::Value> &arguments={},uint64_t limit=1000000);
  ~TaskMachine();
  TaskMachine(const TaskMachine&)=delete;
  TaskMachine &operator=(const TaskMachine&)=delete;
  TaskTransition advance();
  void resume(uint64_t ticket,nexrt::Value value={});
  bool finished()const;
  uint64_t steps()const;
  const std::string &output()const;
};
}
