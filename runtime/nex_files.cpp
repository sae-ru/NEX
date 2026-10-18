#include "nex_files.h"
#include <algorithm>
#include <array>
#include <cerrno>
#include <cstdio>
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
  Impl(const std::string &path,bool writable):writable(writable){
    if(path.empty() || path.find('\0')!=std::string::npos)throw DataError("CAPABILITY","file root is not configured");
    // The host selects the root. User-supplied paths below it never follow links.
    root=Descriptor(::open(path.c_str(),O_RDONLY|O_DIRECTORY|O_CLOEXEC));
    if(root.get()<0)throw DataError("CAPABILITY","configured file root is unavailable");
  }
};
TextFiles::TextFiles(const std::string &root,bool writable):impl(std::make_unique<Impl>(root,writable)){}
TextFiles::~TextFiles()=default;
Value TextFiles::read(const std::string &relative,const Poll &poll) const {
  try{
    check(poll);auto parts=components(relative);auto directory=parent(impl->root.get(),parts,poll);
    Descriptor file(::openat(directory.get(),parts.back().c_str(),O_RDONLY|O_CLOEXEC|O_NOFOLLOW|O_NONBLOCK));
    if(file.get()<0)ioError(errno);
    struct stat info{};if(::fstat(file.get(),&info))ioError(errno);
    if(!S_ISREG(info.st_mode))throw DataError("VALIDATION","only regular text files are supported");
    if(info.st_size<0 || uint64_t(info.st_size)>textLimit)throw DataError("LIMIT","text file exceeds byte limit");
    std::string text;text.reserve(size_t(info.st_size));std::array<char,65536> buffer{};
    for(;;){
      check(poll);auto count=::read(file.get(),buffer.data(),buffer.size());
      if(count<0){if(errno==EINTR)continue;ioError(errno);}
      if(!count)break;
      if(size_t(count)>textLimit-text.size())throw DataError("LIMIT","text file exceeds byte limit");
      text.append(buffer.data(),size_t(count));
    }
    return success(Value(string(text)));
  }catch(const DataError &error){return failure(error.code,error.what());}
}
Value TextFiles::write(const std::string &relative,const std::string &text,const Poll &poll) const {
  try{
    if(!impl->writable)throw DataError("CAPABILITY","file capability does not permit writes");
    check(poll);auto parts=components(relative);
    if(text.size()>textLimit)throw DataError("LIMIT","text value exceeds byte limit");
    unicodeOffsets(text,false);
    auto directory=parent(impl->root.get(),parts,poll);struct stat existing{};
    if(!::fstatat(directory.get(),parts.back().c_str(),&existing,AT_SYMLINK_NOFOLLOW)){
      if(!S_ISREG(existing.st_mode))throw DataError("VALIDATION","write destination must be a regular file");
    }else if(errno!=ENOENT)ioError(errno);
    Temporary temporary(directory.get());
    for(size_t offset=0;offset<text.size();){
      check(poll);auto size=std::min<size_t>(65536,text.size()-offset);
      auto count=::write(temporary.descriptor.get(),text.data()+offset,size);
      if(count<0){if(errno==EINTR)continue;ioError(errno);}
      if(count==0)throw DataError("E_FILE","file write made no progress");
      offset+=size_t(count);
    }
    check(poll);
    while(::fsync(temporary.descriptor.get())){if(errno!=EINTR)ioError(errno);check(poll);}
    check(poll);
    if(::renameat(directory.get(),temporary.name.c_str(),directory.get(),parts.back().c_str()))ioError(errno);
    temporary.published=true;
    return success(Value(1,true));
  }catch(const DataError &error){return failure(error.code,error.what());}
}
}
