#pragma once
#include "nex_bytes.h"
#include "nex_resource.h"
#include <functional>

namespace nexrt {
enum class FileMode {Read,WriteTruncate,Append};
class FileStreamLease;
// Trusted runtime payload. Source syntax and the C FFI are separate contracts.
class FileResource {
  struct State;
  ResourceOwner<State> owner;
  ResourceRegionOwner region;
  friend class ExternalResource;
  friend class TextFiles;
  friend class FileStreamLease;
  explicit FileResource(ResourceOwner<State> owner,ResourceRegionOwner region={}):owner(std::move(owner)),region(std::move(region)){}
public:
  using Poll=std::function<void()>;
  FileResource()=default;
  uint64_t identity() const noexcept {return owner.identity();}
  bool isOpen() const noexcept {return owner.isOpen()&&(!region||region.active());}
  bool close() const noexcept {return owner.close();}
  // Capture on the authorized coordinator. A host worker retains physical
  // storage and revocation checks, never a source Value or FileScope TLS.
  FileStreamLease lease() const;
  FileStreamLease leaseInRegion(const ResourceRegionAuthority &)const;
  void checkRegion(const ResourceRegionAuthority &actor)const{region.check(actor);}
  static void transferRegions(std::span<const FileResource>,const ResourceRegionAuthority &,const ResourceRegionAuthority &,bool commit=true);
  ByteBuffer read(int64_t maximum,const Poll &poll={}) const;
  int64_t write(const ByteBuffer &bytes,const Poll &poll={}) const;
  int64_t seek(int64_t offset,const Poll &poll={}) const;
  int64_t size(const Poll &poll={}) const;
  void flush(const Poll &poll={}) const;
};
// Private host lease for an already-opened regular file. Copies share the
// original cursor/mode/close state and retain its physical quota until retired.
class FileStreamLease {
  ResourceLease<FileResource::State> physical;
  uint64_t id=0;
  ResourceRegionOwner region;
  ResourceRegionAuthority actor;
  friend class FileResource;
  friend class PreparedTaskFileStream;
  FileStreamLease(ResourceLease<FileResource::State> physical,uint64_t id,ResourceRegionOwner region={},ResourceRegionAuthority actor={})
    :physical(std::move(physical)),id(id),region(std::move(region)),actor(std::move(actor)){}
  void checkRead(int64_t maximum)const;
  void checkWrite(size_t bytes)const;
  void checkSeek(int64_t offset)const;
public:
  using Poll=FileResource::Poll;
  FileStreamLease()=default;
  uint64_t identity()const noexcept{return id;}
  void check()const{if(region)region.check(actor);else if(actor)actor.check();physical.check();}
  std::vector<uint8_t> read(int64_t maximum,const Poll &poll={})const;
  int64_t write(std::span<const uint8_t>,const Poll &poll={})const;
  int64_t seek(int64_t offset,const Poll &poll={})const;
  int64_t size(const Poll &poll={})const;
  void flush(const Poll &poll={})const;
};
}
