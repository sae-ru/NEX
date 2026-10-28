#pragma once
#include "nex_bytes.h"
#include "nex_resource.h"
#include <functional>

namespace nexrt {
enum class FileMode {Read,WriteTruncate,Append};
// Trusted runtime payload. Source syntax and the C FFI are separate contracts.
class FileResource {
  struct State;
  ResourceOwner<State> owner;
  friend class TextFiles;
  explicit FileResource(ResourceOwner<State> owner):owner(std::move(owner)){}
public:
  using Poll=std::function<void()>;
  FileResource()=default;
  uint64_t identity() const noexcept {return owner.identity();}
  bool isOpen() const noexcept {return owner.isOpen();}
  bool close() const noexcept {return owner.close();}
  ByteBuffer read(int64_t maximum,const Poll &poll={}) const;
  int64_t write(const ByteBuffer &bytes,const Poll &poll={}) const;
  int64_t seek(int64_t offset,const Poll &poll={}) const;
  int64_t size(const Poll &poll={}) const;
  void flush(const Poll &poll={}) const;
};
}
