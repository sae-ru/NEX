#pragma once
#include "nex_error.h"
#include <cstdlib>
#include <limits>
#include <optional>
#include <string>
#include <string_view>
#include <vector>
#ifdef _WIN32
#ifndef NOMINMAX
#define NOMINMAX
#endif
#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>
#endif

namespace nexrt::platform {
#ifdef _WIN32
inline std::wstring wide(std::string_view text) {
  if(text.empty())return {};
  if(text.size()>size_t(std::numeric_limits<int>::max()))throw DataError("E_LIMIT","text exceeds platform conversion limit");
  auto size=MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text.data(),int(text.size()),nullptr,0);
  if(!size)throw DataError("E_UTF8","text is not valid UTF-8");
  std::wstring result(size,L'\0');
  if(MultiByteToWideChar(CP_UTF8,MB_ERR_INVALID_CHARS,text.data(),int(text.size()),result.data(),size)!=size)
    throw DataError("E_UTF8","text is not valid UTF-8");
  return result;
}
inline std::string utf8(std::wstring_view text) {
  if(text.empty())return {};
  if(text.size()>size_t(std::numeric_limits<int>::max()))throw DataError("E_LIMIT","text exceeds platform conversion limit");
  auto size=WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,text.data(),int(text.size()),nullptr,0,nullptr,nullptr);
  if(!size)throw DataError("E_UTF8","platform text is not valid Unicode");
  std::string result(size,'\0');
  if(WideCharToMultiByte(CP_UTF8,WC_ERR_INVALID_CHARS,text.data(),int(text.size()),result.data(),size,nullptr,nullptr)!=size)
    throw DataError("E_UTF8","platform text is not valid Unicode");
  return result;
}
#endif
inline std::optional<std::string> environment(const std::string &name) {
#ifdef _WIN32
  auto key=wide(name);
  // The documented Windows per-variable bound includes all practical values;
  // one bounded read also avoids a query/resize race with another host thread.
  std::vector<wchar_t> value(32768);
  SetLastError(ERROR_SUCCESS);
  auto count=GetEnvironmentVariableW(key.c_str(),value.data(),DWORD(value.size()));
  if(!count){
    auto error=GetLastError();
    if(error==ERROR_ENVVAR_NOT_FOUND)return std::nullopt;
    if(error!=ERROR_SUCCESS)throw DataError("E_ENV","cannot read process environment");
    return std::string();
  }
  if(count>=value.size())throw DataError("E_LIMIT","environment value exceeds platform limit");
  return utf8(std::wstring_view(value.data(),count));
#else
  if(auto value=std::getenv(name.c_str()))return std::string(value);
  return std::nullopt;
#endif
}
}
