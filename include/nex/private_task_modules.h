#pragma once
#include "nex/backend.h"
#include "nex/task_native.h"
namespace nex {
// Explicit compiler-private025 source modules. No public project/store format.
struct PrivateTaskModuleEmission {
  TaskNativeStep native;
  llvm::json::Object record;
};
llvm::json::Object planSourceExceptionTaskModules(const Program &,const llvm::json::Object &architecture);
llvm::json::Object sourceExceptionTaskModuleDebugContext(const Program &,const llvm::json::Object &architecture);
llvm::json::Object describeSourceExceptionTaskInstances(const Program &,const std::string &templateFilter="",unsigned offset=0,unsigned limit=64);
PrivateTaskModuleEmission emitSourceExceptionTaskModule(const Program &,const llvm::json::Object &architecture,
    const std::string &component,bool optimized=false);
void validateSourceExceptionTaskModule(const Program &,const llvm::json::Object &architecture,
    const std::string &component,const llvm::json::Object &record);
namespace detail {
struct PrivateTaskModuleCodegen {
  std::string entry,profileAccessor,profileComponent,debugAccessor,debugComponent;
  bool application=false,http=false,profiling=false,debugging=false,reads=false,writes=false,streams=false,foreign=false;
  uint64_t timeoutMs=5000;
  std::set<std::string> definitions,complete,exports;
  std::map<std::string,NativeTaskExport> imports;
};
void validatePrivateTaskModuleFunction(const Program &,const Function &);
void validatePrivateTaskModuleEntry(const Program &,const std::string &,bool application,bool http);
TaskNativeStep emitPrivateTaskModule(const Program &,const PrivateTaskModuleCodegen &,bool optimized);
}
}
