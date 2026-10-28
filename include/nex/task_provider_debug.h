#pragma once
#include "nex/backend.h"

namespace nex {
using NativeTaskDebugCheckedSources=std::map<std::string,Program>;
std::string nativeTaskDebugMetadataHash(const NativeTaskDebugCatalog &,
                                       const NativeTaskDebugSourceUnion &);
NativeTaskDebugCheckedSources validateNativeTaskDebugSources(
  const NativeTaskDebugCatalog &,const NativeTaskDebugSourceUnion &,
  const std::map<std::string,std::string> &bundles);
NativeTaskDebugCheckedSources loadNativeTaskDebugSources(
  const std::string &directory,const NativeTaskDebugCatalog &,
  const NativeTaskDebugSourceUnion &);
// Owns only compiler-created source/projection files, never an inferior value.
llvm::json::Array writeNativeTaskDebugSources(const std::string &directory,
  const NativeTaskDebugCatalog &,const NativeTaskDebugSourceUnion &,
  const std::map<std::string,std::string> &bundles);
llvm::json::Array nativeTaskDebugSourceInputs(const NativeTaskDebugCatalog &,
  const NativeTaskDebugSourceUnion &,const std::map<std::string,std::string> &bundles);
// codeImages: exact {component,path,key,hash,sha256,uuid,kind} rows; runtimeImage
// is the actual catalog owner (the executable for Static, the common DSO otherwise).
llvm::json::Object finalizeNativeTaskDebugManifest(llvm::json::Object base,
  const NativeTaskDebugCatalog &,const NativeTaskDebugSourceUnion &,
  const std::map<std::string,std::string> &bundles,
  llvm::json::Array codeImages,llvm::json::Object runtimeImage);
NativeTaskDebugCheckedSources validateNativeTaskDebugManifest(
  const llvm::json::Object &manifest,const std::string &directory);
// Rebind the legacy physical-image/symbol inventory from immutable raw metadata
// through the separately verified image mappings. Raw files are never rewritten.
llvm::json::Array relocateNativeTaskDebugOwnedImages(
  const llvm::json::Object &rawManifest,const llvm::json::Array &imageMappings,
  const std::string &rawDirectory,const std::string &publishedDirectory);
// Verify an already-completed current-action provider build without repairing it.
llvm::json::Object inspectNativeTaskDebugBuildInputs(const BuildResult &);
}
