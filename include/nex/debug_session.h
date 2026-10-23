#pragma once
#include "nex/backend.h"
namespace nex {
void validateNativeDebugArguments(const std::vector<std::string> &arguments);
std::string nativeDebugBuildDirectory(const std::string &directory);
llvm::json::Value nativeDebugSession(const Program &program,const BuildResult &built,
  const std::string &directory,const std::string &compiler,const std::string &adapter,
  const std::vector<std::string> &arguments);
// Compiler-private relocation. Raw completed bytes remain untouched; only a new
// source-checked launch view is written. imageOutputs maps original absolute
// image paths to actual package/retained image files inside physicalDirectory.
llvm::json::Object relocateNativeTaskDebugSession(const Program &,const BuildResult &,
  const std::string &rawDirectory,const std::string &physicalDirectory,
  const std::string &publishedDirectory,const std::string &compiler,
  const std::map<std::string,std::string> &imageOutputs);
}
