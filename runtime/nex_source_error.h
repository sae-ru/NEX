#pragma once
#include <cstdint>
#include <exception>
#include <string>
#include <utility>
namespace nexrt {
struct NativeSite;
std::string copyNativeSourceRecord(const NativeSite *)noexcept;
// Private source payload; immutable once published as an exception/snapshot.
// It owns copied strings/site JSON and cannot retain a task/resource capability.
struct NativeSourceException final : std::exception {
  std::string code,message,source;int64_t line=0;
  NativeSourceException()=default;
  NativeSourceException(std::string code,std::string message,std::string source,int64_t line)
    :code(std::move(code)),message(std::move(message)),source(std::move(source)),line(line){}
  const char *what()const noexcept override{return message.c_str();}
};
inline bool isNativeSourceException(const std::exception_ptr &error)noexcept{
  if(!error)return false;
  try{std::rethrow_exception(error);}catch(const NativeSourceException &){return true;}catch(...){return false;}
}
}
