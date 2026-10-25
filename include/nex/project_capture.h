#pragma once
#include "nex/project_build.h"
namespace nex {
// Data-only physical namespace projection. No tool is invoked or code executed.
// Materialization is confined to a new owned container; package/component
// aliases retain their checked physical relationships inside that container.
llvm::json::Value captureProject(const std::string &root,const std::string &manifest,
  const std::string &source,const std::string &component,const std::set<std::string> &configurations,
  const std::map<std::string,std::string> &overlays = {},
  const std::set<std::string> &debugConfigurations = {},SourceLanguage language=currentSourceLanguage);
// Explicit compiler-owned selection, never inferred from untrusted capture JSON.
std::string materializeProjectCapture(const llvm::json::Value &capture,const std::string &container,SourceLanguage language=currentSourceLanguage);
void verifyProjectCapture(const llvm::json::Value &capture,const std::string &container,SourceLanguage language=currentSourceLanguage);
void validateProjectCaptureData(const llvm::json::Value &capture,SourceLanguage language=currentSourceLanguage);
void validateProjectCapturePlans(const llvm::json::Value &capture,const std::string &container,SourceLanguage language=currentSourceLanguage);
}
