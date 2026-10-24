#pragma once
#include "nex_ffi_host.h"
#include "nex_resource.h"
#include <map>
#include <set>
namespace nexrt {
std::string foreignPlatform();
std::string foreignSignatureDigest(const ForeignSignature &signature);
struct ForeignLibraryGrant {
  std::string directory;
  std::string manifestSha256;
  std::set<std::string> exports;
};
struct ForeignBundleSnapshot {
  std::string manifest,entry;
  std::map<std::string,std::string> files,exports;
};
// Copies and verifies bounded inventory bytes without dlopen or module entry.
ForeignBundleSnapshot inspectForeignBundle(const ForeignLibraryGrant &grant,
    size_t maximumBytes=256*1048576,std::function<void()> poll={});
class ForeignFunction {
  struct Impl;std::shared_ptr<Impl> impl;
  explicit ForeignFunction(std::shared_ptr<Impl> impl):impl(std::move(impl)){}
  friend class ForeignLibraries;
public:
  ForeignFunction()=default;
  bool isOpen()const noexcept;
  const ForeignSignature &signature()const;
  Value invoke(std::span<const Value> arguments,std::function<void()> poll={},ForeignCallLimits limits={})const;
  Value invokeWithResourceScope(std::span<const Value> arguments,ResourceAccess scope,
      std::function<void()> poll={},ForeignCallLimits limits={})const;
  Value invokeInRegion(std::span<const Value>,ResourceAccess,ResourceRegionAuthority,
      std::shared_ptr<ResourceExecutor>,std::function<void()> poll={},ForeignCallLimits limits={})const;
};
class ForeignLibraries {
  struct Impl;std::shared_ptr<Impl> impl;
public:
  explicit ForeignLibraries(std::map<std::string,ForeignLibraryGrant> grants,size_t moduleLimit=64,
      size_t resourceLimit=64,uint64_t resourceBytes=64*1048576);
  ~ForeignLibraries();
  ForeignLibraries(const ForeignLibraries&)=delete;
  ForeignLibraries &operator=(const ForeignLibraries&)=delete;
  void revoke()noexcept;
  std::vector<std::string> grantedDirectories()const;
  std::map<std::string,ForeignLibraryGrant> operatorGrants()const;
  size_t moduleLimit()const noexcept;
  size_t resourceLimit()const noexcept;
  uint64_t resourceBytesLimit()const noexcept;
  uint64_t resourceBytesUsed()const noexcept;
  ForeignFunction bind(const std::string &library,const std::string &name,
                       const ForeignSignature &signature,const std::string &expectedManifestSha256,
                       std::function<void()> poll={})const;
  // Explicit coordinator-captured physical request authority. This overload
  // never looks up the calling worker's transient RequestScope.
  ForeignFunction bindWithResourceScope(const std::string &library,const std::string &name,
                       const ForeignSignature &signature,const std::string &expectedManifestSha256,
                       ResourceAccess,std::function<void()> poll={})const;
};
}
