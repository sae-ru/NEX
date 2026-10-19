#pragma once
#include "nex/language.h"
namespace nex {
struct CoreOptions {
  std::string core,manifest,compiler,expression;
  int thread=-1,frame=-1;
  unsigned timeout=60;
};
llvm::json::Value inspectCore(const CoreOptions &options);
}
