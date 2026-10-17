#pragma once
#include "nex/backend.h"
namespace nex {
struct ProfileOptions {
  std::string output,scenario;
  unsigned events=100000,timeout=30;
};
llvm::json::Value profileNative(const Program &program,const BuildResult &built,llvm::json::Value graph,const ProfileOptions &options);
}
