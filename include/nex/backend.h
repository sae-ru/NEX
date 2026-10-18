#pragma once
#include "nex/language.h"
namespace nex {
struct BuildOptions {
  std::string profile = "debug", target, entry = "main";
  bool testEntry = false, libraryEntry = false;
  std::string toolchain;
};
struct BuildResult {
  std::string executable, mlir, llvm, key;
  bool cached = false;
  std::string notices;
  std::string compilation;
  unsigned compiledModules = 0, reusedModules = 0;
  std::string target, compilerTarget;
  bool hostCompatible = true;
  unsigned compiledFunctions = 0, reusedFunctions = 0;
  bool foreignCalls = false;
};
std::string emitMLIR(const Program &program, const std::string &entry = "main", bool testEntry = false,bool libraryEntry=false);
BuildResult build(const Program &program, const std::string &directory, const BuildOptions &options);
int execute(const std::vector<std::string> &arguments);
struct ProcessResult { int code; std::string output, errors; };
ProcessResult capture(const std::vector<std::string> &arguments,unsigned timeoutSeconds=30);
}
