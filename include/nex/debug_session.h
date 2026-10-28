#pragma once
#include "nex/backend.h"
namespace nex {
std::string nativeDebugBuildDirectory(const std::string &directory);
llvm::json::Value nativeDebugSession(const Program &program,const BuildResult &built,
  const std::string &directory,const std::string &compiler,const std::string &adapter,
  const std::vector<std::string> &arguments);
}
