#pragma once
#include "nex/backend.h"
#include "nex/project.h"

namespace nex {
struct PackageOptions {
  std::string directory, notices, compiler;
  bool dpkgNotices = false;
  std::string foreign;
};
llvm::json::Value packageApplication(const Program &program, BuildOptions buildOptions,
    const std::string &buildDirectory, const std::string &root, Store &store,
    const PackageOptions &options);
}
