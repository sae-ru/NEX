#pragma once
#include "nex/language.h"
#include "nex/packaging.h"

namespace nex {
struct ProjectBuildOptions {
  std::string kind = "plan", component, configuration, directory;
  std::string compilerVersion, compilerBuild;
  PackageOptions package;
};
// A checked physical build description. Planning never opens a Store, invokes
// an external tool, executes source, or creates a cache/output directory.
llvm::json::Value buildProject(const std::string &root,const std::string &manifest,
                              const std::string &text,const ProjectBuildOptions &options);
}
