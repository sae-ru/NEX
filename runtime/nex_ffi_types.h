#pragma once
#include "nex_ffi_host.h"
namespace nexrt::foreign_detail {
// Per-call authorities are separate from the immutable, reusable type layout.
class TypedContext {
  struct Impl;std::unique_ptr<Impl> impl;
public:
  explicit TypedContext(const ForeignSignature &signature);
  ~TypedContext();
  void arguments(std::span<const Value> values,const std::function<void()> &poll);
  void result(const Value &value,const std::function<void()> &poll);
  bool unitResult() const;
  size_t parameter(uint64_t index) const;
  size_t resultType() const;
  uint32_t kind(size_t type) const;
  uint64_t variants(size_t type) const;
  uint64_t children(size_t type,uint64_t variant) const;
  size_t child(size_t type,uint64_t variant,uint64_t index) const;
  uint64_t nominalBytes(size_t type,uint64_t variant) const;
  Value nominal(size_t type,uint64_t variant,std::span<const Value> fields,const std::function<void()> &poll);
  const std::string &description() const;
  std::pair<std::string,std::string> resource(size_t type)const;
  bool resourceConstructible(size_t type)const;
  bool resourceDeclared(const std::string &name,const std::string &identity)const;
};
}
