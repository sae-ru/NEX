#pragma once
#include "nex/task_transition.h"

namespace nex {
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
