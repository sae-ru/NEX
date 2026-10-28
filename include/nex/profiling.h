#pragma once
#include "nex/backend.h"
#include <functional>
namespace nex {
struct ProfileOptions {
  std::string output,scenario;
  unsigned events=100000,timeout=30;
  std::vector<std::string> arguments;
  std::string directory;
  std::map<std::string,std::string> environment;
  std::function<void(int)> interrupted;
};
llvm::json::Value profileNative(const Program &program,const BuildResult &built,llvm::json::Value graph,const ProfileOptions &options);
}
