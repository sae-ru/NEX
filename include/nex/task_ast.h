#pragma once
#include "nex/task_transition.h"

namespace nex {
// Independent checked-AST control traversal. It never lowers or executes TaskIR.
// The host owns scheduling and capability operations; this private machine
// exposes suspension requests without enabling public language0.18 execution.
class TaskAstMachine {
  struct Impl;
  std::unique_ptr<Impl> impl;
public:
  TaskAstMachine(const Program &,const std::string &entry,
    const std::vector<nexrt::Value> &arguments={},uint64_t limit=1000000);
  ~TaskAstMachine();
  TaskAstMachine(const TaskAstMachine&)=delete;
  TaskAstMachine &operator=(const TaskAstMachine&)=delete;
  TaskTransition advance();
  void resume(uint64_t ticket,nexrt::Value value={});
  bool finished()const;
  uint64_t steps()const;
  const std::string &output()const;
};
}
