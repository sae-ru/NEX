#pragma once
#include <filesystem>
#include <system_error>
#ifdef _WIN32
#include "nex_platform.h"
#ifdef interface
#undef interface
#endif
#ifdef ERROR
#undef ERROR
#endif
#ifdef IGNORE
#undef IGNORE
#endif
#include <cstddef>
#include <cstring>
#include <vector>
#endif

namespace nex {
// Publish a sibling stage without exposing a missing/deleted destination.
// Existing readers retain their original file; later opens see the new bytes.
inline std::error_code replaceNativeFile(const std::filesystem::path &from,
                                         const std::filesystem::path &to) {
#ifdef _WIN32
  const auto name=std::filesystem::absolute(to).native();
  if(name.size()>32766)return std::make_error_code(std::errc::filename_too_long);
  struct RenameInfo {DWORD flags;HANDLE root;DWORD bytes;WCHAR name[1];};
  const auto size=sizeof(RenameInfo)+name.size()*sizeof(wchar_t);
  std::vector<std::byte> buffer(size);auto *info=reinterpret_cast<RenameInfo*>(buffer.data());
  info->flags=0x00000001|0x00000002|0x00000040;info->root=nullptr;
  info->bytes=DWORD(name.size()*sizeof(wchar_t));
  std::memcpy(info->name,name.data(),info->bytes);
  HANDLE file=CreateFileW(from.c_str(),DELETE,FILE_SHARE_READ|FILE_SHARE_WRITE|FILE_SHARE_DELETE,
                          nullptr,OPEN_EXISTING,FILE_FLAG_OPEN_REPARSE_POINT,nullptr);
  if(file==INVALID_HANDLE_VALUE)return {int(GetLastError()),std::system_category()};
  const BOOL renamed=SetFileInformationByHandle(file,static_cast<FILE_INFO_BY_HANDLE_CLASS>(22),info,DWORD(size));
  const DWORD error=renamed?ERROR_SUCCESS:GetLastError();CloseHandle(file);
  return error?std::error_code(int(error),std::system_category()):std::error_code{};
#else
  std::error_code error;std::filesystem::rename(from,to,error);return error;
#endif
}
}
