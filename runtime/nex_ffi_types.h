#pragma once
#include "nex_ffi_host.h"
namespace nexrt::foreign_detail {
// Per-call authorities are separate from the immutable, reusable type layout.
class TypedContext {
  friend class TaskCodec;
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
// A typed host-only owner table accompanies copied data. Indices in bytes are
// never authorities: reconstruction needs the genuine table and logical region.
// No source Value, borrowed pointer or C invocation token is retained here.
struct TaskForeignSnapshot {
  std::vector<uint8_t> bytes;
  std::vector<ExternalResource> owners;
};
// Exact checked nominal layouts. The default copied-data codec continues to
// reject resources. Its explicit owned mode requires a genuine region on each
// conversion; file/function values remain unavailable in either mode.
class TaskCodec {
  struct Impl;std::shared_ptr<const Impl> impl;
public:
  explicit TaskCodec(const ForeignSignature &,bool owned=false);
  std::vector<uint8_t> encodeArguments(std::span<const Value>,const std::function<void()> &poll={})const;
  std::vector<Value> decodeArguments(std::span<const uint8_t>,const std::function<void()> &poll={})const;
  std::vector<uint8_t> encodeResult(const Value &,const std::function<void()> &poll={})const;
  Value decodeResult(std::span<const uint8_t>,const std::function<void()> &poll={})const;
  TaskForeignSnapshot snapshotArguments(std::span<const Value>,const ResourceRegionAuthority&,const std::function<void()> &poll={})const;
  std::vector<Value> restoreArguments(const TaskForeignSnapshot&,const ResourceRegionAuthority&,const std::function<void()> &poll={})const;
  TaskForeignSnapshot snapshotResult(const Value&,const ResourceRegionAuthority&,const std::function<void()> &poll={})const;
  Value restoreResult(const TaskForeignSnapshot&,const ResourceRegionAuthority&,const std::function<void()> &poll={})const;
  static constexpr size_t byteLimit=1048576;
  static constexpr size_t ownerLimit=64;
};
}
