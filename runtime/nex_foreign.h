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
// Private source-task context. Capture on the explicitly authorized caller;
// later binds retain that lexical/request authority across task resumes. Ending
// the original scope revokes it; a copied snapshot never renews authorization.
class CapturedForeignScope {
  struct Impl;std::shared_ptr<const Impl> impl;
  explicit CapturedForeignScope(std::shared_ptr<const Impl>);
  friend CapturedForeignScope captureForeignScope(bool);
public:
  CapturedForeignScope()=default;
  void check()const;
  ForeignSignature signature(const std::string &)const;
  ForeignFunction bind(const std::string &,std::function<void()> poll={})const;
  ForeignCallLimits callLimits()const;
};
CapturedForeignScope captureForeignScope(bool unavailableDeferred=false);
// Used by the interpreter and native value bridge. A retained context cannot
// extend its lexical authority. No module pointer or owner crosses this API.
Value invokeScopedForeign(const std::string &binding,std::span<const Value> arguments,
                          std::function<void()> poll={});
// Terminal cleanup for standalone native finish/failure. Explicit host catalogues
// shared by these contexts are revoked; request-local failures use unwinding.
void resetForeignScopes()noexcept;
}
