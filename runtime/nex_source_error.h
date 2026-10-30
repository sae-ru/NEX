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
  // Return an owned snapshot for handler bindings, including when the checked
  // packet view is a temporary. Aggregate payloads retain their original object.
  Value getScalar(const std::string &expected,Value::Tag tag)const{
    const auto &result=get(expected);
    if(tag==Value::Object||result.tag!=tag)
      throw DataError("E_SOURCE_TYPE","source error payload scalar kind does not match the checked handler");
    return result;
  }
  Value getObject(const std::string &expected,Data::Kind kind)const{
    const auto &result=get(expected);
    if(result.tag!=Value::Object||!result.object||result.object->kind!=kind)
      throw DataError("E_SOURCE_TYPE","source error payload object kind does not match the checked handler");
    return result;
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
// Compiler-private managed transport. The legacy representation is retained
// byte for byte; typed records append a concrete key and the original owned
// value under a distinct marker. These are not wire/JSON or foreign ABI types.
inline constexpr const char *sourceErrorRecordV1="NEX_PRIVATE_SOURCE_ERROR_V1:";
inline constexpr const char *sourceErrorRecordV2="NEX_PRIVATE_SOURCE_ERROR_V2:";
inline const Data &checkedSourceErrorRecord(const Value &value){
  if(value.tag!=Value::Object||!value.object||value.object->kind!=Data::Record)
    throw DataError("E_RUNTIME","invalid private source error");
  const auto &data=*value.object;
  bool legacy=data.text.starts_with(sourceErrorRecordV1)&&data.values.size()==2;
  bool typed=data.text.starts_with(sourceErrorRecordV2)&&data.values.size()==4;
  if(!legacy&&!typed)throw DataError("E_RUNTIME","invalid private source error");
  for(size_t index=0;index<2;++index){
    const auto &field=data.values[index];
    if(field.tag!=Value::Object||!field.object||field.object->kind!=Data::String)
      throw DataError("E_RUNTIME","invalid private source error strings");
  }
  if(typed){
    const auto &key=data.values[2];
    if(key.tag!=Value::Object||!key.object||key.object->kind!=Data::String)
      throw DataError("E_SOURCE_TYPE","invalid source error type key");
    (void)SourceErrorPayload(key.object->text,data.values[3]);
  }
  return data;
}
inline Value nativeSourceErrorRecord(const NativeSourceException &error){
  auto record=std::make_shared<Data>(Data::Record);
  record->text=(error.payload?sourceErrorRecordV2:sourceErrorRecordV1)+error.source;
  record->ordinal=error.line;
  record->values={Value(string(error.code)),Value(string(error.message))};
  if(error.payload){
    record->values.emplace_back(string(error.payload->typeKey));
    record->values.push_back(error.payload->value);
  }
  return Value(std::move(record));
}
inline NativeSourceException nativeSourceErrorException(const Value &value){
  const auto &record=checkedSourceErrorRecord(value);
  bool typed=record.values.size()==4;
  NativeSourceException error(record.values[0].object->text,record.values[1].object->text,
      record.text.substr(std::char_traits<char>::length(typed?sourceErrorRecordV2:sourceErrorRecordV1)),record.ordinal);
  if(typed)error.payload=std::make_shared<const SourceErrorPayload>(record.values[2].object->text,record.values[3]);
  return error;
}
inline bool sourceErrorRecordMatches(const Value &value,const std::string &expected){
  const auto &record=checkedSourceErrorRecord(value);
  return record.values.size()==4&&SourceErrorPayload::validKey(expected)&&record.values[2].object->text==expected;
}
inline SourceErrorPayload sourceErrorRecordPayload(const Value &value,const std::string &expected){
  const auto &record=checkedSourceErrorRecord(value);
  if(record.values.size()!=4||record.values[2].object->text!=expected)
    throw DataError("E_SOURCE_TYPE","source error payload type does not match the checked handler");
  return SourceErrorPayload(record.values[2].object->text,record.values[3]);
}
inline bool isNativeSourceException(const std::exception_ptr &error)noexcept{
  if(!error)return false;
  try{std::rethrow_exception(error);}catch(const NativeSourceException &){return true;}catch(...){return false;}
}
}
