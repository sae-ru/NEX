#pragma once
#include "nex/project.h"
namespace nex {
// Process output is untrusted. Mapping verifies the report against the selected
// checked program and build manifest before consulting this store's local IDs.
llvm::json::Value parseNativeManifest(const std::string &text);
llvm::json::Value nativeDiagnostics(const Program &program,const llvm::json::Value &manifest,
  Store &store,const std::string &errors);
}
