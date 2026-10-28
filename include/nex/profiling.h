#pragma once
#include "nex/backend.h"
#include <functional>
namespace nex {
// Checked source ownership, supplied by the selected project/captured plan.
// A provider can own concrete sites absent from the root Program.
struct TaskProfileComponentSource {
  Program program;
  std::map<std::string,std::string> definitions;
};
using TaskProfileSourceUnion=std::map<std::string,TaskProfileComponentSource>;
llvm::json::Object validateTaskProfileSourceUnion(const NativeTaskProfileCatalog &,
                                                const TaskProfileSourceUnion &);
// The definitions are the checked physical image ledger, not runtime rows.
void validateTaskProfileCatalogOwnership(const NativeTaskProviderInfo &,
                                        const NativeTaskProfileCatalog &,
                                        const std::map<std::string,std::set<std::string>> &definitions);
// Closed current-action image/catalog pins; does not launch or repair a build.
llvm::json::Object inspectTaskProfileBuildInputs(const BuildResult &);
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
  // Compiler-owned, never decoded from an arbitrary runtime report.
  const TaskProfileSourceUnion *taskProviderSources=nullptr;
};
llvm::json::Value profileNative(const Program &program,const BuildResult &built,llvm::json::Value graph,const ProfileOptions &options);
// Task schema2 is validated before graph attribution or budget use. These
// compiler-owned readers never execute code from a report.
llvm::json::Value parseTaskProfileRuntimeReport(const std::string &text);
void validateTaskProfileRuntimeReport(const llvm::json::Object &report,
                                     const llvm::json::Object &expectedIdentity,
                                     const nexrt::TaskExecutionLimits &effective,
                                     const NativeTaskProfileCatalog *catalog=nullptr);
std::string serializeTaskProfileReport(llvm::json::Object &report,size_t runtimeBytes,
                                       size_t maximumBytes=64*1024*1024);
llvm::json::Array taskProfileBudgetIncomplete(const llvm::json::Object &report,
                                            const llvm::json::Object &budget);
}
