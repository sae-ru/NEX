#pragma once
#include "nex/backend.h"
#include "nex/project.h"
#include "nex/foreign_catalogue.h"

namespace nex {
struct PackageOptions {
  std::string directory, notices, compiler;
  bool dpkgNotices = false;
  std::string foreign;
};
using ForeignSelection=std::map<std::string,std::set<std::string>>;
struct ForeignPackagePreparation {
  std::string directory;
  ForeignCatalogueSnapshot snapshot;
  llvm::json::Value report=nullptr;
  llvm::json::Object files;
};
struct ForeignProgramProjection {
  Program program;
  llvm::json::Value report=nullptr;
};
struct ForeignPackageArtifact {
  std::string directory;
  llvm::json::Value projection=nullptr;
  llvm::json::Object files;
};
// Compiler-private packaging data. Preparation only inspects/copies native
// images; projection edits exact literal tokens and rechecks the source model.
ForeignPackagePreparation prepareForeignPackage(const PackageOptions &options,
  const ForeignSelection &selection,const std::string &workingDirectory);
ForeignProgramProjection projectForeignProgram(const Program &program,
  const std::set<std::string> &functions,const ForeignPackagePreparation &prepared,
  const std::string &root);
ForeignPackagePreparation selectForeignPackage(const ForeignPackagePreparation &prepared,
  const ForeignSelection &selection,const std::string &directory);
llvm::json::Value packageApplication(const Program &program, BuildOptions buildOptions,
    const std::string &buildDirectory, const std::string &root, Store &store,
    const PackageOptions &options);
// Consume an actual checked project artifact. This never rebuilds its source or
// opens a graph Store. Project foreign-pin projection is handled separately.
llvm::json::Value packageNativeArtifact(const Program &program,const BuildResult &built,
                                      const PackageOptions &options,
                                      const ForeignPackageArtifact *foreign=nullptr);
}
