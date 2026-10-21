#pragma once
#include "nex/language.h"
#include "nex/packaging.h"
#include "nex/profiling.h"

namespace nex {
struct ProjectPackageProjection;
struct ProjectBuildOptions {
  std::string kind = "plan", component, configuration, directory;
  std::string compilerVersion, compilerBuild;
  PackageOptions package;
  bool machine = true;
  std::string compiler, adapter = "lldb", foreign;
  std::vector<std::string> arguments;
  unsigned timeout = 30;
  bool explicitTimeout = false;
  ProfileOptions profiling;
  // Private test-driver override, never accepted from a build manifest or CLI.
  std::string testFunction, selectedTest, expectedPlanHash;
  std::map<std::string,std::string> sourceOverlays;
  bool archivedSources = false;
  std::string workload;
  // Compiler-owned projection; never accepted from a manifest, task or CLI.
  std::shared_ptr<const ProjectPackageProjection> packageProjection;
};
// A checked physical build description. Planning never opens a Store, invokes
// an external tool, executes source, or creates a cache/output directory.
llvm::json::Value buildProject(const std::string &root,const std::string &manifest,
                              const std::string &text,const ProjectBuildOptions &options);
}
