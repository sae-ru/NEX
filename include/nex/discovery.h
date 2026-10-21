#pragma once
#include "nex/language.h"

namespace nex {
// Readonly projection of the actual descriptor; source/store context is unused.
llvm::json::Value discover(const std::string &kind,const std::string &field,
                          const std::string &toolchain,const std::string &compilerBuild);
}
