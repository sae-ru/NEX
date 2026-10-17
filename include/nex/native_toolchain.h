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
void requireNativeHost(const BuildOptions &options);
void requireNativeHost(const BuildResult &result);
}
