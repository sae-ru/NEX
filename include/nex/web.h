#pragma once
#include "nex/backend.h"

namespace nexrt { struct TaskExecutionLimits; }

namespace nex {
llvm::json::Value previewWebApp(const std::string &directory,const std::vector<std::string> &arguments,
  unsigned timeout,bool machine);
struct WebModule {
  std::string source;
  llvm::json::Value mapping;
  // Resumable exports return task.Step<T>; invoke them through task.call/run.
  // Pure modules retain their ordinary synchronous function signatures.
  bool asynchronous=false;
  // Source-error helper requested by public025 and retained private emitters.
  // The historical member name is retained for existing C++ callers.
  bool privateSourceExceptions=false;
};
// Only the reachable client/shared closure is emitted. Export names are caller supplied.
WebModule emitTypeScript(const Program &program,const std::map<std::string,std::string> &entries);
// No public version selection, graph publication or browser UI enablement.
WebModule emitSourceExceptionsPrototypeTypeScript(const Program &,const std::map<std::string,std::string> &entries);
WebModule emitSourceExceptionTasksPrototypeTypeScript(const Program &,const std::map<std::string,std::string> &entries);
void writeWebModule(const WebModule &module,const std::string &directory);
// All transitive adapter sources participate in a generated module's cache key.
std::string webRuntimeInputs(const WebModule &module);
ProcessResult runTypeScriptTest(const WebModule &module,const std::string &directory,unsigned timeout=30,
  const nexrt::TaskExecutionLimits *limits=nullptr);
llvm::json::Value inspectWebApp(const Program &program);
llvm::json::Value generateWebApp(const Program &program,const std::string &directory);
llvm::json::Value buildWebApp(const Program &program,const std::string &directory,const std::string &profile);
}
