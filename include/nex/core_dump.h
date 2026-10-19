#pragma once
#include "nex/language.h"
namespace nex {
struct CoreOptions {
  std::string core,manifest,compiler,expression;
  int thread=-1,frame=-1;
  unsigned timeout=60;
  // Internal capsule projection, never selected by an ordinary debug manifest.
  std::string recordedProgram;
};
llvm::json::Value inspectCore(const CoreOptions &options);
llvm::json::Value inspectCoreCapsule(const std::string &directory,const CoreOptions &options);
llvm::json::Value exportCoreCapsule(const std::string &directory,const CoreOptions &options);
}
