#pragma once
#include "llvm/Support/FileSystem.h"
#include <filesystem>
#include <string>
#ifdef __linux__
#include <dlfcn.h>
#include <sys/auxv.h>
#endif

namespace nex {
inline std::string executablePath(const char *argv0=nullptr,void *address=nullptr) {
#ifdef __linux__
  // An explicitly invoked ld.so owns /proc/self/exe. AT_PHDR belongs to the
  // main program instead, even when this helper lives in a shared library.
  // Resolve once before project commands temporarily change the working path.
  static const std::string image=[] {
    Dl_info info{};
    auto headers=getauxval(AT_PHDR);
    if(headers&&dladdr(reinterpret_cast<void*>(headers),&info)&&info.dli_fname) {
      std::error_code error;
      auto path=std::filesystem::canonical(info.dli_fname,error);
      if(!error&&std::filesystem::is_regular_file(path,error)&&!error)return path.string();
    }
    return std::string{};
  }();
  if(!image.empty())return image;
#endif
  return llvm::sys::fs::getMainExecutable(argv0,address);
}
}
