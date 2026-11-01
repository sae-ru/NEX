#pragma once
#include "nex/backend.h"
namespace nex {
struct TaskProcessResult {
  ProcessResult process;
  bool timedOut=false,outputLimit=false;
  int interrupted=0;
};
// Native task-check supervisor: POSIX process groups or a Windows Job Object.
// Child compilers/tools belong to the same supervised process tree.
TaskProcessResult runTaskProcess(const std::vector<std::string> &arguments,const std::string &directory,
  const std::map<std::string,std::string> &environment,unsigned seconds,const std::string &logs);
}
