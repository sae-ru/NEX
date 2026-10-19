#pragma once
#include "nex/backend.h"

namespace nex {
struct WebModule {
  std::string source;
  llvm::json::Value mapping;
};
// Only the reachable client/shared closure is emitted. Export names are caller supplied.
WebModule emitTypeScript(const Program &program,const std::map<std::string,std::string> &entries);
void writeWebModule(const WebModule &module,const std::string &directory);
ProcessResult runTypeScriptTest(const WebModule &module,const std::string &directory);
llvm::json::Value generateWebApp(const Program &program,const std::string &directory);
llvm::json::Value buildWebApp(const Program &program,const std::string &directory,const std::string &profile);
}
