#pragma once
#include "nex/project_build.h"
namespace nex {
// Data-only physical namespace projection. No tool is invoked or code executed.
// Materialization is confined to a new owned container; package/component
// aliases retain their checked physical relationships inside that container.
llvm::json::Value captureProject(const std::string &root,const std::string &manifest,
  const std::string &source,const std::string &component,const std::set<std::string> &configurations,
  const std::map<std::string,std::string> &overlays = {});
std::string materializeProjectCapture(const llvm::json::Value &capture,const std::string &container);
void verifyProjectCapture(const llvm::json::Value &capture,const std::string &container);
void validateProjectCaptureData(const llvm::json::Value &capture);
void validateProjectCapturePlans(const llvm::json::Value &capture,const std::string &container);
}
