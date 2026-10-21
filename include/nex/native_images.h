#pragma once
#include "nex/backend.h"
namespace nex {
std::string nativeImageUUID(const std::string &path);
// Inputs originate only in a checked project plan. Static dependencies are the
// archive frontier of this image; dynamic dependencies include its DSO closure.
struct NativeImageInput {
  std::string name,kind;
  const Program *program=nullptr;
  BuildOptions options;
  BuildResult stage;
  std::vector<std::string> staticDependencies,dynamicDependencies;
};
struct NativeImageResults {
  std::map<std::string,BuildResult> images;
  llvm::json::Value runtime=nullptr;
};
NativeImageResults buildNativeImages(const std::string &directory,
                                    const std::vector<NativeImageInput> &inputs);
}
