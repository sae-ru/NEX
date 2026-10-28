#pragma once
#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
// Experimental trusted RK3588 RKNN adapter. No NEX/runtime C++ objects cross its ABI.
#include "nex_ffi_module.h"
#include "third_party/json.hpp"
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>
#include <unistd.h>

using JSON=nlohmann::json;
struct Failure:std::runtime_error {
  std::string code;
  Failure(std::string code,std::string text):std::runtime_error(std::move(text)),code(std::move(code)){}
};
struct Library {
  void *value=nullptr;
  explicit Library(const char *path,int flags=RTLD_NOW|RTLD_LOCAL){value=dlopen(path,flags);if(!value)throw Failure("E_DEVICE_UNAVAILABLE",dlerror());}
  ~Library(){if(value)dlclose(value);}
  template<class T>T symbol(const char *name){dlerror();auto p=dlsym(value,name);auto e=dlerror();if(e||!p)throw Failure("E_DEVICE_ABI",e?e:name);return reinterpret_cast<T>(p);}
  Library(const Library&)=delete;
};
void trace(const JSON &entry){
  if(auto path=std::getenv("NEX_RK_NPU_TRACE_FILE")){
    std::ofstream output(path,std::ios::app);if(!output)throw Failure("E_TRACE","cannot append private accelerator trace");
    output<<entry.dump()<<'\n';if(!output)throw Failure("E_TRACE","cannot write private accelerator trace");
  }
}
nex_ffi_status error(const nex_ffi_api_v1 *a,nex_ffi_call call,nex_ffi_ref *out,const std::string &code,const std::string &message){
  auto text=message.substr(0,2048);
  return a->make_failure(call,reinterpret_cast<const uint8_t*>(code.data()),code.size(),reinterpret_cast<const uint8_t*>(text.data()),text.size(),out);
}
#define FFI(expression) do {auto status=(expression);if(status)return status;}while(0)
std::mutex acceleratorMutex; // Explicit serialized adapter; no source concurrency claim.

