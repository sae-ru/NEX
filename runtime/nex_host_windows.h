#pragma once
#ifdef _WIN32
#include "nex_platform.h"
#include <array>
#include <algorithm>
#include <cerrno>
#include <cstring>
#include <filesystem>
#include <vector>
#include <bcrypt.h>
#include <aclapi.h>
#include <fcntl.h>
#include <io.h>
#include <optional>
#ifdef interface
#undef interface
#endif
#ifdef ERROR
#undef ERROR
#endif
#ifdef IGNORE
#undef IGNORE
#endif

namespace nexrt::host_windows {
struct Handle {
  HANDLE value=INVALID_HANDLE_VALUE;
  explicit Handle(HANDLE value=INVALID_HANDLE_VALUE):value(value){}
  ~Handle(){if(value&&value!=INVALID_HANDLE_VALUE)CloseHandle(value);}
  Handle(const Handle&)=delete;Handle &operator=(const Handle&)=delete;
  HANDLE release(){auto result=value;value=INVALID_HANDLE_VALUE;return result;}
};
inline int error(DWORD code){
  errno=code==ERROR_FILE_EXISTS||code==ERROR_ALREADY_EXISTS?EEXIST:
    code==ERROR_FILE_NOT_FOUND||code==ERROR_PATH_NOT_FOUND?ENOENT:
    code==ERROR_ACCESS_DENIED||code==ERROR_SHARING_VIOLATION?EACCES:EIO;
  return -1;
}
struct PrivateSecurity {
  SECURITY_DESCRIPTOR descriptor{};std::vector<unsigned char> token,container,acl;
  std::vector<PSID> principals;
  explicit PrivateSecurity(DWORD access=FILE_ALL_ACCESS,DWORD inheritance=OBJECT_INHERIT_ACE|CONTAINER_INHERIT_ACE){
    HANDLE raw=nullptr;
    if(!OpenThreadToken(GetCurrentThread(),TOKEN_QUERY,TRUE,&raw)){
      if(GetLastError()!=ERROR_NO_TOKEN||!OpenProcessToken(GetCurrentProcess(),TOKEN_QUERY,&raw))throw DataError("E_FILE","cannot inspect current Windows principal");
    }
    Handle handle(raw);DWORD count=0;GetTokenInformation(raw,TokenUser,nullptr,0,&count);
    token.resize(count);
    if(!count||!GetTokenInformation(raw,TokenUser,token.data(),count,&count))throw DataError("E_FILE","cannot inspect current Windows principal");
    auto sid=reinterpret_cast<TOKEN_USER*>(token.data())->User.Sid;
    principals.push_back(sid);
    // TokenIsAppContainer and TokenAppContainerSid have Win32 ABI values29/31.
    // Some supported SDK headers hide their declarations behind _WIN32_WINNT.
    DWORD isContainer=0;
    if(!GetTokenInformation(raw,static_cast<TOKEN_INFORMATION_CLASS>(29),&isContainer,sizeof(isContainer),&count))
      throw DataError("E_FILE","cannot inspect Windows AppContainer principal");
    if(isContainer){
      struct ContainerInformation {PSID sid;};
      count=0;GetTokenInformation(raw,static_cast<TOKEN_INFORMATION_CLASS>(31),nullptr,0,&count);
      if(count<sizeof(ContainerInformation)||count>65536)
        throw DataError("E_FILE","invalid Windows AppContainer principal size");
      container.resize(count);
      if(!GetTokenInformation(raw,static_cast<TOKEN_INFORMATION_CLASS>(31),container.data(),count,&count))
        throw DataError("E_FILE","cannot inspect Windows AppContainer principal");
      auto app=reinterpret_cast<ContainerInformation*>(container.data())->sid;
      if(!app||!IsValidSid(app)||EqualSid(sid,app))
        throw DataError("E_FILE","invalid Windows AppContainer principal");
      principals.push_back(app);
    }
    DWORD bytes=sizeof(ACL);
    for(auto principal:principals)bytes+=sizeof(ACCESS_ALLOWED_ACE)-sizeof(DWORD)+GetLengthSid(principal);
    acl.resize(bytes);
    if(!InitializeAcl(reinterpret_cast<PACL>(acl.data()),bytes,ACL_REVISION))
      throw DataError("E_FILE","cannot create private Windows ACL");
    for(auto principal:principals)
      if(!AddAccessAllowedAceEx(reinterpret_cast<PACL>(acl.data()),ACL_REVISION,
           inheritance,access,principal))
        throw DataError("E_FILE","cannot create private Windows ACL");
    if(!InitializeSecurityDescriptor(&descriptor,SECURITY_DESCRIPTOR_REVISION)||
       !SetSecurityDescriptorOwner(&descriptor,sid,FALSE)||
       !SetSecurityDescriptorDacl(&descriptor,TRUE,reinterpret_cast<PACL>(acl.data()),FALSE)||
       !SetSecurityDescriptorControl(&descriptor,SE_DACL_PROTECTED,SE_DACL_PROTECTED))throw DataError("E_FILE","cannot create private Windows ACL");
  }
};
inline bool createPrivateDirectory(const std::filesystem::path &path){
  PrivateSecurity security;SECURITY_ATTRIBUTES attributes{sizeof(attributes),&security.descriptor,FALSE};
  if(CreateDirectoryW(path.c_str(),&attributes))return true;
  error(GetLastError());return false;
}
inline bool isPrivateDirectory(const std::filesystem::path &path){
  Handle directory(CreateFileW(path.c_str(),READ_CONTROL|FILE_READ_ATTRIBUTES,
    FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,
    FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_BACKUP_SEMANTICS,nullptr));
  FILE_ATTRIBUTE_TAG_INFO info{};
  if(directory.value==INVALID_HANDLE_VALUE||!GetFileInformationByHandleEx(directory.value,FileAttributeTagInfo,&info,sizeof(info))||
     !(info.FileAttributes&FILE_ATTRIBUTE_DIRECTORY)||info.FileAttributes&FILE_ATTRIBUTE_REPARSE_POINT)return false;
  PSECURITY_DESCRIPTOR descriptor=nullptr;PSID owner=nullptr;PACL acl=nullptr;
  if(GetSecurityInfo(directory.value,SE_FILE_OBJECT,OWNER_SECURITY_INFORMATION|DACL_SECURITY_INFORMATION,&owner,nullptr,&acl,nullptr,&descriptor)!=ERROR_SUCCESS)return false;
  struct Release{PSECURITY_DESCRIPTOR value;~Release(){LocalFree(value);}} release{descriptor};
  PrivateSecurity current;auto user=reinterpret_cast<TOKEN_USER*>(current.token.data())->User.Sid;
  SECURITY_DESCRIPTOR_CONTROL control{};DWORD revision=0;
  if(!owner||!EqualSid(owner,user)||!acl||!GetSecurityDescriptorControl(descriptor,&control,&revision)||!(control&SE_DACL_PROTECTED))return false;
  if(acl->AceCount!=current.principals.size())return false;
  std::vector<bool> seen(current.principals.size(),false);
  for(DWORD i=0;i<acl->AceCount;++i){void *raw=nullptr;if(!GetAce(acl,i,&raw))return false;
    auto *ace=static_cast<ACCESS_ALLOWED_ACE*>(raw);
    if(ace->Header.AceType!=ACCESS_ALLOWED_ACE_TYPE)return false;
    auto found=std::find_if(current.principals.begin(),current.principals.end(),
      [&](PSID sid){return EqualSid(&ace->SidStart,sid);});
    if(found==current.principals.end()||seen[found-current.principals.begin()])return false;
    seen[found-current.principals.begin()]=true;
  }return !seen.empty()&&std::all_of(seen.begin(),seen.end(),[](bool value){return value;});
}
struct Identity {
  uint64_t volume=0;std::array<unsigned char,16> file{};bool directory=false;
  bool operator==(const Identity&)const=default;
};
inline std::optional<Identity> identity(HANDLE handle){
  // Some LLVM-MinGW headers hide FILE_ID_INFO behind _WIN32_WINNT. This is
  // its actual24-byte Win32 ABI, not a synthetic POSIX inode or truncated ID.
  struct NativeFileId {uint64_t volume;std::array<unsigned char,16> file;};
  static_assert(sizeof(NativeFileId)==24);
  FILE_ATTRIBUTE_TAG_INFO attributes{};NativeFileId info{};
  if(handle==INVALID_HANDLE_VALUE||GetFileType(handle)!=FILE_TYPE_DISK||
     !GetFileInformationByHandleEx(handle,FileAttributeTagInfo,&attributes,sizeof(attributes))||
     attributes.FileAttributes&FILE_ATTRIBUTE_REPARSE_POINT||
     !GetFileInformationByHandleEx(handle,static_cast<FILE_INFO_BY_HANDLE_CLASS>(18),&info,sizeof(info)))return std::nullopt;
  Identity result;result.volume=info.volume;result.directory=bool(attributes.FileAttributes&FILE_ATTRIBUTE_DIRECTORY);
  result.file=info.file;return result;
}
inline std::optional<Identity> identity(const std::filesystem::path &path){
  Handle file(CreateFileW(path.c_str(),FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,
    OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_BACKUP_SEMANTICS,nullptr));return identity(file.value);
}
inline void privateAccess(const std::filesystem::path &path,DWORD access){
  Handle file(CreateFileW(path.c_str(),WRITE_DAC|READ_CONTROL|FILE_READ_ATTRIBUTES,
    FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,
    FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_BACKUP_SEMANTICS,nullptr));
  if(!identity(file.value))throw DataError("E_FILE","cannot seal a non-regular or reparse snapshot member");
  PrivateSecurity security(access);
  auto code=SetSecurityInfo(file.value,SE_FILE_OBJECT,DACL_SECURITY_INFORMATION|PROTECTED_DACL_SECURITY_INFORMATION,
    nullptr,nullptr,reinterpret_cast<PACL>(security.acl.data()),nullptr);
  if(code!=ERROR_SUCCESS)throw DataError("E_FILE","cannot set private snapshot ACL: "+std::to_string(code));
}
// Retain cleanup authority before sealing a snapshot directory. A restricted
// process must not need to reopen a read-only path with WRITE_DAC afterwards.
struct DirectoryPermissions {
  Handle handle;
  std::vector<unsigned char> original;
  SECURITY_INFORMATION protection=DACL_SECURITY_INFORMATION;
  explicit DirectoryPermissions(const std::filesystem::path &path):
    handle(CreateFileW(path.c_str(),WRITE_DAC|READ_CONTROL|FILE_READ_ATTRIBUTES,
      FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,
      FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_BACKUP_SEMANTICS,nullptr)){
    auto id=identity(handle.value);
    if(!id||!id->directory)throw DataError("E_FILE","cannot retain private directory cleanup authority");
    PSECURITY_DESCRIPTOR descriptor=nullptr;PACL acl=nullptr;
    auto code=GetSecurityInfo(handle.value,SE_FILE_OBJECT,DACL_SECURITY_INFORMATION,
      nullptr,nullptr,&acl,nullptr,&descriptor);
    if(code!=ERROR_SUCCESS)throw DataError("E_FILE","cannot inspect private directory ACL");
    struct Release{PSECURITY_DESCRIPTOR value;~Release(){LocalFree(value);}} release{descriptor};
    SECURITY_DESCRIPTOR_CONTROL control{};DWORD revision=0;
    if(!acl||acl->AclSize<sizeof(ACL)||!GetSecurityDescriptorControl(descriptor,&control,&revision))
      throw DataError("E_FILE","invalid private directory ACL");
    auto first=reinterpret_cast<const unsigned char*>(acl);
    original.assign(first,first+acl->AclSize);
    protection|=(control&SE_DACL_PROTECTED)?PROTECTED_DACL_SECURITY_INFORMATION:UNPROTECTED_DACL_SECURITY_INFORMATION;
  }
  void seal(DWORD access){
    PrivateSecurity security(access);
    auto code=SetSecurityInfo(handle.value,SE_FILE_OBJECT,DACL_SECURITY_INFORMATION|PROTECTED_DACL_SECURITY_INFORMATION,
      nullptr,nullptr,reinterpret_cast<PACL>(security.acl.data()),nullptr);
    if(code!=ERROR_SUCCESS)throw DataError("E_FILE","cannot seal private directory ACL");
  }
  void restore(){
    auto code=SetSecurityInfo(handle.value,SE_FILE_OBJECT,protection,
      nullptr,nullptr,reinterpret_cast<PACL>(original.data()),nullptr);
    if(code!=ERROR_SUCCESS)throw DataError("E_FILE","cannot restore private directory ACL");
  }
};
inline void writePrivateFile(const std::filesystem::path &path,const std::string &bytes){
  PrivateSecurity security;
  SECURITY_ATTRIBUTES attributes{sizeof(attributes),&security.descriptor,FALSE};
  Handle file(CreateFileW(path.c_str(),GENERIC_WRITE,0,&attributes,CREATE_NEW,FILE_ATTRIBUTE_NORMAL,nullptr));
  if(file.value==INVALID_HANDLE_VALUE)throw DataError("E_FILE","cannot create private Windows file: "+std::to_string(GetLastError()));
  size_t offset=0;
  while(offset<bytes.size()){
    DWORD written=0,count=DWORD(std::min<size_t>(bytes.size()-offset,MAXDWORD));
    if(!WriteFile(file.value,bytes.data()+offset,count,&written,nullptr)||!written)
      throw DataError("E_FILE","cannot write private Windows file: "+std::to_string(GetLastError()));
    offset+=written;
  }
  if(!FlushFileBuffers(file.value))throw DataError("E_FILE","cannot flush private Windows file: "+std::to_string(GetLastError()));
}
inline std::filesystem::path canonical(const std::filesystem::path &path){
  // Win32 normalizes '..' before following reparse points. NEX resolves the
  // actual parent of an explicitly selected configuration, component by
  // component, so a link/../configuration keeps its physical provenance.
  auto full=path.is_absolute()?path:std::filesystem::current_path()/path;
  auto result=full.root_path();
  std::filesystem::path pending;
  for(const auto &part:full.relative_path()){
    if(part==L".")continue;
    if(part==L".."){
      // Resolve links before taking their physical parent. Normal components
      // can be opened together without querying inaccessible ancestors.
      if(!pending.empty()){
        result=std::filesystem::canonical(result/pending);
        pending.clear();
      }
      result=result.parent_path();
    }else pending/=part;
  }
  return std::filesystem::canonical(result/pending);
}
inline int openRegularDescriptor(const std::filesystem::path &path,int flags){
  bool writable=(flags&(_O_WRONLY|_O_RDWR))!=0;DWORD access=(writable?GENERIC_WRITE:GENERIC_READ)|FILE_READ_ATTRIBUTES;
  if(flags&_O_RDWR)access|=GENERIC_READ;
  DWORD disposition=flags&_O_CREAT?(flags&_O_EXCL?CREATE_NEW:flags&_O_TRUNC?CREATE_ALWAYS:OPEN_ALWAYS):OPEN_EXISTING;
  PrivateSecurity security;SECURITY_ATTRIBUTES attributes{sizeof(attributes),&security.descriptor,FALSE};
  Handle file(CreateFileW(path.c_str(),access,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
    flags&_O_CREAT?&attributes:nullptr,disposition,FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_BACKUP_SEMANTICS,nullptr));
  auto id=identity(file.value);if(!id||id->directory){error(GetLastError());return -1;}
  auto fd=::_open_osfhandle(reinterpret_cast<intptr_t>(file.value),_O_BINARY|_O_NOINHERIT|(flags&_O_RDWR?_O_RDWR:writable?_O_WRONLY:_O_RDONLY));
  if(fd>=0)file.release();return fd;
}
inline int synchronize(int fd){
  if(FlushFileBuffers(reinterpret_cast<HANDLE>(::_get_osfhandle(fd))))return 0;return error(GetLastError());
}
inline int64_t fileSize(int fd){LARGE_INTEGER value{};return GetFileSizeEx(reinterpret_cast<HANDLE>(::_get_osfhandle(fd)),&value)?value.QuadPart:-1;}
inline int64_t readAt(int fd,void *buffer,size_t size,int64_t offset){
  if(offset<0){errno=EINVAL;return -1;}
  Handle file(ReOpenFile(reinterpret_cast<HANDLE>(::_get_osfhandle(fd)),GENERIC_READ,
    FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,FILE_FLAG_OVERLAPPED));
  if(file.value==INVALID_HANDLE_VALUE)return error(GetLastError());
  Handle event(CreateEventW(nullptr,TRUE,FALSE,nullptr));if(!event.value)return error(GetLastError());
  OVERLAPPED operation{};operation.Offset=DWORD(uint64_t(offset));operation.OffsetHigh=DWORD(uint64_t(offset)>>32);operation.hEvent=event.value;
  DWORD count=0;auto requested=DWORD(std::min<size_t>(size,MAXDWORD));
  if(!ReadFile(file.value,buffer,requested,&count,&operation)){
    auto code=GetLastError();if(code==ERROR_HANDLE_EOF)return 0;
    if(code!=ERROR_IO_PENDING)return error(code);
    if(!GetOverlappedResult(file.value,&operation,&count,TRUE))return error(GetLastError());
  }return count;
}
inline std::string readRegular(const std::filesystem::path &path,size_t limit){
  Handle file(CreateFileW(path.c_str(),GENERIC_READ,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,
    OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT|FILE_FLAG_BACKUP_SEMANTICS,nullptr));
  FILE_ATTRIBUTE_TAG_INFO info{};LARGE_INTEGER length{};
  if(file.value==INVALID_HANDLE_VALUE||GetFileType(file.value)!=FILE_TYPE_DISK||
     !GetFileInformationByHandleEx(file.value,FileAttributeTagInfo,&info,sizeof(info))||
     info.FileAttributes&(FILE_ATTRIBUTE_DIRECTORY|FILE_ATTRIBUTE_REPARSE_POINT)||!GetFileSizeEx(file.value,&length))
    throw DataError("E_FILE","expected a regular non-reparse Windows file");
  if(length.QuadPart<0||uint64_t(length.QuadPart)>limit)throw DataError("E_LIMIT","host file exceeds byte limit");
  std::string result;std::array<char,65536> buffer{};
  for(;;){DWORD count=0;if(!ReadFile(file.value,buffer.data(),DWORD(buffer.size()),&count,nullptr))throw DataError("E_FILE","cannot read Windows host file");
    if(!count)break;if(count>limit-result.size())throw DataError("E_LIMIT","host file exceeds byte limit");result.append(buffer.data(),count);}
  return result;
}
}

