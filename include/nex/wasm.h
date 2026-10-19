#pragma once
#include "nex/backend.h"
namespace nex {
llvm::json::Value buildWasm(const Program &program,const std::string &buildDirectory,
                           const std::string &entry,const std::string &profile,
                           const std::string &outputDirectory="");
}
