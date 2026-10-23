#pragma once
#include "nex/backend.h"
#include <functional>
namespace nex {
struct ProfileOptions {
  std::string output,scenario;
  unsigned events=100000,timeout=30;
  std::vector<std::string> arguments;
  std::string directory;
  std::map<std::string,std::string> environment;
  std::function<void(int)> interrupted;
  // Private compiler-owned launch prefix/evidence, never executable workload data.
  std::vector<std::string> launcher;
  std::function<llvm::json::Value()> additionalEvidence;
};
llvm::json::Value profileNative(const Program &program,const BuildResult &built,llvm::json::Value graph,const ProfileOptions &options);
// Task schema2 is validated before graph attribution or budget use. These
// compiler-owned readers never execute code from a report.
llvm::json::Value parseTaskProfileRuntimeReport(const std::string &text);
void validateTaskProfileRuntimeReport(const llvm::json::Object &report,
                                     const llvm::json::Object &expectedIdentity,
                                     const nexrt::TaskExecutionLimits &effective);
std::string serializeTaskProfileReport(llvm::json::Object &report,size_t runtimeBytes,
                                       size_t maximumBytes=64*1024*1024);
llvm::json::Array taskProfileBudgetIncomplete(const llvm::json::Object &report,
                                            const llvm::json::Object &budget);
}
