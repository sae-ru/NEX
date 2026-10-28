#pragma once
#include "nex_ffi_loader.h"
namespace nexrt {
// Explicit operator configuration, never an ambient environment grant.
std::shared_ptr<ForeignLibraries> loadForeignLibraries(const std::string &configuration);
// Empty in ordinary builds. Packaged builds resolve their reviewed catalogue
// from the actual executable location, independently of argv[0] and cwd.
std::string packagedForeignCatalogue();
struct ForeignScopeLimits {
  size_t bindings=4096;
  uint64_t metadataBytes=64*1048576;
  ForeignCallLimits call;
};
class ForeignScope {
  struct Impl;std::unique_ptr<Impl> impl;
public:
  explicit ForeignScope(std::shared_ptr<ForeignLibraries> libraries,ForeignScopeLimits limits={});
  ~ForeignScope();
  ForeignScope(const ForeignScope&)=delete;
  ForeignScope &operator=(const ForeignScope&)=delete;
};
// Used by the interpreter and native value bridge. A retained context cannot
// extend its lexical authority. No module pointer or owner crosses this API.
Value invokeScopedForeign(const std::string &binding,std::span<const Value> arguments,
                          std::function<void()> poll={});
// Terminal cleanup for standalone native finish/failure. Explicit host catalogues
// shared by these contexts are revoked; request-local failures use unwinding.
void resetForeignScopes()noexcept;
}
