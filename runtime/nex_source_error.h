#pragma once
#include <cstdint>
#include <exception>
#include <memory>
#include <string>
#include <utility>
#include "nex_value.h"
namespace nexrt {
struct NativeSite;
struct SourceErrorPayload final {
  const std::string typeKey;
  const Value value;
  static bool validKey(const std::string &key)noexcept{
    if(key.size()!=64)return false;
    for(unsigned char c:key)if(!((c>='0'&&c<='9')||(c>='a'&&c<='f')))return false;
    return true;
  }
  SourceErrorPayload(std::string key,Value value):typeKey(std::move(key)),value(std::move(value)){
    if(!validKey(typeKey))throw DataError("E_SOURCE_TYPE","source error type key must be a complete SHA256 digest");
    if(this->value.tag==Value::Floating){(void)this->value.floating();return;}
    if(this->value.tag==Value::Integer)return;
    if(this->value.tag==Value::Boolean&&this->value.scalar>=0&&this->value.scalar<=1)return;
    if(this->value.tag==Value::Object&&this->value.object)return;
    throw DataError("E_SOURCE_TYPE","source error payload is not an owned source value");
  }
  bool matches(const std::string &expected)const noexcept{return validKey(expected)&&typeKey==expected;}
  const Value &get(const std::string &expected)const{
    if(!matches(expected))throw DataError("E_SOURCE_TYPE","source error payload type does not match the checked handler");
    return value;
  }
};
std::string copyNativeSourceRecord(const NativeSite *)noexcept;
// Private source payload; immutable once published as an exception/snapshot.
// Legacy errors own only copied strings/site JSON. Internal typed packets may
// additionally retain a complete owned value; delivery must still check its
// realm and owner ancestry. This C++ layout is behind the runtime-cohort pin,
// not the published task descriptor or C foreign-module ABI.
struct NativeSourceException final : std::exception {
  std::string code,message,source;int64_t line=0;
  std::shared_ptr<const SourceErrorPayload> payload;
  NativeSourceException()=default;
  NativeSourceException(std::string code,std::string message,std::string source,int64_t line,
      std::shared_ptr<const SourceErrorPayload> payload={})
    :code(std::move(code)),message(std::move(message)),source(std::move(source)),line(line),payload(std::move(payload)){}
  const char *what()const noexcept override{return message.c_str();}
};
inline bool isNativeSourceException(const std::exception_ptr &error)noexcept{
  if(!error)return false;
  try{std::rethrow_exception(error);}catch(const NativeSourceException &){return true;}catch(...){return false;}
}
}
