#pragma once
#include "nex_value.h"
#include <functional>
#include <memory>

namespace nexrt {
// Host-owned capability. No descriptor or mutable resource becomes a NEX value.
class TextFiles {
  struct Impl;
  std::unique_ptr<Impl> impl;
public:
  static constexpr size_t textLimit = 1024 * 1024;
  static constexpr size_t pathLimit = 4096;
  using Poll = std::function<void()>;
  TextFiles(const std::string &root, bool writable);
  ~TextFiles();
  TextFiles(const TextFiles&) = delete;
  TextFiles &operator=(const TextFiles&) = delete;
  Value read(const std::string &relative, const Poll &poll = {}) const;
  Value write(const std::string &relative, const std::string &text, const Poll &poll = {}) const;
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
void resetFileEnvironment() noexcept;
}
