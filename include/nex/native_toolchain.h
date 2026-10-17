#pragma once
#include "nex/backend.h"

namespace nex {
struct NativeToolchain {
  std::string compiler, target, sysroot;
  std::string sqliteInclude, sqliteLibrary, opensslInclude, opensslSSL, opensslCrypto;
  bool hostCompatible = true;
  std::vector<std::string> driver;
  std::string identity;
};
NativeToolchain configureNative(const BuildOptions &options);
struct NativeToolchainSnapshot {
  std::string hash, target;
  bool hostCompatible = true;
  llvm::json::Value manifest = nullptr, inputs = nullptr;
};
// Read-only identity capture; never runs a driver from a manifest/receipt.
NativeToolchainSnapshot inspectNativeToolchain(const BuildOptions &options);
void requireNativeHost(const BuildOptions &options);
void requireNativeHost(const BuildResult &result);
}
