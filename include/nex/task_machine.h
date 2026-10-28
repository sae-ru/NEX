#pragma once
#include "nex/task_transition.h"

namespace nex {
class TaskMachine {
  struct Impl;std::unique_ptr<Impl> impl;
public:
  TaskMachine(const Program &,const std::string &entry,
    const std::vector<nexrt::Value> &arguments={},uint64_t limit=1000000,
    nexrt::Value closure={},unsigned outerDepth=0,size_t maximumState=262144,
    TaskControlPoll controlPoll={});
  ~TaskMachine();
  TaskMachine(const TaskMachine&)=delete;
  TaskMachine &operator=(const TaskMachine&)=delete;
  TaskTransition advance();
  void restrictBudget(uint64_t remaining);
  size_t pendingActions()const;
  void resume(uint64_t ticket,nexrt::Value value={});
  void resumeSourceException(uint64_t ticket,const SourceException &);
  bool finished()const;
  uint64_t steps()const;
  const std::string &output()const;
};
}
