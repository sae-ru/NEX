#pragma once
#ifdef _WIN32
#include "host_dlfcn.h"
#include "host_file_observers.h"
#include <string_view>
#include <filesystem>
namespace nex_test {
inline unsigned imageCount(std::string_view pattern){
  unsigned count=0;
  for(auto module:nex_test_loaded_modules()){
    wchar_t name[32768];auto size=GetModuleFileNameW(module,name,32768);
    if(!size||size>=32768)throw std::runtime_error("cannot inspect native Windows module filename");
    auto file=std::filesystem::path(std::wstring(name,size)).filename();
    auto utf8=nexrt::platform::utf8(file.wstring());
    if(utf8.find(pattern)!=std::string::npos)++count;
  }
  return count;
}
}
#endif
