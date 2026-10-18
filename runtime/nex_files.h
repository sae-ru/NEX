#pragma once
#include "nex_value.h"
#include "nex_resource.h"
#include <functional>
#include <memory>

namespace nexrt {
enum class FileMode {Read,WriteTruncate,Append};
// Trusted C++ runtime interface. Not yet a source-language type or FFI ABI.
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
// Host-owned capability. No descriptor or mutable resource becomes a NEX value.
class TextFiles {
  struct Impl;
  std::shared_ptr<Impl> impl;
  friend class FileScope;
  explicit TextFiles(std::shared_ptr<Impl> impl):impl(std::move(impl)){}
  std::unique_ptr<TextFiles> retain() const;
public:
  static constexpr size_t byteLimit = 1024 * 1024;
  static constexpr size_t textLimit = byteLimit;
  static constexpr size_t pathLimit = 4096;
  using Poll = std::function<void()>;
  TextFiles(const std::string &root, bool writable);
  ~TextFiles();
  TextFiles(const TextFiles&) = delete;
  TextFiles &operator=(const TextFiles&) = delete;
  Value read(const std::string &relative, const Poll &poll = {}) const;
  Value write(const std::string &relative, const std::string &text, const Poll &poll = {}) const;
  Value readBytes(const std::string &relative, const Poll &poll = {}) const;
  Value writeBytes(const std::string &relative, const ByteBuffer &bytes, const Poll &poll = {}) const;
  ResourceDomain resourceScope(size_t limit=64) const;
  FileResource open(const std::string &relative,FileMode mode,const Poll &poll={}) const;
  FileResource openIn(const ResourceDomain &scope,const std::string &relative,FileMode mode,const Poll &poll={}) const;
};
// An explicit host scope overrides the process environment. Native HTTP calls
// do not inherit an environment capability unless the trusted host grants one.
class FileScope {
  struct Impl;
  std::unique_ptr<Impl> impl;
public:
  explicit FileScope(bool environmentAllowed = true);
  explicit FileScope(TextFiles &capability);
  ~FileScope();
  FileScope(const FileScope&) = delete;
  FileScope &operator=(const FileScope&) = delete;
};
Value fileReadText(const std::string &relative, bool environmentAllowed = true, const TextFiles::Poll &poll = {});
Value fileWriteText(const std::string &relative, const std::string &text, bool environmentAllowed = true, const TextFiles::Poll &poll = {});
Value fileReadBytes(const std::string &relative, bool environmentAllowed = true, const TextFiles::Poll &poll = {});
Value fileWriteBytes(const std::string &relative, const ByteBuffer &bytes, bool environmentAllowed = true, const TextFiles::Poll &poll = {});
FileResource fileOpen(const std::string &relative,FileMode mode,bool environmentAllowed=true,const TextFiles::Poll &poll={});
void resetFileEnvironment() noexcept;
}
