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
class ForeignFunction {
  struct Impl;std::shared_ptr<Impl> impl;
  explicit ForeignFunction(std::shared_ptr<Impl> impl):impl(std::move(impl)){}
  friend class ForeignLibraries;
public:
  ForeignFunction()=default;
  bool isOpen()const noexcept;
  Value invoke(std::span<const Value> arguments,std::function<void()> poll={},ForeignCallLimits limits={})const;
};
class ForeignLibraries {
  struct Impl;std::shared_ptr<Impl> impl;
public:
  explicit ForeignLibraries(std::map<std::string,ForeignLibraryGrant> grants,size_t moduleLimit=64);
  ~ForeignLibraries();
  ForeignLibraries(const ForeignLibraries&)=delete;
  ForeignLibraries &operator=(const ForeignLibraries&)=delete;
  void revoke()noexcept;
  ForeignFunction bind(const std::string &library,const std::string &name,
                       const ForeignSignature &signature,const std::string &expectedManifestSha256,
                       std::function<void()> poll={})const;
};
}
