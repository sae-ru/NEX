#ifdef _WIN32
#include "nex_files_windows.h"
#else
#include "nex_files.h"
#include "nex_external_resource.h"
#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <mutex>
#include <optional>
#include <string_view>
#include <fcntl.h>
#include <sys/random.h>
#include <sys/stat.h>
#include <unistd.h>

namespace nexrt {
namespace {
class Descriptor {
  int value = -1;
public:
  explicit Descriptor(int value = -1):value(value){}
  ~Descriptor(){ if(value >= 0) ::close(value); }
  Descriptor(const Descriptor&) = delete;
  Descriptor &operator=(const Descriptor&) = delete;
  Descriptor(Descriptor &&other) noexcept:value(other.value){other.value=-1;}
  Descriptor &operator=(Descriptor &&other) noexcept {
    if(this != &other){if(value >= 0)::close(value);value=other.value;other.value=-1;}
    return *this;
  }
  int get() const {return value;}
};
[[noreturn]] void ioError(int code) {
  if(code == ENOENT)throw DataError("NOT_FOUND","file or parent directory does not exist");
  if(code == EACCES || code == EPERM)throw DataError("PERMISSION","file operation is not permitted");
  if(code == ELOOP || code == ENOTDIR || code == EISDIR)throw DataError("VALIDATION","file path is not a regular file or contains a symbolic link");
  if(code == EFBIG || code == EOVERFLOW)throw DataError("LIMIT","file exceeds supported limits");
  throw DataError("E_FILE","filesystem operation failed");
}
void check(const TextFiles::Poll &poll){if(poll)poll();}
std::vector<std::string> components(const std::string &relative){
  if(relative.empty() || relative.size() > TextFiles::pathLimit || relative.front() == '/' || relative.find('\0') != std::string::npos)
    throw DataError("VALIDATION","file path must be a bounded nonempty relative path");
  unicodeOffsets(relative,false);
  std::vector<std::string> result;
  for(size_t offset=0;offset<relative.size();){
    auto end=relative.find('/',offset);if(end==std::string::npos)end=relative.size();
    auto part=relative.substr(offset,end-offset);
    if(part.empty() || part=="." || part==".." || result.size()==128)
      throw DataError("VALIDATION","file path contains an invalid component");
    result.push_back(std::move(part));
    if(end==relative.size())break;
    offset=end+1;if(offset==relative.size())throw DataError("VALIDATION","file path has a trailing separator");
  }
  return result;
}
Descriptor parent(int root,const std::vector<std::string> &parts,const TextFiles::Poll &poll){
  Descriptor directory(::fcntl(root,F_DUPFD_CLOEXEC,0));if(directory.get()<0)ioError(errno);
  for(size_t index=0;index+1<parts.size();++index){
    check(poll);
    Descriptor next(::openat(directory.get(),parts[index].c_str(),O_RDONLY|O_DIRECTORY|O_CLOEXEC|O_NOFOLLOW));
    if(next.get()<0)ioError(errno);
    directory=std::move(next);
  }
  return directory;
}
struct Temporary {
  int parent;
  std::string name;
  Descriptor descriptor;
  bool published=false;
  explicit Temporary(int parent):parent(parent){
    static constexpr char hex[]="0123456789abcdef";
    for(unsigned attempt=0;attempt<16;++attempt){
      std::array<unsigned char,16> entropy{};
      if(::getentropy(entropy.data(),entropy.size()))ioError(errno);
      name=".nex-write-";
      for(auto byte:entropy){name+=hex[byte>>4];name+=hex[byte&15];}
      descriptor=Descriptor(::openat(parent,name.c_str(),O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC|O_NOFOLLOW,0600));
      if(descriptor.get()>=0)return;
      if(errno!=EEXIST)ioError(errno);
    }
    throw DataError("E_FILE","cannot reserve a temporary file");
  }
  ~Temporary(){if(!published && descriptor.get()>=0)::unlinkat(parent,name.c_str(),0);}
};
}
struct TextFiles::Impl {
  Descriptor root;
  bool writable;
  ResourceDomain resources;
  const std::shared_ptr<const FileIOObserver> observer;
  Impl(const std::string &path,bool writable,FileIOObserver observer={})
      :writable(writable),observer(observer?std::make_shared<const FileIOObserver>(std::move(observer)):nullptr){
    if(path.empty() || path.find('\0')!=std::string::npos)throw DataError("CAPABILITY","file root is not configured");
    // The host selects the root. User-supplied paths below it never follow links.
    root=Descriptor(::open(path.c_str(),O_RDONLY|O_DIRECTORY|O_CLOEXEC));
    if(root.get()<0)throw DataError("CAPABILITY","configured file root is unavailable");
  }
  template<class Content> Content read(const std::string &relative,const Poll &poll,size_t reservedBytes=0) const;
  template<class Validate> void write(const std::string &relative,std::span<const uint8_t> content,const Poll &poll,Validate validate) const;
};
TextFiles::TextFiles(const std::string &root,bool writable):impl(std::make_shared<Impl>(root,writable)){}
TextFiles::TextFiles(const std::string &root,bool writable,FileIOObserver observer):impl(std::make_shared<Impl>(root,writable,std::move(observer))){}
TextFiles::~TextFiles()=default;
std::unique_ptr<TextFiles> TextFiles::retain() const {return std::unique_ptr<TextFiles>(new TextFiles(impl));}
template<class Content> Content TextFiles::Impl::read(const std::string &relative,const Poll &poll,size_t reservedBytes) const {
  check(poll);auto parts=components(relative);auto directory=parent(root.get(),parts,poll);
  Descriptor file(::openat(directory.get(),parts.back().c_str(),O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK));
  if(file.get()<0)ioError(errno);
  struct stat info{};if(::fstat(file.get(),&info))ioError(errno);
  if(!S_ISREG(info.st_mode))throw DataError("VALIDATION","only regular files are supported");
  if(info.st_size<0 || uint64_t(info.st_size)>byteLimit)throw DataError("LIMIT","file exceeds byte limit");
  Content content;content.reserve(reservedBytes?reservedBytes:size_t(info.st_size));
  if(reservedBytes&&content.capacity()>reservedBytes)throw DataError("LIMIT","file read storage exceeds its reservation");
  std::array<char,65536> buffer{};
  for(;;){
    check(poll);auto count=::read(file.get(),buffer.data(),buffer.size());
    if(count<0){if(errno==EINTR)continue;ioError(errno);}
    if(!count)break;
    if(size_t(count)>byteLimit-content.size())throw DataError("LIMIT","file exceeds byte limit");
    content.insert(content.end(),buffer.data(),buffer.data()+size_t(count));
  }
  return content;
}
struct FileReadLease::State {
  struct Pin {
    std::shared_ptr<TextFiles::Impl> files;
    // An exact owned array avoids std::string's rounded backing capacity at
    // the4096-byte boundary. Allocator overhead is not declared path payload.
    std::unique_ptr<char[]> relative;
    size_t length;
    Pin(std::shared_ptr<TextFiles::Impl> files,const std::string &path)
      :files(std::move(files)),relative(std::make_unique<char[]>(path.size())),length(path.size()){
      std::copy(path.begin(),path.end(),relative.get());
    }
  };
  ResourceLease<Pin> physical;
  uint64_t id;size_t pathBytes;
  State(ResourceLease<Pin> physical,uint64_t id,size_t pathBytes):physical(std::move(physical)),id(id),pathBytes(pathBytes){}
};
FileReadLease TextFiles::readLeaseIn(const ResourceAccess &grant,const std::string &relative)const {
  // Validate before admission; no per-operation open/read occurs here.
  (void)components(relative);
  auto retained=impl;
  auto owner=grant.make<FileReadLease::State::Pin>([&](const ResourcePermit &permit){
    permit.check();return std::make_unique<FileReadLease::State::Pin>(retained,relative);
  });
  return FileReadLease(std::make_shared<FileReadLease::State>(owner.acquire(),owner.identity(),relative.size()));
}
uint64_t FileReadLease::identity()const noexcept{return state?state->id:0;}
size_t FileReadLease::retainedPathBytes()const noexcept{return state?state->pathBytes:0;}
void FileReadLease::check()const {
  auto retained=state;
  if(!retained)throw DataError("E_RESOURCE_CLOSED","file read lease is unavailable");
  retained->physical.check();
}
std::vector<uint8_t> FileReadLease::read(const TextFiles::Poll &poll)const {
  auto retained=state;
  if(!retained)throw DataError("E_RESOURCE_CLOSED","file read lease is unavailable");
  auto physical=retained->physical;
  const auto &pin=physical.value();auto callback=poll;
  auto checkpoint=[physical,callback](){physical.check();if(callback)callback();physical.check();};
  auto result=pin.files->read<std::vector<uint8_t>>(std::string(pin.relative.get(),pin.length),checkpoint,TextFiles::byteLimit);
  // The coordinator must also check before admitting a completion. A domain
  // can be revoked after this worker's last poll or after physical retirement.
  checkpoint();return result;
}
struct FileReadGrant::State {
  std::shared_ptr<TextFiles::Impl> files;
  ResourceAccess resources;
  std::string error;
  State(std::shared_ptr<TextFiles::Impl> files,ResourceAccess resources)
    :files(std::move(files)),resources(std::move(resources)){}
  explicit State(std::string error):error(std::move(error)){}
};
struct FileOpenLease::State {
  std::shared_ptr<TextFiles::Impl> files;
  ResourceAccess resources;
  const size_t length;
  const std::unique_ptr<char[]> relative;
  const FileMode mode;
  State(std::shared_ptr<TextFiles::Impl> files,ResourceAccess resources,const std::string &path,FileMode mode)
    :files(std::move(files)),resources(std::move(resources)),length(path.size()),relative(std::make_unique<char[]>(length)),mode(mode){
    std::copy(path.begin(),path.end(),relative.get());
  }
};
void FileReadGrant::check()const {
  auto retained=state;
  if(!retained||!retained->files)
    throw DataError("CAPABILITY",retained&&!retained->error.empty()?retained->error:"file read capability is not configured");
  retained->resources.check();
}
FileReadLease FileReadGrant::lease(const std::string &relative)const {
  check();
  return TextFiles(state->files).readLeaseIn(state->resources,relative);
}
void FileWriteGrant::check()const {
  physical.check();
  if(!physical.state->files->writable)
    throw DataError("CAPABILITY","file capability does not permit writes");
}
FileWriteLease FileWriteGrant::lease(const std::string &relative)const {
  check();return FileWriteLease(physical.lease(relative));
}
FileOpenLease FileReadGrant::openRead(const std::string &relative)const {
  check();(void)components(relative);
  return FileOpenLease(std::make_shared<FileOpenLease::State>(state->files,state->resources,relative,FileMode::Read));
}
FileOpenLease FileWriteGrant::openWrite(const std::string &relative,FileMode mode)const {
  check();
  if(mode!=FileMode::WriteTruncate&&mode!=FileMode::Append)throw DataError("VALIDATION","write open requires truncate or append mode");
  (void)components(relative);
  return FileOpenLease(std::make_shared<FileOpenLease::State>(physical.state->files,physical.state->resources,relative,mode));
}
void FileOpenLease::check()const {
  if(!state||!state->files)throw DataError("CAPABILITY","file open capability is not configured");
  state->resources.check();
  if(state->mode!=FileMode::Read&&!state->files->writable)throw DataError("CAPABILITY","file capability does not permit writes");
}
size_t FileOpenLease::retainedPathBytes()const noexcept{return state?state->length:0;}
FileResource FileOpenLease::open(const TextFiles::Poll &poll)const {return openInRegion({},poll);}
FileResource FileOpenLease::openInRegion(const ResourceRegionAuthority &region,const TextFiles::Poll &poll,const std::shared_ptr<ResourceExecutor> &cleanup)const {
  check();auto retained=state;auto executor=cleanup;
  auto checkpoint=[retained,poll]{retained->resources.check();if(poll)poll();retained->resources.check();};
  auto result=TextFiles(retained->files).openInAccess(retained->resources,std::string(retained->relative.get(),retained->length),retained->mode,checkpoint,region,executor);
  retained->resources.check();return result;
}
template<class Validate> void TextFiles::Impl::write(const std::string &relative,std::span<const uint8_t> content,const Poll &poll,Validate validate) const {
  if(!writable)throw DataError("CAPABILITY","file capability does not permit writes");
  check(poll);auto parts=components(relative);
  if(content.size()>byteLimit)throw DataError("LIMIT","file value exceeds byte limit");
  validate();
  auto directory=parent(root.get(),parts,poll);struct stat existing{};
  if(!::fstatat(directory.get(),parts.back().c_str(),&existing,AT_SYMLINK_NOFOLLOW)){
    if(!S_ISREG(existing.st_mode))throw DataError("VALIDATION","write destination must be a regular file");
  }else if(errno!=ENOENT)ioError(errno);
  Temporary temporary(directory.get());
  for(size_t offset=0;offset<content.size();){
    check(poll);auto size=std::min<size_t>(65536,content.size()-offset);
    auto count=::write(temporary.descriptor.get(),content.data()+offset,size);
    if(count<0){if(errno==EINTR)continue;ioError(errno);}
    if(count==0)throw DataError("E_FILE","file write made no progress");
    offset+=size_t(count);
  }
  check(poll);
  while(::fsync(temporary.descriptor.get())){if(errno!=EINTR)ioError(errno);check(poll);}
  check(poll);
  if(::renameat(directory.get(),temporary.name.c_str(),directory.get(),parts.back().c_str()))ioError(errno);
  temporary.published=true;
}
void FileWriteLease::write(std::span<const uint8_t> content,const TextFiles::Poll &poll)const {
  auto retained=physical.state;
  if(!retained)throw DataError("E_RESOURCE_CLOSED","file write lease is unavailable");
  auto lease=retained->physical;
  const auto &pin=lease.value();auto callback=poll;
  auto checkpoint=[lease,callback](){lease.check();if(callback)callback();lease.check();};
  // The existing fsync+rename implementation is the commit boundary. There is
  // deliberately no post-commit poll promising rollback after publication.
  pin.files->write(std::string(pin.relative.get(),pin.length),content,checkpoint,[]{});
}
Value TextFiles::read(const std::string &relative,const Poll &poll) const {
  auto retained=impl;auto path=relative;auto callback=poll;
  try{return success(Value(string(retained->read<std::string>(path,callback))));}
  catch(const DataError &error){return failure(error.code,error.what());}
}
Value TextFiles::write(const std::string &relative,const std::string &text,const Poll &poll) const {
  auto retained=impl;auto path=relative;auto content=text;auto callback=poll;
  try{
    retained->write(path,{reinterpret_cast<const uint8_t*>(content.data()),content.size()},callback,[&]{unicodeOffsets(content,false);});
    return success(Value(1,true));
  }catch(const DataError &error){return failure(error.code,error.what());}
}
Value TextFiles::readBytes(const std::string &relative,const Poll &poll) const {
  auto retained=impl;auto path=relative;auto callback=poll;
  try{return success(Value(bytes(ByteBuffer::owned(retained->read<std::vector<uint8_t>>(path,callback)))));}
  catch(const DataError &error){return failure(error.code,error.what());}
}
Value TextFiles::writeBytes(const std::string &relative,const ByteBuffer &bytes,const Poll &poll) const {
  // Poll may release the caller's last value. Retain immutable storage until
  // every borrowed write view has finished, including exceptional exits.
  auto content=bytes;auto retained=impl;auto path=relative;auto callback=poll;
  try{retained->write(path,content.view(),callback,[]{});return success(Value(1,true));}
  catch(const DataError &error){return failure(error.code,error.what());}
}

struct FileResource::State {
  Descriptor descriptor;
  const FileMode mode;
  mutable std::mutex mutex;
  const std::shared_ptr<const FileIOObserver> observer;
  State(Descriptor descriptor,FileMode mode,std::shared_ptr<const FileIOObserver> observer)
      :descriptor(std::move(descriptor)),mode(mode),observer(std::move(observer)){}
};
namespace {
void observeFile(const std::shared_ptr<const FileIOObserver> &observer,FileIOOperation operation,
    FileIOPhase phase,int64_t argument,int64_t result=0,int error=0){
  if(!observer)return;
  try{(*observer)(FileIOEvent{operation,phase,argument,result,error});}
  catch(const DataError &){throw;}
  catch(const std::bad_alloc &){throw;}
  catch(...){throw DataError("E_TASK_HOST","file IO observer failed");}
}
template<class Lease,class Operation>
auto streamCall(const Lease &lease,const TextFiles::Poll &poll,FileIOOperation kind,int64_t argument,Operation operation) {
  const auto &state=lease.value();
  for(;;){
    check(poll);lease.check();
    observeFile(state.observer,kind,FileIOPhase::Before,argument);
    // An observer may wait while the host cancels/revokes. Recheck before the
    // actual syscall; observation never renews or manufactures authority.
    if(state.observer){check(poll);lease.check();}
    decltype(operation(state)) result;int error;
    {
      std::lock_guard guard(state.mutex);lease.check();
      result=operation(state);error=errno;
    }
    observeFile(state.observer,kind,FileIOPhase::After,argument,int64_t(result),result<0?error:0);
    if(result<0){if(error==EINTR)continue;ioError(error);}
    check(poll);lease.check();return result;
  }
}
}
FileStreamLease FileResource::lease()const{return leaseInRegion({});}
FileStreamLease FileResource::leaseInRegion(const ResourceRegionAuthority &actor)const{
  if(region)region.check(actor);else if(actor)actor.check();
  return FileStreamLease(owner.acquire(),owner.identity(),region,actor);
}
void FileResource::transferRegions(std::span<const FileResource> files,const ResourceRegionAuthority &actor,const ResourceRegionAuthority &target,bool commit){
  ExternalResource::transferRegions({},actor,target,commit,files);
}
void FileStreamLease::checkRead(int64_t maximum)const {
  check();if(physical.value().mode!=FileMode::Read)throw DataError("CAPABILITY","file handle does not permit reads");
  if(maximum<0)throw DataError("E_RANGE","read size must be nonnegative");
  if(uint64_t(maximum)>TextFiles::byteLimit)throw DataError("LIMIT","read size exceeds byte limit");
}
void FileStreamLease::checkWrite(size_t bytes)const {
  check();if(physical.value().mode==FileMode::Read)throw DataError("CAPABILITY","file handle does not permit writes");
  if(bytes>TextFiles::byteLimit)throw DataError("LIMIT","write size exceeds byte limit");
}
void FileStreamLease::checkSeek(int64_t offset)const {
  check();
  if(offset<0 || uint64_t(offset)>uint64_t(std::numeric_limits<off_t>::max()))
    throw DataError("E_RANGE","file offset is outside supported range");
}
std::vector<uint8_t> FileStreamLease::read(int64_t maximum,const Poll &poll)const {
  auto retained=*this;auto lease=retained.physical;auto callback=[retained,copy=poll]{retained.check();if(copy)copy();retained.check();};checkRead(maximum);
  std::vector<uint8_t> content(static_cast<size_t>(maximum));
  auto count=streamCall(lease,callback,FileIOOperation::Read,maximum,[&](const auto &state){return ::read(state.descriptor.get(),content.data(),content.size());});
  content.resize(size_t(count));return content;
}
int64_t FileStreamLease::write(std::span<const uint8_t> content,const Poll &poll)const {
  auto retained=*this;auto lease=retained.physical;auto callback=[retained,copy=poll]{retained.check();if(copy)copy();retained.check();};
  checkWrite(content.size());
  return streamCall(lease,callback,FileIOOperation::Write,int64_t(content.size()),[&](const auto &state){return ::write(state.descriptor.get(),content.data(),content.size());});
}
int64_t FileStreamLease::seek(int64_t offset,const Poll &poll)const {
  auto retained=*this;auto lease=retained.physical;auto callback=[retained,copy=poll]{retained.check();if(copy)copy();retained.check();};
  checkSeek(offset);
  return streamCall(lease,callback,FileIOOperation::Seek,offset,[&](const auto &state){return ::lseek(state.descriptor.get(),off_t(offset),SEEK_SET);});
}
int64_t FileStreamLease::size(const Poll &poll)const {
  auto retained=*this;auto lease=retained.physical;auto callback=[retained,copy=poll]{retained.check();if(copy)copy();retained.check();};
  return streamCall(lease,callback,FileIOOperation::Size,0,[](const auto &state)->int64_t{
    struct stat info{};if(::fstat(state.descriptor.get(),&info))return -1;
    if(info.st_size<0 || uint64_t(info.st_size)>uint64_t(std::numeric_limits<int64_t>::max()))
      throw DataError("LIMIT","file size exceeds supported range");
    return int64_t(info.st_size);
  });
}
void FileStreamLease::flush(const Poll &poll)const {
  auto retained=*this;auto lease=retained.physical;auto callback=[retained,copy=poll]{retained.check();if(copy)copy();retained.check();};
  retained.check();if(lease.value().mode==FileMode::Read)throw DataError("CAPABILITY","file handle does not permit writes");
  streamCall(lease,callback,FileIOOperation::Flush,0,[](const auto &state){return ::fsync(state.descriptor.get());});
}
ByteBuffer FileResource::read(int64_t maximum,const Poll &poll)const {return ByteBuffer::owned(lease().read(maximum,poll));}
int64_t FileResource::write(const ByteBuffer &bytes,const Poll &poll)const {
  auto content=bytes;return lease().write(content.view(),poll);
}
int64_t FileResource::seek(int64_t offset,const Poll &poll)const{return lease().seek(offset,poll);}
int64_t FileResource::size(const Poll &poll)const{return lease().size(poll);}
void FileResource::flush(const Poll &poll)const{lease().flush(poll);}
ResourceDomain TextFiles::resourceScope(size_t limit) const {return impl->resources.child(limit);}
FileResource TextFiles::open(const std::string &relative,FileMode mode,const Poll &poll) const {
  auto retained=impl;
  return openIn(retained->resources,relative,mode,poll);
}
FileResource TextFiles::openIn(const ResourceDomain &scope,const std::string &relative,FileMode mode,const Poll &poll) const {
  if(!scope.descendsFrom(impl->resources))throw DataError("CAPABILITY","file resource scope belongs to another capability");
  return openInAccess(scope.access(),relative,mode,poll);
}
FileResource TextFiles::openInAccess(const ResourceAccess &scope,const std::string &relative,FileMode mode,const Poll &poll,ResourceRegionAuthority region,const std::shared_ptr<ResourceExecutor> &cleanup)const {
  auto retained=impl;auto path=relative;auto callback=poll;auto executor=cleanup;
  if(mode!=FileMode::Read&&mode!=FileMode::WriteTruncate&&mode!=FileMode::Append)
    throw DataError("VALIDATION","invalid file mode");
  if(mode!=FileMode::Read&&!retained->writable)throw DataError("CAPABILITY","file capability does not permit writes");
  ResourceRegionOwner logical;ResourceSettlement settlement;
  std::optional<resource_detail::SettlementGuard> creation;
  if(region){logical=region.reserve();settlement=ResourceSettlement::pending();creation.emplace(settlement);logical.attach(settlement);}
  auto create=[retained,path=std::move(path),callback=std::move(callback),mode,logical](const ResourcePermit &permit){
    auto poll=[&]{if(logical)logical.checkCreation();permit.check();check(callback);permit.check();if(logical)logical.checkCreation();};
    poll();auto parts=components(path);auto directory=parent(retained->root.get(),parts,poll);poll();
    struct stat existing{};
    if(!::fstatat(directory.get(),parts.back().c_str(),&existing,AT_SYMLINK_NOFOLLOW)){
      if(!S_ISREG(existing.st_mode))throw DataError("VALIDATION","only regular files are supported");
    }else if(errno!=ENOENT)ioError(errno);
    int flags=O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK;
    flags|=mode==FileMode::Read?O_RDONLY:O_WRONLY|O_CREAT;
    if(mode==FileMode::Append)flags|=O_APPEND;
    auto operation=mode==FileMode::Read?FileIOOperation::OpenRead:mode==FileMode::WriteTruncate?FileIOOperation::OpenWrite:FileIOOperation::OpenAppend;
    observeFile(retained->observer,operation,FileIOPhase::Before,0);if(retained->observer)poll();
    Descriptor file(::openat(directory.get(),parts.back().c_str(),flags,0600));
    if(file.get()<0)ioError(errno);
    struct stat info{};if(::fstat(file.get(),&info))ioError(errno);
    if(!S_ISREG(info.st_mode))throw DataError("VALIDATION","only regular files are supported");
    poll();
    if(mode==FileMode::WriteTruncate){
      while(::ftruncate(file.get(),0)){if(errno!=EINTR)ioError(errno);poll();}
    }
    auto result=std::make_unique<FileResource::State>(std::move(file),mode,retained->observer);
    // The descriptor and quota are still held here; no source File has been
    // published. OpenWrite includes its real truncation before this event.
    observeFile(retained->observer,operation,FileIOPhase::After,0);
    if(retained->observer)poll();return result;
  };
  // Source stream opens already run on an admitted IO worker. Reserve their
  // finalizer before construction, and retire the full payload/quota/fence on
  // the owning executor even when the final alias is released by a coordinator.
  auto physical=executor?scope.makeOnExecutor<FileResource::State>(executor,std::move(create),settlement,true):
    scope.make<FileResource::State>(std::move(create),settlement);
  if(logical)logical.publish(physical.revocation());
  return FileResource(std::move(physical),std::move(logical));
}

namespace {
struct Access {
  std::string root, errorCode, errorMessage;
  bool writable=false, attempted=false;
  std::unique_ptr<TextFiles> owned;
  std::unique_ptr<ResourceDomain> resources;
  explicit Access(bool environmentAllowed){
    if(environmentAllowed){
      if(auto *value=std::getenv("NEX_FILES_ROOT"))root=value;
      if(auto *value=std::getenv("NEX_FILES_WRITE"))writable=std::string_view(value)=="1";
    }
  }
  explicit Access(std::unique_ptr<TextFiles> capability):attempted(true),owned(std::move(capability)){}
  Access(std::unique_ptr<TextFiles> capability,const ResourceDomain &scope)
      :attempted(true),owned(std::move(capability)),resources(std::make_unique<ResourceDomain>(scope.child())){}
  TextFiles &capability(){
    if(!attempted){
      attempted=true;
      try{
        if(root.empty()||root.front()!='/')throw DataError("CAPABILITY","file root must be an absolute configured directory");
        owned=std::make_unique<TextFiles>(root,writable);
      }
      catch(const DataError &error){errorCode=error.code;errorMessage=error.what();}
    }
    if(!owned)throw DataError(errorCode.empty()?"CAPABILITY":errorCode,errorMessage.empty()?"file capability is not configured":errorMessage);
    return *owned;
  }
  FileResource open(const std::string &path,FileMode mode,const TextFiles::Poll &poll){
    auto &files=capability();
    if(!resources)resources=std::make_unique<ResourceDomain>(files.resourceScope());
    if(auto bind=resource_detail::requestBinder)if(auto *request=bind(*resources))
      return files.openIn(*request,path,mode,poll);
    return files.openIn(*resources,path,mode,poll);
  }
};
thread_local Access *currentFiles=nullptr;
thread_local std::unique_ptr<Access> environmentFiles;
Access &access(bool environmentAllowed){
  if(currentFiles)return *currentFiles;
  if(!environmentAllowed)throw DataError("CAPABILITY","request file capability is not configured");
  if(!environmentFiles)environmentFiles=std::make_unique<Access>(true);
  return *environmentFiles;
}
}
bool inFileScope() noexcept{return currentFiles!=nullptr;}
struct FileScope::Impl {
  Access value;
  Access *previous;
  explicit Impl(bool allowed):value(allowed),previous(currentFiles){currentFiles=&value;}
  explicit Impl(std::unique_ptr<TextFiles> capability):value(std::move(capability)),previous(currentFiles){currentFiles=&value;}
  Impl(std::unique_ptr<TextFiles> capability,const ResourceDomain &scope):value(std::move(capability),scope),previous(currentFiles){currentFiles=&value;}
  ~Impl(){currentFiles=previous;}
};
FileScope::FileScope(bool allowed):impl(std::make_unique<Impl>(allowed)){}
FileScope::FileScope(TextFiles &capability):impl(std::make_unique<Impl>(capability.retain())){}
FileScope::FileScope(TextFiles &capability,const ResourceDomain &resources){
  if(!resources.descendsFrom(capability.impl->resources))throw DataError("CAPABILITY","file resource scope belongs to another capability");
  impl=std::make_unique<Impl>(capability.retain(),resources);
}
FileScope::~FileScope()=default;
FileReadLease captureFileReadLease(const std::string &relative,bool environmentAllowed){
  auto &current=access(environmentAllowed);auto &files=current.capability();
  if(!current.resources)current.resources=std::make_unique<ResourceDomain>(files.resourceScope());
  if(auto bind=resource_detail::requestBinder)if(auto *request=bind(*current.resources))
    return files.readLeaseIn(request->access(),relative);
  return files.readLeaseIn(current.resources->access(),relative);
}
FileReadGrant captureFileReadGrant(bool environmentAllowed){
  try{
    auto &current=access(environmentAllowed);auto &files=current.capability();
    if(!current.resources)current.resources=std::make_unique<ResourceDomain>(files.resourceScope());
    auto resources=current.resources->access();
    if(auto bind=resource_detail::requestBinder)if(auto *request=bind(*current.resources))
      resources=request->access();
    resources.check();
    return FileReadGrant(std::make_shared<FileReadGrant::State>(files.impl,std::move(resources)));
  }catch(const DataError &error){
    // A declaration or skipped conditional read must not require authority.
    // Control/resource failures are never converted into a missing grant.
    if(error.code!="CAPABILITY")throw;
    return FileReadGrant(std::make_shared<FileReadGrant::State>(error.what()));
  }
}
FileWriteGrant captureFileWriteGrant(bool environmentAllowed){
  // Capture may be unused; absent/read-only authority fails on attempted use.
  return FileWriteGrant(captureFileReadGrant(environmentAllowed));
}
Value fileReadText(const std::string &relative,bool environmentAllowed,const TextFiles::Poll &poll){
  try{return access(environmentAllowed).capability().read(relative,poll);}
  catch(const DataError &error){return failure(error.code,error.what());}
}
Value fileWriteText(const std::string &relative,const std::string &text,bool environmentAllowed,const TextFiles::Poll &poll){
  try{return access(environmentAllowed).capability().write(relative,text,poll);}
  catch(const DataError &error){return failure(error.code,error.what());}
}
Value fileReadBytes(const std::string &relative,bool environmentAllowed,const TextFiles::Poll &poll){
  try{return access(environmentAllowed).capability().readBytes(relative,poll);}
  catch(const DataError &error){return failure(error.code,error.what());}
}
Value fileWriteBytes(const std::string &relative,const ByteBuffer &bytes,bool environmentAllowed,const TextFiles::Poll &poll){
  try{return access(environmentAllowed).capability().writeBytes(relative,bytes,poll);}
  catch(const DataError &error){return failure(error.code,error.what());}
}
void resetFileEnvironment() noexcept {environmentFiles.reset();}
FileResource fileOpen(const std::string &relative,FileMode mode,bool environmentAllowed,const TextFiles::Poll &poll){
  return access(environmentAllowed).open(relative,mode,poll);
}
}

#endif
