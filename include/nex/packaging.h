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
// Consume an actual checked project artifact. This never rebuilds its source or
// opens a graph Store. Project foreign-pin projection is handled separately.
llvm::json::Value packageNativeArtifact(const Program &program,const BuildResult &built,
                                      const PackageOptions &options);
}
