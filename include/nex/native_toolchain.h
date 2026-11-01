#pragma once
#include "nex/backend.h"

namespace nex {
struct NativeToolchain {
  std::string compiler, target, sysroot, linker, archiver, debugPackager, sdkManifest;
  std::string wasmLinker, wasmCompiler;
  std::string windowsRuntime, windowsNotices;
  std::string sqliteInclude, sqliteLibrary, opensslInclude, opensslSSL, opensslCrypto;
  bool hostCompatible = true;
  std::vector<std::string> driver;
  std::string identity;
};
NativeToolchain configureNative(const BuildOptions &options);
// Wasm uses the host SDK's all-target LLVM tools, independently of an explicit
// native target compiler/sysroot. NEX_WASM_CLANG is the dedicated override.
NativeToolchain configureWasm();
// Completed Windows links retain hashes for statically linked vendor notices.
llvm::json::Array nativeStaticLinkInputs(const NativeToolchain &tools,bool storage,bool foreign,bool server);
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
