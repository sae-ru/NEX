#pragma once
#include "nex/server_workload.h"
namespace nex {
// Caller owns the private directory and stops the native group before cleanup.
// Credentials and mutable state are fresh per check and are never receipt inputs.
struct TaskWorkloadState {
  std::vector<std::string> arguments;
  std::map<std::string,std::string> environment;
  llvm::json::Object description;
};
TaskWorkloadState createTaskWorkloadState(const ServerWorkload &workload,
  const std::string &ownedDirectory,unsigned workers);
llvm::json::Array taskWorkloadBudgetFailures(const llvm::json::Object &profile,
  const llvm::json::Object &budget);
}
