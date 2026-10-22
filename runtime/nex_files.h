#pragma once
#include "nex_value.h"
#include "nex_resource.h"
#include <functional>
#include <memory>

namespace nexrt {
class FileReadLease;
// Host-owned capability. No descriptor or mutable resource becomes a NEX value.
class TextFiles {
  struct Impl;
  std::shared_ptr<Impl> impl;
  friend class FileScope;
  friend class FileReadLease;
  friend FileReadLease captureFileReadLease(const std::string &,bool);
  explicit TextFiles(std::shared_ptr<Impl> impl):impl(std::move(impl)){}
  std::unique_ptr<TextFiles> retain() const;
  FileReadLease readLeaseIn(const ResourceAccess &,const std::string &) const;
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
#ifndef _WIN32
// Private host-only read bridge. Capturing resolves a lexical grant on its
// coordinator; a worker sees only this revocation-aware physical lease/path.
// No source file, Value, descriptor or TLS context is transported.
class FileReadLease {
  struct State;
  std::shared_ptr<State> state;
  friend class TextFiles;
  explicit FileReadLease(std::shared_ptr<State> state):state(std::move(state)){}
public:
  FileReadLease()=default;
  uint64_t identity()const noexcept;
  void check()const;
  std::vector<uint8_t> read(const TextFiles::Poll &poll={})const;
};
FileReadLease captureFileReadLease(const std::string &relative,bool environmentAllowed=true);
#endif
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
