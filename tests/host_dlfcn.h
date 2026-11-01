#pragma once
#ifdef _WIN32
#include "nex_platform.h"
#include <string>
#include <vector>
#include <unordered_map>
#include <psapi.h>
#ifndef RTLD_NOW
#define RTLD_NOW 0
#define RTLD_LOCAL 0
#define RTLD_GLOBAL 0
#endif
#define RTLD_DEFAULT nullptr
inline thread_local std::string nex_test_loader_error;
inline std::vector<HMODULE> nex_test_loaded_modules(){
  std::vector<HMODULE> modules(4096);DWORD bytes=0;
  if(!K32EnumProcessModules(GetCurrentProcess(),modules.data(),DWORD(modules.size()*sizeof(HMODULE)),&bytes)||bytes>modules.size()*sizeof(HMODULE))
    throw std::runtime_error("cannot inspect native Windows module mappings");
  modules.resize(bytes/sizeof(HMODULE));return modules;
}
struct Dl_info {const char *dli_fname=nullptr;void *dli_fbase=nullptr;const char *dli_sname=nullptr;void *dli_saddr=nullptr;};
inline int dladdr(const void *address,Dl_info *info){
  HMODULE module=nullptr;
  if(!address||!GetModuleHandleExW(GET_MODULE_HANDLE_EX_FLAG_FROM_ADDRESS|GET_MODULE_HANDLE_EX_FLAG_UNCHANGED_REFCOUNT,reinterpret_cast<LPCWSTR>(address),&module))return 0;
  wchar_t path[32768];auto size=GetModuleFileNameW(module,path,32768);if(!size||size>=32768)return 0;
  thread_local std::unordered_map<HMODULE,std::string> names;auto &name=names[module];auto current=nexrt::platform::utf8(std::wstring(path,size));if(name!=current)name=std::move(current);
  *info={name.c_str(),module,nullptr,nullptr};return 1;
}
inline void *dlopen(const char *path,int){
  nex_test_loader_error.clear();auto wide=nexrt::platform::wide(path);
  auto module=LoadLibraryExW(wide.c_str(),nullptr,LOAD_LIBRARY_SEARCH_DLL_LOAD_DIR|LOAD_LIBRARY_SEARCH_SYSTEM32);
  if(!module)nex_test_loader_error="LoadLibraryExW: "+std::to_string(GetLastError());
  return module;
}
inline void *dlsym(void *module,const char *name){
  nex_test_loader_error.clear();FARPROC address=nullptr;
  if(module)address=GetProcAddress(static_cast<HMODULE>(module),name);
  else for(auto image:nex_test_loaded_modules())if(auto candidate=GetProcAddress(image,name)){
    if(address&&address!=candidate){nex_test_loader_error="ambiguous native Windows export";return nullptr;}
    address=candidate;
  }
  if(!address)nex_test_loader_error="GetProcAddress: "+std::to_string(GetLastError());
  return reinterpret_cast<void*>(address);
}
inline int dlclose(void *module){return FreeLibrary(static_cast<HMODULE>(module))?0:-1;}
inline const char *dlerror(){return nex_test_loader_error.empty()?nullptr:nex_test_loader_error.c_str();}
#else
#include <dlfcn.h>
#endif
