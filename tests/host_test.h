#pragma once
#ifdef _WIN32
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <winsock2.h>
#include <afunix.h>
#include "nex_host_windows.h"
#include <winternl.h>
#include <array>
#include <cstdlib>
#include <sys/stat.h>
#include <set>
#include "host_file_observers.h"
inline int setenv(const char *name,const char *value,int overwrite){
  if(!overwrite&&nexrt::platform::environment(name))return 0;
  return ::_wputenv_s(nexrt::platform::wide(name).c_str(),nexrt::platform::wide(value).c_str());
}
inline int setenv(const char *name,const wchar_t *value,int overwrite){
  return setenv(name,nexrt::platform::utf8(value).c_str(),overwrite);
}
inline int unsetenv(const char *name){return ::_wputenv_s(nexrt::platform::wide(name).c_str(),L"");}
inline int open(const wchar_t *path,int flags,...){return ::_wopen(path,flags,_S_IREAD|_S_IWRITE);}
namespace nex_test {
struct Environment {
  std::string name;std::optional<std::string> previous;
  Environment(const char *name,const std::optional<std::string> &value):name(name),previous(nexrt::platform::environment(name)){
    if(value)::setenv(name,value->c_str(),1);else ::unsetenv(name);
  }
  ~Environment(){if(previous)::setenv(name.c_str(),previous->c_str(),1);else ::unsetenv(name.c_str());}
};
inline DWORD run(const std::filesystem::path &self,const std::vector<std::string> &arguments,bool inheritStdio=false,bool ownDescendants=false){
  auto quote=[](const std::wstring &text){std::wstring out=L"\"";size_t slashes=0;
    for(auto c:text){if(c==L'\\'){++slashes;continue;}if(c==L'\"')out.append(slashes*2+1,L'\\');else out.append(slashes,L'\\');slashes=0;out+=c;}
    out.append(slashes*2,L'\\');return out+L'\"';};
  std::wstring command=quote(self.wstring());for(const auto &argument:arguments)command+=L" "+quote(nexrt::platform::wide(argument));
  STARTUPINFOW startup{};startup.cb=sizeof(startup);PROCESS_INFORMATION process{};
  // The forwarding fixture has closed its log and owns only its inherited
  // standard streams. Other callers retain the default non-inheriting launch.
  if(inheritStdio){startup.dwFlags=STARTF_USESTDHANDLES;startup.hStdInput=GetStdHandle(STD_INPUT_HANDLE);startup.hStdOutput=GetStdHandle(STD_OUTPUT_HANDLE);startup.hStdError=GetStdHandle(STD_ERROR_HANDLE);}
  nexrt::host_windows::Handle job;
  if(ownDescendants){
    job.value=CreateJobObjectW(nullptr,nullptr);JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if(!job.value||!SetInformationJobObject(job.value,JobObjectExtendedLimitInformation,&limits,sizeof(limits)))throw std::runtime_error("cannot own native fixture descendants");
  }
  if(!CreateProcessW(self.c_str(),command.data(),nullptr,nullptr,inheritStdio,CREATE_NO_WINDOW|CREATE_SUSPENDED,nullptr,nullptr,&startup,&process))throw std::runtime_error("cannot start native fixture child");
  nexrt::host_windows::Handle child(process.hProcess),thread(process.hThread);
  if((ownDescendants&&!AssignProcessToJobObject(job.value,process.hProcess))||ResumeThread(process.hThread)==DWORD(-1)){
    TerminateProcess(process.hProcess,125);WaitForSingleObject(process.hProcess,INFINITE);throw std::runtime_error("cannot supervise native fixture child");
  }
  if(WaitForSingleObject(process.hProcess,120000)!=WAIT_OBJECT_0){TerminateProcess(process.hProcess,125);WaitForSingleObject(process.hProcess,INFINITE);throw std::runtime_error("native fixture child timed out");}
  DWORD status=0;if(!GetExitCodeProcess(process.hProcess,&status))throw std::runtime_error("cannot inspect native fixture child exit");return status;
}
struct NonRegular {
  std::filesystem::path path;
  explicit NonRegular(std::filesystem::path path):path(std::filesystem::absolute(path)){
    sockaddr_un address{};address.sun_family=AF_UNIX;
    auto bound=this->path;
    struct Staged {
      std::filesystem::path directory,endpoint;
      ~Staged(){if(!endpoint.empty())DeleteFileW(endpoint.c_str());if(!directory.empty())RemoveDirectoryW(directory.c_str());}
    } staged;
    if(bound.u8string().size()>=sizeof(address.sun_path)){
      if(bound.filename().u8string().size()>=sizeof(address.sun_path))throw std::runtime_error("nonregular socket fixture name exceeds native limit");
      // Bind a genuine short endpoint on the same volume, close it, then move
      // its AF_UNIX reparse point to the requested long path. The private
      // staging directory is new; the process-wide cwd and existing ACLs stay
      // untouched, including when other fixture threads are running.
      nexrt::host_windows::PrivateSecurity security;
      SECURITY_ATTRIBUTES attributes{sizeof(attributes),&security.descriptor,FALSE};
      auto parent=bound.parent_path();
      for(;!parent.empty()&&staged.directory.empty();){
        for(unsigned attempt=0;attempt<8;++attempt){
          std::array<unsigned char,16> random{};
          if(BCryptGenRandom(nullptr,random.data(),ULONG(random.size()),BCRYPT_USE_SYSTEM_PREFERRED_RNG)<0)throw std::runtime_error("cannot name native socket fixture staging directory");
          std::string name="nex-sock-";for(auto byte:random){name+="0123456789abcdef"[byte>>4];name+="0123456789abcdef"[byte&15];}
          auto directory=parent/name,endpoint=directory/"s";
          if(endpoint.u8string().size()>=sizeof(address.sun_path))break;
          if(CreateDirectoryW(directory.c_str(),&attributes)){staged.directory=directory;staged.endpoint=endpoint;bound=endpoint;break;}
          if(GetLastError()!=ERROR_ALREADY_EXISTS&&GetLastError()!=ERROR_FILE_EXISTS)break;
        }
        auto next=parent.parent_path();if(next==parent)break;parent=std::move(next);
      }
      if(staged.directory.empty())throw std::runtime_error("cannot create bounded native socket fixture staging directory");
    }
    {
      WSADATA data{};if(WSAStartup(MAKEWORD(2,2),&data))throw std::runtime_error("cannot initialize native sockets");
      struct Finish {~Finish(){WSACleanup();}} finish;
      auto socket=::socket(AF_UNIX,SOCK_STREAM,0);if(socket==INVALID_SOCKET)throw std::runtime_error("cannot create native AF_UNIX socket");
      struct Close {SOCKET value;~Close(){closesocket(value);}} close{socket};
      auto bytes=bound.u8string();std::memcpy(address.sun_path,bytes.data(),bytes.size());
      if(::bind(socket,reinterpret_cast<const sockaddr*>(&address),sizeof(address)))throw std::runtime_error("cannot bind native nonregular socket fixture");
    }
    if(!staged.directory.empty()){
      // MoveFileW refuses to replace an existing destination. Closing the
      // socket first retains its native reparse tag without a live listener.
      if(!MoveFileW(bound.c_str(),this->path.c_str()))throw std::runtime_error("cannot move native socket fixture to its long path: "+std::to_string(GetLastError()));
      staged.endpoint.clear();
    }
  }
  ~NonRegular(){DeleteFileW(path.c_str());}
};
inline bool privateFile(const std::filesystem::path &path){
  using namespace nexrt::host_windows;
  Handle file(CreateFileW(path.c_str(),READ_CONTROL|FILE_READ_ATTRIBUTES,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,nullptr));
  auto id=identity(file.value);if(!id||id->directory)return false;
  PSECURITY_DESCRIPTOR descriptor=nullptr;PSID owner=nullptr;PACL acl=nullptr;
  if(GetSecurityInfo(file.value,SE_FILE_OBJECT,OWNER_SECURITY_INFORMATION|DACL_SECURITY_INFORMATION,&owner,nullptr,&acl,nullptr,&descriptor)!=ERROR_SUCCESS)return false;
  struct Release {PSECURITY_DESCRIPTOR value;~Release(){LocalFree(value);}} release{descriptor};
  PrivateSecurity current;auto sid=reinterpret_cast<TOKEN_USER*>(current.token.data())->User.Sid;
  SECURITY_DESCRIPTOR_CONTROL control{};DWORD revision=0;
  if(!owner||!EqualSid(owner,sid)||!acl||acl->AceCount!=1||!GetSecurityDescriptorControl(descriptor,&control,&revision)||!(control&SE_DACL_PROTECTED))return false;
  void *raw=nullptr;if(!GetAce(acl,0,&raw))return false;auto ace=static_cast<ACCESS_ALLOWED_ACE*>(raw);
  return ace->Header.AceType==ACCESS_ALLOWED_ACE_TYPE&&!(ace->Header.AceFlags&INHERITED_ACE)&&EqualSid(&ace->SidStart,sid)&&(ace->Mask&FILE_ALL_ACCESS)==FILE_ALL_ACCESS;
}

}
#endif
#ifndef _WIN32
#include <filesystem>
#include <stdexcept>
#include <sys/stat.h>
namespace nex_test {
struct NonRegular {
  std::filesystem::path path;
  explicit NonRegular(std::filesystem::path path):path(std::move(path)){
    if(::mkfifo(this->path.c_str(),0600))throw std::runtime_error("cannot create FIFO fixture");
  }
  ~NonRegular(){std::error_code ignored;std::filesystem::remove(path,ignored);}
};
inline bool privateFile(const std::filesystem::path &path){struct stat info{};return !::stat(path.c_str(),&info)&&(info.st_mode&0777)==0600;}
}
#endif
