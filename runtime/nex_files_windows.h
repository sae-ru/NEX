// Included once by nex_files.cpp for the Windows runtime implementation.
#include "nex_files.h"
#include "nex_platform.h"
#include "nex_external_resource.h"
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstring>
#include <limits>
#include <mutex>
#include <string_view>
#include <winternl.h>
#include <bcrypt.h>

namespace nexrt {
namespace {
class Descriptor {
  HANDLE value=INVALID_HANDLE_VALUE;
public:
  explicit Descriptor(HANDLE value=INVALID_HANDLE_VALUE):value(value){}
  ~Descriptor(){if(value&&value!=INVALID_HANDLE_VALUE)CloseHandle(value);}
  Descriptor(const Descriptor&)=delete;
  Descriptor &operator=(const Descriptor&)=delete;
  Descriptor(Descriptor &&other)noexcept:value(other.value){other.value=INVALID_HANDLE_VALUE;}
  Descriptor &operator=(Descriptor &&other)noexcept{
    if(this!=&other){if(value&&value!=INVALID_HANDLE_VALUE)CloseHandle(value);value=other.value;other.value=INVALID_HANDLE_VALUE;}return *this;
  }
  HANDLE get()const{return value;}
};
[[noreturn]] void ioError(DWORD code){
  if(code==ERROR_FILE_NOT_FOUND||code==ERROR_PATH_NOT_FOUND)throw DataError("NOT_FOUND","file or parent directory does not exist");
  if(code==ERROR_ACCESS_DENIED||code==ERROR_PRIVILEGE_NOT_HELD||code==ERROR_SHARING_VIOLATION||code==ERROR_WRITE_PROTECT)
    throw DataError("PERMISSION","file operation is not permitted");
  if(code==ERROR_DIRECTORY||code==ERROR_INVALID_NAME||code==ERROR_CANT_ACCESS_FILE||code==ERROR_FILENAME_EXCED_RANGE||code==ERROR_CANT_RESOLVE_FILENAME)
    throw DataError("VALIDATION","file path is not a regular file or contains a reparse point");
  if(code==ERROR_FILE_EXISTS||code==ERROR_ALREADY_EXISTS)throw DataError("E_FILE_EXISTS","temporary name already exists");
  if(code==ERROR_FILE_TOO_LARGE||code==ERROR_ARITHMETIC_OVERFLOW)throw DataError("LIMIT","file exceeds supported limits");
  throw DataError("E_FILE","filesystem operation failed");
}
void status(NTSTATUS value){
  // RtlNtStatusToDosError maps STATUS_FILE_IS_A_DIRECTORY to access denied,
  // losing the file-kind distinction required by the public adapter contract.
  if(static_cast<ULONG>(value)==0xc00000baUL)throw DataError("VALIDATION","file path is not a regular file");
  if(value<0)ioError(RtlNtStatusToDosError(value));
}
void check(const TextFiles::Poll &poll){if(poll)poll();}
bool absoluteRoot(const std::string &path){
  return (path.size()>=3&&((path[0]>='A'&&path[0]<='Z')||(path[0]>='a'&&path[0]<='z'))&&path[1]==':'&&(path[2]=='\\'||path[2]=='/'))||path.starts_with("\\\\");
}
std::vector<std::string> components(const std::string &relative){
  if(relative.empty()||relative.size()>TextFiles::pathLimit||relative.front()=='/'||relative.find('\0')!=std::string::npos)
    throw DataError("VALIDATION","file path must be a bounded nonempty relative path");
  unicodeOffsets(relative,false);std::vector<std::string> result;
  for(size_t offset=0;offset<relative.size();){
    auto end=relative.find('/',offset);if(end==std::string::npos)end=relative.size();auto part=relative.substr(offset,end-offset);
    if(part.empty()||part=="."||part==".."||result.size()==128||part.find_first_of("\\:<>\"|?*")!=std::string::npos||part.back()=='.'||part.back()==' '||
       std::any_of(part.begin(),part.end(),[](unsigned char c){return c<32;}))
      throw DataError("VALIDATION","file path contains an invalid Windows component");
    auto base=part.substr(0,part.find('.'));for(auto &c:base)if(c>='a'&&c<='z')c-=32;
    if(base=="CON"||base=="PRN"||base=="AUX"||base=="NUL"||base=="CONIN$"||base=="CONOUT$"||
       ((base.starts_with("COM")||base.starts_with("LPT"))&&
        ((base.size()==4&&base[3]>='1'&&base[3]<='9')||base.substr(3)=="¹"||base.substr(3)=="²"||base.substr(3)=="³")))
      throw DataError("VALIDATION","file path contains a reserved Windows component");
    result.push_back(std::move(part));if(end==relative.size())break;offset=end+1;
    if(offset==relative.size())throw DataError("VALIDATION","file path has a trailing separator");
  }
  return result;
}
void kind(HANDLE file,bool directory){
  FILE_ATTRIBUTE_TAG_INFO info{};
  if(GetFileType(file)!=FILE_TYPE_DISK)throw DataError("VALIDATION","only regular disk files and directories are supported");
  if(!GetFileInformationByHandleEx(file,FileAttributeTagInfo,&info,sizeof(info)))ioError(GetLastError());
  if((info.FileAttributes&FILE_ATTRIBUTE_REPARSE_POINT)||bool(info.FileAttributes&FILE_ATTRIBUTE_DIRECTORY)!=directory)
    throw DataError("VALIDATION","file path is not the required regular file or contains a reparse point");
}
struct PrivateSecurity {
  SECURITY_DESCRIPTOR descriptor{};
  std::vector<unsigned char> token,acl;
  PrivateSecurity(){
    HANDLE raw=nullptr;
    if(!OpenThreadToken(GetCurrentThread(),TOKEN_QUERY,TRUE,&raw)){
      if(GetLastError()!=ERROR_NO_TOKEN)ioError(GetLastError());
      if(!OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&raw))ioError(GetLastError());
    }
    Descriptor handle(raw);DWORD size=0;
    GetTokenInformation(handle.get(),TokenUser,nullptr,0,&size);
    if(!size||GetLastError()!=ERROR_INSUFFICIENT_BUFFER)ioError(GetLastError());
    token.resize(size);if(!GetTokenInformation(handle.get(),TokenUser,token.data(),size,&size))ioError(GetLastError());
    auto sid=reinterpret_cast<TOKEN_USER*>(token.data())->User.Sid;
    auto bytes=DWORD(sizeof(ACL)+sizeof(ACCESS_ALLOWED_ACE)-sizeof(DWORD)+GetLengthSid(sid));acl.resize(bytes);
    if(!InitializeAcl(reinterpret_cast<PACL>(acl.data()),bytes,ACL_REVISION)||
       !AddAccessAllowedAceEx(reinterpret_cast<PACL>(acl.data()),ACL_REVISION,0,FILE_ALL_ACCESS,sid)||
       !InitializeSecurityDescriptor(&descriptor,SECURITY_DESCRIPTOR_REVISION)||
       !SetSecurityDescriptorDacl(&descriptor,TRUE,reinterpret_cast<PACL>(acl.data()),FALSE)||
       !SetSecurityDescriptorControl(&descriptor,SE_DACL_PROTECTED,SE_DACL_PROTECTED))ioError(GetLastError());
  }
};
Descriptor openRelative(HANDLE root,const std::string &name,ACCESS_MASK access,ULONG disposition,ULONG options,PSECURITY_DESCRIPTOR security=nullptr){
  auto text=platform::wide(name);if(text.size()>32767)throw DataError("VALIDATION","file component exceeds platform limit");
  UNICODE_STRING string{};string.Buffer=text.data();string.Length=USHORT(text.size()*sizeof(wchar_t));string.MaximumLength=string.Length;
  OBJECT_ATTRIBUTES attributes{};attributes.Length=sizeof(attributes);attributes.RootDirectory=root;attributes.ObjectName=&string;attributes.Attributes=OBJ_CASE_INSENSITIVE;attributes.SecurityDescriptor=security;
  IO_STATUS_BLOCK io{};HANDLE file=INVALID_HANDLE_VALUE;
  status(NtCreateFile(&file,access|FILE_READ_ATTRIBUTES|SYNCHRONIZE,&attributes,&io,nullptr,FILE_ATTRIBUTE_NORMAL,
    FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,disposition,options|FILE_OPEN_REPARSE_POINT|FILE_SYNCHRONOUS_IO_NONALERT,nullptr,0));
  return Descriptor(file);
}
Descriptor parent(HANDLE root,const std::vector<std::string> &parts,const TextFiles::Poll &poll){
  HANDLE value=nullptr;if(!DuplicateHandle(GetCurrentProcess(),root,GetCurrentProcess(),&value,0,FALSE,DUPLICATE_SAME_ACCESS))ioError(GetLastError());
  Descriptor directory(value);
  for(size_t i=0;i+1<parts.size();++i){check(poll);auto next=openRelative(directory.get(),parts[i],FILE_TRAVERSE,FILE_OPEN,FILE_DIRECTORY_FILE);kind(next.get(),true);directory=std::move(next);}
  return directory;
}
int64_t fileSize(HANDLE file){LARGE_INTEGER size{};if(!GetFileSizeEx(file,&size))ioError(GetLastError());if(size.QuadPart<0)throw DataError("LIMIT","file size exceeds supported range");return size.QuadPart;}
size_t winRead(HANDLE file,void *data,size_t size){if(!size)return 0;DWORD count=0;if(!ReadFile(file,data,DWORD(size),&count,nullptr)){auto error=GetLastError();if(error==ERROR_HANDLE_EOF)return 0;ioError(error);}return count;}
size_t winWrite(HANDLE file,const void *data,size_t size){if(!size)return 0;DWORD count=0;if(!WriteFile(file,data,DWORD(size),&count,nullptr))ioError(GetLastError());return count;}
void flush(HANDLE file){if(!FlushFileBuffers(file))ioError(GetLastError());}
void deleteTemporary(HANDLE file)noexcept{FILE_DISPOSITION_INFORMATION info{TRUE};IO_STATUS_BLOCK io{};NtSetInformationFile(file,&io,&info,sizeof(info),FileDispositionInformation);}
struct Temporary {
  Descriptor descriptor;
  bool published=false;
  explicit Temporary(HANDLE parent){
    static constexpr char hex[]="0123456789abcdef";PrivateSecurity security;
    for(unsigned attempt=0;attempt<16;++attempt){
      std::array<unsigned char,16> random{};status(BCryptGenRandom(nullptr,random.data(),ULONG(random.size()),BCRYPT_USE_SYSTEM_PREFERRED_RNG));std::string name=".nex-write-";
      for(auto byte:random){name+=hex[byte>>4];name+=hex[byte&15];}
      try{descriptor=openRelative(parent,name,FILE_WRITE_DATA|DELETE,FILE_CREATE,FILE_NON_DIRECTORY_FILE,&security.descriptor);return;}
      catch(const DataError &error){if(error.code!="E_FILE_EXISTS")throw;}
    }
    throw DataError("E_FILE","cannot reserve a temporary file");
  }
  ~Temporary(){if(!published&&descriptor.get()!=INVALID_HANDLE_VALUE)deleteTemporary(descriptor.get());}
  void publish(HANDLE parent,const std::string &name){
    // The user-mode MinGW NT declaration predates the Flags union. Class65
    // uses the documented Windows10 1709 layout and keeps opened readers on
    // the replaced file. No pathname-based or non-atomic fallback is used.
    struct Rename {ULONG flags;HANDLE root;ULONG length;WCHAR name[1];};
    static_assert(offsetof(Rename,root)==offsetof(FILE_RENAME_INFORMATION,RootDirectory));
    static_assert(offsetof(Rename,name)==offsetof(FILE_RENAME_INFORMATION,FileName));
    auto text=platform::wide(name);auto size=sizeof(Rename)+text.size()*sizeof(wchar_t);std::vector<std::max_align_t> storage((size+sizeof(std::max_align_t)-1)/sizeof(std::max_align_t));
    auto info=reinterpret_cast<Rename*>(storage.data());info->flags=0x00000001|0x00000002;info->root=parent;info->length=ULONG(text.size()*sizeof(wchar_t));std::memcpy(info->name,text.data(),info->length);IO_STATUS_BLOCK io{};
    status(NtSetInformationFile(descriptor.get(),&io,info,ULONG(size),static_cast<FILE_INFORMATION_CLASS>(65)));published=true;
  }
};
void existingRegular(HANDLE parent,const std::string &name){
  try{auto file=openRelative(parent,name,0,FILE_OPEN,FILE_NON_DIRECTORY_FILE);kind(file.get(),false);}
  catch(const DataError &error){if(error.code!="NOT_FOUND")throw;}
}
}
struct TextFiles::Impl {
  Descriptor root;
  bool writable;
  ResourceDomain resources;
  const std::shared_ptr<const FileIOObserver> observer;
  Impl(const std::string &path,bool writable,FileIOObserver observer={}):writable(writable),observer(observer?std::make_shared<const FileIOObserver>(std::move(observer)):nullptr){
    if(path.empty()||path.find('\0')!=std::string::npos||!absoluteRoot(path))throw DataError("CAPABILITY","file root must be an absolute configured directory");
    auto text=platform::wide(path);
    root=Descriptor(CreateFileW(text.c_str(),FILE_TRAVERSE|FILE_READ_ATTRIBUTES|SYNCHRONIZE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,FILE_FLAG_BACKUP_SEMANTICS,nullptr));
    if(root.get()==INVALID_HANDLE_VALUE)throw DataError("CAPABILITY","configured file root is unavailable");
    // A trusted host root may follow an alias; every child is opened no-follow.
    BY_HANDLE_FILE_INFORMATION info{};if(GetFileType(root.get())!=FILE_TYPE_DISK||!GetFileInformationByHandle(root.get(),&info)||!(info.dwFileAttributes&FILE_ATTRIBUTE_DIRECTORY))throw DataError("CAPABILITY","configured file root is unavailable");
  }
  template<class Content> Content read(const std::string &relative,const Poll &poll)const{
    check(poll);auto parts=components(relative);auto directory=parent(root.get(),parts,poll);auto file=openRelative(directory.get(),parts.back(),FILE_READ_DATA,FILE_OPEN,FILE_NON_DIRECTORY_FILE);kind(file.get(),false);auto size=fileSize(file.get());
    if(uint64_t(size)>byteLimit)throw DataError("LIMIT","file exceeds byte limit");
    Content content;content.reserve(size_t(size));std::array<char,65536> buffer{};
    for(;;){check(poll);auto count=winRead(file.get(),buffer.data(),buffer.size());if(!count)break;if(count>byteLimit-content.size())throw DataError("LIMIT","file exceeds byte limit");content.insert(content.end(),buffer.data(),buffer.data()+count);}
    return content;
  }
  template<class Validate> void write(const std::string &relative,std::span<const uint8_t> content,const Poll &poll,Validate validate)const{
    if(!writable)throw DataError("CAPABILITY","file capability does not permit writes");check(poll);auto parts=components(relative);if(content.size()>byteLimit)throw DataError("LIMIT","file value exceeds byte limit");validate();auto directory=parent(root.get(),parts,poll);
    // Recheck cancellation after acquiring the pinned parent and before any
    // mutation. A host may replace its pathname here; every subsequent open
    // and publication must continue to use this same admitted handle.
    check(poll);existingRegular(directory.get(),parts.back());Temporary temporary(directory.get());
    for(size_t offset=0;offset<content.size();){check(poll);auto size=std::min<size_t>(65536,content.size()-offset);auto count=winWrite(temporary.descriptor.get(),content.data()+offset,size);if(!count)throw DataError("E_FILE","file write made no progress");offset+=count;}
    check(poll);flush(temporary.descriptor.get());check(poll);temporary.publish(directory.get(),parts.back());
  }
};
TextFiles::TextFiles(const std::string &root,bool writable):impl(std::make_shared<Impl>(root,writable)){}
TextFiles::TextFiles(const std::string &root,bool writable,FileIOObserver observer):impl(std::make_shared<Impl>(root,writable,std::move(observer))){}
TextFiles::~TextFiles()=default;
std::unique_ptr<TextFiles> TextFiles::retain()const{return std::unique_ptr<TextFiles>(new TextFiles(impl));}
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
  auto result=pin.files->read<std::vector<uint8_t>>(std::string(pin.relative.get(),pin.length),checkpoint);
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
  State(Descriptor descriptor,FileMode mode,std::shared_ptr<const FileIOObserver> observer):descriptor(std::move(descriptor)),mode(mode),observer(std::move(observer)){}
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
auto streamCall(const Lease &lease,const TextFiles::Poll &poll,FileIOOperation kind,int64_t argument,Operation operation){
  const auto &state=lease.value();check(poll);lease.check();
  observeFile(state.observer,kind,FileIOPhase::Before,argument);
  if(state.observer){check(poll);lease.check();}
  int64_t result;DWORD error;
  {std::lock_guard guard(state.mutex);lease.check();result=operation(state);error=GetLastError();}
  // Callbacks run after the real syscall and outside the cursor lock. A
  // callback can revoke/close but cannot publish an unadmitted completion.
  observeFile(state.observer,kind,FileIOPhase::After,argument,result,result<0?int(error):0);
  if(result<0)ioError(error);
  check(poll);lease.check();return result;
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
void FileStreamLease::checkRead(int64_t maximum)const{
  check();if(physical.value().mode!=FileMode::Read)throw DataError("CAPABILITY","file handle does not permit reads");
  if(maximum<0)throw DataError("E_RANGE","read size must be nonnegative");
  if(uint64_t(maximum)>TextFiles::byteLimit)throw DataError("LIMIT","read size exceeds byte limit");
}
void FileStreamLease::checkWrite(size_t bytes)const{
  check();if(physical.value().mode==FileMode::Read)throw DataError("CAPABILITY","file handle does not permit writes");
  if(bytes>TextFiles::byteLimit)throw DataError("LIMIT","write size exceeds byte limit");
}
void FileStreamLease::checkSeek(int64_t offset)const{
  check();if(offset<0)throw DataError("E_RANGE","file offset is outside supported range");
}
std::vector<uint8_t> FileStreamLease::read(int64_t maximum,const Poll &poll)const{
  auto retained=*this;auto lease=retained.physical;auto callback=[retained,copy=poll]{retained.check();if(copy)copy();retained.check();};checkRead(maximum);
  std::vector<uint8_t> content(static_cast<size_t>(maximum));
  auto count=streamCall(lease,callback,FileIOOperation::Read,maximum,[&](const auto &state)->int64_t{
    if(content.empty())return 0;DWORD count=0;
    if(!ReadFile(state.descriptor.get(),content.data(),DWORD(content.size()),&count,nullptr))return GetLastError()==ERROR_HANDLE_EOF?0:-1;
    return count;
  });content.resize(size_t(count));return content;
}
int64_t FileStreamLease::write(std::span<const uint8_t> content,const Poll &poll)const{
  auto retained=*this;auto lease=retained.physical;auto callback=[retained,copy=poll]{retained.check();if(copy)copy();retained.check();};checkWrite(content.size());
  return streamCall(lease,callback,FileIOOperation::Write,int64_t(content.size()),[&](const auto &state)->int64_t{
    if(content.empty())return 0;DWORD count=0;
    if(!WriteFile(state.descriptor.get(),content.data(),DWORD(content.size()),&count,nullptr))return -1;return count;
  });
}
int64_t FileStreamLease::seek(int64_t offset,const Poll &poll)const{
  auto retained=*this;auto lease=retained.physical;auto callback=[retained,copy=poll]{retained.check();if(copy)copy();retained.check();};checkSeek(offset);
  return streamCall(lease,callback,FileIOOperation::Seek,offset,[&](const auto &state)->int64_t{LARGE_INTEGER desired{},actual{};desired.QuadPart=offset;if(!SetFilePointerEx(state.descriptor.get(),desired,&actual,FILE_BEGIN))return -1;return actual.QuadPart;});
}
int64_t FileStreamLease::size(const Poll &poll)const{
  auto retained=*this;auto lease=retained.physical;auto callback=[retained,copy=poll]{retained.check();if(copy)copy();retained.check();};
  return streamCall(lease,callback,FileIOOperation::Size,0,[](const auto &state)->int64_t{
    LARGE_INTEGER size{};if(!GetFileSizeEx(state.descriptor.get(),&size))return -1;
    if(size.QuadPart<0){SetLastError(ERROR_FILE_TOO_LARGE);return -1;}return size.QuadPart;
  });
}
void FileStreamLease::flush(const Poll &poll)const{
  auto retained=*this;auto lease=retained.physical;auto callback=[retained,copy=poll]{retained.check();if(copy)copy();retained.check();};checkWrite(0);
  streamCall(lease,callback,FileIOOperation::Flush,0,[](const auto &state)->int64_t{return FlushFileBuffers(state.descriptor.get())?0:-1;});
}
ByteBuffer FileResource::read(int64_t maximum,const Poll &poll)const{return ByteBuffer::owned(lease().read(maximum,poll));}
int64_t FileResource::write(const ByteBuffer &bytes,const Poll &poll)const{auto retained=bytes;return lease().write(retained.view(),poll);}
int64_t FileResource::seek(int64_t offset,const Poll &poll)const{return lease().seek(offset,poll);}
int64_t FileResource::size(const Poll &poll)const{return lease().size(poll);}
void FileResource::flush(const Poll &poll)const{lease().flush(poll);}
ResourceDomain TextFiles::resourceScope(size_t limit)const{return impl->resources.child(limit);}
FileResource TextFiles::open(const std::string &relative,FileMode mode,const Poll &poll)const{auto retained=impl;return openIn(retained->resources,relative,mode,poll);}
FileResource TextFiles::openIn(const ResourceDomain &scope,const std::string &relative,FileMode mode,const Poll &poll)const{
  if(!scope.descendsFrom(impl->resources))throw DataError("CAPABILITY","file resource scope belongs to another capability");
  return openInAccess(scope.access(),relative,mode,poll);
}
FileResource TextFiles::openInAccess(const ResourceAccess &scope,const std::string &relative,FileMode mode,const Poll &poll,ResourceRegionAuthority region,const std::shared_ptr<ResourceExecutor> &cleanup)const{
  auto retained=impl;auto path=relative;auto callback=poll;auto executor=cleanup;
  if(mode!=FileMode::Read&&mode!=FileMode::WriteTruncate&&mode!=FileMode::Append)throw DataError("VALIDATION","invalid file mode");
  if(mode!=FileMode::Read&&!retained->writable)throw DataError("CAPABILITY","file capability does not permit writes");
  ResourceRegionOwner logical;ResourceSettlement settlement;
  std::optional<resource_detail::SettlementGuard> creation;
  if(region){logical=region.reserve();settlement=ResourceSettlement::pending();creation.emplace(settlement);logical.attach(settlement);}
  auto create=[retained,path=std::move(path),callback=std::move(callback),mode,logical](const ResourcePermit &permit){
    auto poll=[&]{if(logical)logical.checkCreation();permit.check();check(callback);permit.check();if(logical)logical.checkCreation();};poll();auto parts=components(path);auto directory=parent(retained->root.get(),parts,poll);poll();existingRegular(directory.get(),parts.back());
    auto operation=mode==FileMode::Read?FileIOOperation::OpenRead:mode==FileMode::WriteTruncate?FileIOOperation::OpenWrite:FileIOOperation::OpenAppend;
    observeFile(retained->observer,operation,FileIOPhase::Before,0);if(retained->observer)poll();
    std::unique_ptr<PrivateSecurity> security;if(mode!=FileMode::Read)security=std::make_unique<PrivateSecurity>();
    auto file=openRelative(directory.get(),parts.back(),mode==FileMode::Read?FILE_READ_DATA:mode==FileMode::Append?FILE_APPEND_DATA:FILE_WRITE_DATA,
      mode==FileMode::Read?FILE_OPEN:FILE_OPEN_IF,FILE_NON_DIRECTORY_FILE,security?&security->descriptor:nullptr);kind(file.get(),false);poll();
    if(mode==FileMode::WriteTruncate){LARGE_INTEGER zero{};if(!SetFilePointerEx(file.get(),zero,nullptr,FILE_BEGIN)||!SetEndOfFile(file.get()))ioError(GetLastError());}
    auto result=std::make_unique<FileResource::State>(std::move(file),mode,retained->observer);
    observeFile(retained->observer,operation,FileIOPhase::After,0);if(retained->observer)poll();return result;
  };
  auto physical=executor?scope.makeOnExecutor<FileResource::State>(executor,std::move(create),settlement,true):scope.make<FileResource::State>(std::move(create),settlement);
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
      if(auto value=platform::environment("NEX_FILES_ROOT"))root=*value;
      if(auto value=platform::environment("NEX_FILES_WRITE"))writable=*value=="1";
    }
  }
  explicit Access(std::unique_ptr<TextFiles> capability):attempted(true),owned(std::move(capability)){}
  Access(std::unique_ptr<TextFiles> capability,const ResourceDomain &scope)
      :attempted(true),owned(std::move(capability)),resources(std::make_unique<ResourceDomain>(scope.child())){}
  TextFiles &capability(){
    if(!attempted){
      attempted=true;
      try{
        if(root.empty()||!absoluteRoot(root))throw DataError("CAPABILITY","file root must be an absolute configured directory");
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
