#pragma once
#include "nex/backend.h"
namespace nex {
struct TaskProcessResult {
  ProcessResult process;
  bool timedOut=false,outputLimit=false;
  int interrupted=0;
};
// A synchronous POSIX process-group supervisor used by task checks. Child
// compilers/tools inherit its group; the leader is observed before reaping.
TaskProcessResult runTaskProcess(const std::vector<std::string> &arguments,const std::string &directory,
  const std::map<std::string,std::string> &environment,unsigned seconds,const std::string &logs);
}
