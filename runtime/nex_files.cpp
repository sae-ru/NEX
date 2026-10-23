#ifdef _WIN32
#include "nex_files_windows.h"
#else
#include "nex_files.h"
#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include <mutex>
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
  Impl(const std::string &path,bool writable):writable(writable){
    if(path.empty() || path.find('\0')!=std::string::npos)throw DataError("CAPABILITY","file root is not configured");
    // The host selects the root. User-supplied paths below it never follow links.
    root=Descriptor(::open(path.c_str(),O_RDONLY|O_DIRECTORY|O_CLOEXEC));
    if(root.get()<0)throw DataError("CAPABILITY","configured file root is unavailable");
  }
  template<class Content> Content read(const std::string &relative,const Poll &poll,size_t reservedBytes=0) const;
  template<class Validate> void write(const std::string &relative,std::span<const uint8_t> content,const Poll &poll,Validate validate) const;
};
TextFiles::TextFiles(const std::string &root,bool writable):impl(std::make_shared<Impl>(root,writable)){}
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
  State(Descriptor descriptor,FileMode mode):descriptor(std::move(descriptor)),mode(mode){}
};
namespace {
template<class Lease,class Operation>
auto streamCall(const Lease &lease,const TextFiles::Poll &poll,Operation operation) {
  const auto &state=lease.value();
  for(;;){
    check(poll);lease.check();
    decltype(operation(state)) result;int error;
    {
      std::lock_guard guard(state.mutex);lease.check();
      result=operation(state);error=errno;
    }
    if(result<0){if(error==EINTR)continue;ioError(error);}
    check(poll);lease.check();return result;
  }
}
}
ByteBuffer FileResource::read(int64_t maximum,const Poll &poll) const {
  auto lease=owner.acquire();auto callback=poll;
  if(lease.value().mode!=FileMode::Read)throw DataError("CAPABILITY","file handle does not permit reads");
  if(maximum<0)throw DataError("E_RANGE","read size must be nonnegative");
  if(uint64_t(maximum)>TextFiles::byteLimit)throw DataError("LIMIT","read size exceeds byte limit");
  std::vector<uint8_t> content(static_cast<size_t>(maximum));
  auto count=streamCall(lease,callback,[&](const auto &state){return ::read(state.descriptor.get(),content.data(),content.size());});
  content.resize(size_t(count));return ByteBuffer::owned(std::move(content));
}
int64_t FileResource::write(const ByteBuffer &bytes,const Poll &poll) const {
  auto lease=owner.acquire();auto content=bytes;auto callback=poll;
  if(lease.value().mode==FileMode::Read)throw DataError("CAPABILITY","file handle does not permit writes");
  if(uint64_t(content.length())>TextFiles::byteLimit)throw DataError("LIMIT","write size exceeds byte limit");
  auto view=content.view();
  return streamCall(lease,callback,[&](const auto &state){return ::write(state.descriptor.get(),view.data(),view.size());});
}
int64_t FileResource::seek(int64_t offset,const Poll &poll) const {
  auto lease=owner.acquire();auto callback=poll;
  if(offset<0 || uint64_t(offset)>uint64_t(std::numeric_limits<off_t>::max()))
    throw DataError("E_RANGE","file offset is outside supported range");
  return streamCall(lease,callback,[&](const auto &state){return ::lseek(state.descriptor.get(),off_t(offset),SEEK_SET);});
}
int64_t FileResource::size(const Poll &poll) const {
  auto lease=owner.acquire();auto callback=poll;
  return streamCall(lease,callback,[](const auto &state)->int64_t{
    struct stat info{};if(::fstat(state.descriptor.get(),&info))return -1;
    if(info.st_size<0 || uint64_t(info.st_size)>uint64_t(std::numeric_limits<int64_t>::max()))
      throw DataError("LIMIT","file size exceeds supported range");
    return int64_t(info.st_size);
  });
}
void FileResource::flush(const Poll &poll) const {
  auto lease=owner.acquire();auto callback=poll;
  if(lease.value().mode==FileMode::Read)throw DataError("CAPABILITY","file handle does not permit writes");
  streamCall(lease,callback,[](const auto &state){return ::fsync(state.descriptor.get());});
}
ResourceDomain TextFiles::resourceScope(size_t limit) const {return impl->resources.child(limit);}
FileResource TextFiles::open(const std::string &relative,FileMode mode,const Poll &poll) const {
  auto retained=impl;
  return openIn(retained->resources,relative,mode,poll);
}
FileResource TextFiles::openIn(const ResourceDomain &scope,const std::string &relative,FileMode mode,const Poll &poll) const {
  auto retained=impl;auto path=relative;auto callback=poll;
  if(!scope.descendsFrom(retained->resources))throw DataError("CAPABILITY","file resource scope belongs to another capability");
  if(mode!=FileMode::Read&&mode!=FileMode::WriteTruncate&&mode!=FileMode::Append)
    throw DataError("VALIDATION","invalid file mode");
  if(mode!=FileMode::Read&&!retained->writable)throw DataError("CAPABILITY","file capability does not permit writes");
  return FileResource(scope.make<FileResource::State>([retained,path=std::move(path),callback=std::move(callback),mode](const ResourcePermit &permit){
    auto poll=[&]{permit.check();check(callback);permit.check();};
    poll();auto parts=components(path);auto directory=parent(retained->root.get(),parts,poll);poll();
    struct stat existing{};
    if(!::fstatat(directory.get(),parts.back().c_str(),&existing,AT_SYMLINK_NOFOLLOW)){
      if(!S_ISREG(existing.st_mode))throw DataError("VALIDATION","only regular files are supported");
    }else if(errno!=ENOENT)ioError(errno);
    int flags=O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK;
    flags|=mode==FileMode::Read?O_RDONLY:O_WRONLY|O_CREAT;
    if(mode==FileMode::Append)flags|=O_APPEND;
    Descriptor file(::openat(directory.get(),parts.back().c_str(),flags,0600));
    if(file.get()<0)ioError(errno);
    struct stat info{};if(::fstat(file.get(),&info))ioError(errno);
    if(!S_ISREG(info.st_mode))throw DataError("VALIDATION","only regular files are supported");
    poll();
    if(mode==FileMode::WriteTruncate){
      while(::ftruncate(file.get(),0)){if(errno!=EINTR)ioError(errno);poll();}
    }
    return std::make_unique<FileResource::State>(std::move(file),mode);
  }));
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
  ~Impl(){currentFiles=previous;}
};
FileScope::FileScope(bool allowed):impl(std::make_unique<Impl>(allowed)){}
FileScope::FileScope(TextFiles &capability):impl(std::make_unique<Impl>(capability.retain())){}
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
