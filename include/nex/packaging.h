#pragma once
#include "nex/backend.h"

namespace nex {
struct PackageOptions {
  std::string directory, notices, compiler;
  bool dpkgNotices = false;
};
llvm::json::Value packageApplication(const Program &program, const BuildResult &build,
                                    const PackageOptions &options);
}