// Private snapshot creation and dynamic-module operations keep the POSIX
// loader's interface while using real Win32 handles and a restricted DLL path.
inline char *mkdtemp(char *pattern){
  auto length=std::strlen(pattern);if(length<6||std::string_view(pattern+length-6)!="XXXXXX"){errno=EINVAL;return nullptr;}
  for(unsigned attempt=0;attempt<128;++attempt){
    std::array<unsigned char,6> random{};
    if(BCryptGenRandom(nullptr,random.data(),ULONG(random.size()),BCRYPT_USE_SYSTEM_PREFERRED_RNG)<0){errno=EIO;return nullptr;}
    for(size_t i=0;i<6;++i)pattern[length-6+i]="0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"[random[i]%62];
    if(nexrt::host_windows::createPrivateDirectory(nexrt::platform::wide(pattern)))return pattern;
    if(errno!=EEXIST)return nullptr;
  }errno=EEXIST;return nullptr;
}
constexpr int RTLD_NOW=2,RTLD_LOCAL=0;
inline thread_local std::string nexWindowsDllError;
inline void *dlopen(const wchar_t *path,int){
  std::wstring filename(path);
  // A trailing dot prevents the Win32 loader from silently adding .dll.
  if(!std::filesystem::path(filename).has_extension())filename+=L'.';
  auto module=LoadLibraryExW(filename.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);
  nexWindowsDllError=module?"":"Windows DLL load failed: "+std::to_string(GetLastError());return module;
}
inline void *dlopen(const char *path,int flags){return dlopen(nexrt::platform::wide(path).c_str(),flags);}
inline int dlclose(void *module){return FreeLibrary(static_cast<HMODULE>(module))?0:-1;}
inline void *dlsym(void *module,const char *name){
  auto address=GetProcAddress(static_cast<HMODULE>(module),name);
  nexWindowsDllError=address?"":"Windows DLL export unavailable: "+std::to_string(GetLastError());return reinterpret_cast<void*>(address);
}
inline const char *dlerror(){static thread_local std::string last;last=std::move(nexWindowsDllError);nexWindowsDllError.clear();return last.empty()?nullptr:last.c_str();}
struct Dl_info {const char *dli_fname=nullptr;void *dli_fbase=nullptr;const char *dli_sname=nullptr;void *dli_saddr=nullptr;};
inline int dladdr(const void *address,Dl_info *info){
  HMODULE module=nullptr;
  if(!address||!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,
      reinterpret_cast<LPCWSTR>(address),&module))return 0;
  std::vector<wchar_t> name(32768);auto count=GetModuleFileNameW(module,name.data(),DWORD(name.size()));
  if(!count||count==name.size())return 0;
  static thread_local std::string path;path=nexrt::platform::utf8(std::wstring_view(name.data(),count));
  info->dli_fname=path.c_str();info->dli_fbase=module;return 1;
}
#endif
