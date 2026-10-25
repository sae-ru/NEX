#pragma once
#include "nex_value.h"
#include "nex_resource.h"
#include <functional>
#include <memory>

namespace nexrt {
class FileReadLease;
class FileReadGrant;
class FileWriteLease;
class FileWriteGrant;
class FileOpenLease;
#ifndef _WIN32
// Opt-in trusted-host observation. No descriptor, path, payload, source Value
// or authority crosses this boundary. Calls occur outside resource/cursor locks.
enum class FileIOOperation {OpenRead,OpenWrite,OpenAppend,Read,Write,Seek,Size,Flush};
enum class FileIOPhase {Before,After};
struct FileIOEvent {
  FileIOOperation operation;
  FileIOPhase phase;
  int64_t argument=0,result=0;
  int error=0;
};
using FileIOObserver=std::function<void(const FileIOEvent &)>;
#endif
// Host-owned capability. No descriptor or mutable resource becomes a NEX value.
class TextFiles {
  struct Impl;
  std::shared_ptr<Impl> impl;
  friend class FileScope;
  friend class FileReadLease;
  friend class FileReadGrant;
  friend FileReadLease captureFileReadLease(const std::string &,bool);
  friend FileReadGrant captureFileReadGrant(bool);
  friend class FileOpenLease;
  explicit TextFiles(std::shared_ptr<Impl> impl):impl(std::move(impl)){}
  std::unique_ptr<TextFiles> retain() const;
  FileReadLease readLeaseIn(const ResourceAccess &,const std::string &) const;
  FileResource openInAccess(const ResourceAccess &,const std::string &,FileMode,const std::function<void()> &,ResourceRegionAuthority region={},const std::shared_ptr<ResourceExecutor> &cleanup={})const;
public:
  static constexpr size_t byteLimit = 1024 * 1024;
  static constexpr size_t textLimit = byteLimit;
  static constexpr size_t pathLimit = 4096;
  using Poll = std::function<void()>;
  TextFiles(const std::string &root, bool writable);
#ifndef _WIN32
  TextFiles(const std::string &root,bool writable,FileIOObserver observer);
#endif
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
  friend class FileWriteLease;
  explicit FileReadLease(std::shared_ptr<State> state):state(std::move(state)){}
public:
  FileReadLease()=default;
  uint64_t identity()const noexcept;
  size_t retainedPathBytes()const noexcept;
  void check()const;
  std::vector<uint8_t> read(const TextFiles::Poll &poll={})const;
};
FileReadLease captureFileReadLease(const std::string &relative,bool environmentAllowed=true);
// Capture authority once on the host coordinator, after its root RequestScope
// exists. Copies retain physical root state and revocable access, never a domain
// owner. Per-path preparation can then run on a scheduler without consulting its
// temporary RequestScope, FileScope TLS or process environment. An unavailable
// grant reports CAPABILITY only when check()/lease() attempts to use it.
class FileReadGrant {
  struct State;
  std::shared_ptr<const State> state;
  friend FileReadGrant captureFileReadGrant(bool);
  friend class FileWriteGrant;
  explicit FileReadGrant(std::shared_ptr<const State> state):state(std::move(state)){}
public:
  FileReadGrant()=default;
  void check()const;
  FileReadLease lease(const std::string &relative)const;
  FileOpenLease openRead(const std::string &relative)const;
};
FileReadGrant captureFileReadGrant(bool environmentAllowed=true);
// A write grant preserves the same root/request revocation lineage as reads.
// A read grant alone never exposes a write operation. Neither grant is a source
// value or authority inferred from an IO worker's environment/TLS.
class FileWriteLease {
  FileReadLease physical;
  friend class FileWriteGrant;
  explicit FileWriteLease(FileReadLease physical):physical(std::move(physical)){}
public:
  FileWriteLease()=default;
  uint64_t identity()const noexcept{return physical.identity();}
  size_t retainedPathBytes()const noexcept{return physical.retainedPathBytes();}
  void check()const{physical.check();}
  void write(std::span<const uint8_t>,const TextFiles::Poll &poll={})const;
};
class FileWriteGrant {
  FileReadGrant physical;
  friend FileWriteGrant captureFileWriteGrant(bool);
  explicit FileWriteGrant(FileReadGrant physical):physical(std::move(physical)){}
public:
  FileWriteGrant()=default;
  void check()const;
  FileWriteLease lease(const std::string &relative)const;
  FileOpenLease openWrite(const std::string &relative,FileMode mode=FileMode::WriteTruncate)const;
};
FileWriteGrant captureFileWriteGrant(bool environmentAllowed=true);
// No file is opened while preparing this exact owned path. The captured
// root/request authority is checked on the IO worker and again at admission.
class FileOpenLease {
  struct State;
  std::shared_ptr<const State> state;
  friend class FileReadGrant;
  friend class FileWriteGrant;
  explicit FileOpenLease(std::shared_ptr<const State> state):state(std::move(state)){}
public:
  FileOpenLease()=default;
  void check()const;
  size_t retainedPathBytes()const noexcept;
  FileResource open(const TextFiles::Poll &poll={})const;
  FileResource openInRegion(const ResourceRegionAuthority &,const TextFiles::Poll &poll={},const std::shared_ptr<ResourceExecutor> &cleanup={})const;
};
#endif
// An explicit host scope overrides the process environment. Native HTTP calls
// do not inherit an environment capability unless the trusted host grants one.
// Host-only lexical authority inspection; this neither grants nor captures it.
bool inFileScope() noexcept;
class FileScope {
  struct Impl;
  std::unique_ptr<Impl> impl;
public:
  explicit FileScope(bool environmentAllowed = true);
  explicit FileScope(TextFiles &capability);
#ifndef _WIN32
  // The host retains the ancestor domain and can revoke it independently of
  // this coordinator's lexical TLS. It must belong to this exact capability.
  FileScope(TextFiles &capability,const ResourceDomain &resources);
#endif
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
