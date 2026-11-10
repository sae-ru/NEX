#include "nex_json.h"
#include "third_party/json.hpp"
#include <functional>
#include <set>

namespace nexrt {
namespace {
using JSON=nlohmann::ordered_json;
constexpr size_t maxBytes=1024*1024,maxDepth=64,maxItems=10000,maxNodes=100000;
void reject(const std::string &message){throw DataError("E_JSON",message);}
JSON parse(const std::string &text,bool details=false){
  if(text.size()>maxBytes)reject("JSON input exceeds byte limit");
  try{
  std::vector<std::set<std::string>> names;size_t events=0;
  auto callback=[&](int depth,JSON::parse_event_t event,JSON &value){
    if(size_t(depth)>maxDepth||++events>maxNodes*3)reject("JSON input exceeds depth/node limit");
    if(event==JSON::parse_event_t::object_start)names.emplace_back();
    if(event==JSON::parse_event_t::object_end)names.pop_back();
    if(event==JSON::parse_event_t::key&&!names.back().insert(value.get<std::string>()).second)reject("duplicate JSON object key");
    return true;
  };
  return JSON::parse(text,callback);
  }catch(const DataError &){if(details)throw;reject("invalid JSON text or wire schema");}
  catch(const JSON::exception &){reject("invalid JSON text or wire schema");}
  return nullptr;
}
std::string encode(const Value &value,size_t depth,size_t &nodes){
  if(depth>maxDepth||++nodes>maxNodes)reject("JSON value exceeds depth/node limit");
  if(value.tag==Value::Integer)return nexrt::quoted(std::to_string(value.scalar));
  if(value.tag==Value::Boolean)return value.scalar?"true":"false";
  if(value.tag==Value::Floating)return formatFloat(value.floating());
  const auto &d=*value.object;
  if(d.kind==Data::Closure)reject("function values cannot cross the JSON boundary");
  if(d.kind==Data::External)reject("external resources cannot cross the JSON boundary");
  if(d.kind==Data::File)reject("file resources cannot cross the JSON boundary");
  if(d.kind==Data::String)return nexrt::quoted(d.text);
  if(d.kind==Data::Bytes){
    const auto &buffer=byteBuffer(value.object);
    if(uint64_t(buffer.length())>((maxBytes-2)/4)*3)reject("JSON value exceeds byte limit");
    return nexrt::quoted(buffer.base64());
  }
  if(d.kind==Data::Success)return "{\"ok\":"+encode(d.values[0],depth+1,nodes)+"}";
  if(d.kind==Data::Failure)return "{\"error\":{\"code\":"+nexrt::quoted(d.text)+",\"message\":"+nexrt::quoted(d.values[0].object->text)+"}}";
  if(d.kind==Data::Enum){
    if(depth+1>maxDepth)reject("JSON enum wrapper exceeds depth limit");
    auto separator=d.text.rfind("::");if(separator==std::string::npos)reject("invalid enum runtime tag");
    if(d.values.size()>maxItems)reject("JSON enum exceeds item limit");std::string fields="{";
    for(size_t i=0;i<d.values.size();++i){if(i)fields+=",";fields+=nexrt::quoted(d.names.at(i))+":"+encode(d.values[i],depth+2,nodes);if(fields.size()>maxBytes)reject("JSON value exceeds byte limit");}
    return "{\"case\":"+nexrt::quoted(d.text.substr(separator+2))+",\"fields\":"+fields+"}}";
  }
  if(d.values.size()>maxItems)reject("JSON collection exceeds item limit");
  std::string out=d.kind==Data::List?"[":"{";
  for(size_t i=0;i<d.values.size();++i){if(i)out+=",";if(d.kind==Data::Record)out+=nexrt::quoted(d.names[i])+":";out+=encode(d.values[i],depth+1,nodes);if(out.size()>maxBytes)reject("JSON value exceeds byte limit");}
  return out+(d.kind==Data::List?"]":"}");
}
Value decode(const JSON &value,const JSON &type,const JSON &records,const JSON &enums,size_t depth,size_t &nodes){
  if(depth>maxDepth||++nodes>maxNodes)reject("JSON value exceeds depth/node limit");
  if(type=="i64"){
    if(!value.is_string())reject("i64 requires a canonical decimal JSON string");
    const auto &text=value.get_ref<const std::string&>();size_t first=text.starts_with('-')?1:0;
    if(first==text.size()||(text[first]=='0'&&(first||text.size()!=1))||!std::all_of(text.begin()+first,text.end(),[](char c){return c>='0'&&c<='9';}))reject("i64 requires a canonical decimal JSON string");
    int64_t integer=0;auto parsed=std::from_chars(text.data(),text.data()+text.size(),integer);
    if(parsed.ec!=std::errc()||parsed.ptr!=text.data()+text.size())reject("JSON integer is outside i64 range");return Value(integer);
  }
  if(type=="bool"){if(!value.is_boolean())reject("expected JSON boolean");return Value(value.get<bool>(),true);}
  if(type=="f64"){
    if(!value.is_number())reject("f64 requires a finite JSON number");
    auto floating=value.get<double>();if(!std::isfinite(floating))reject("f64 requires a finite JSON number");
    return Value::floating(floating);
  }
  if(type=="str"){if(!value.is_string())reject("expected JSON string");return Value(string(value.get<std::string>()));}
  if(type=="bytes"){
    if(!value.is_string())reject("bytes require a canonical base64 JSON string");
    try{return Value(bytes(ByteBuffer::fromBase64(value.get_ref<const std::string&>())));}
    catch(const DataError &){reject("bytes require a canonical base64 JSON string");}
  }
  if(type.contains("list")){
    if(!value.is_array()||value.size()>maxItems)reject("expected JSON array within item limit");
    auto data=std::make_shared<Data>(Data::List);for(const auto &item:value)data->values.push_back(decode(item,type.at("list"),records,enums,depth+1,nodes));return Value(data);
  }
  if(type.contains("result")){
    if(!value.is_object()||value.size()!=1)reject("expected tagged JSON result");
    if(value.contains("ok"))return success(decode(value.at("ok"),type.at("result"),records,enums,depth+1,nodes));
    if(!value.contains("error"))reject("expected ok or error result");const auto &error=value.at("error");
    if(!error.is_object()||error.size()!=2||!error.contains("code")||!error.contains("message")||!error.at("code").is_string()||!error.at("message").is_string())reject("invalid JSON error");
    return failure(error.at("code").get<std::string>(),error.at("message").get<std::string>());
  }
  if(type.contains("enum")){
    auto name=type.at("enum").get<std::string>();const auto &cases=enums.at(name);
    if(!value.is_object()||value.size()!=2||!value.contains("case")||!value.contains("fields")||!value.at("case").is_string()||!value.at("fields").is_object())reject("expected tagged JSON enum");
    const auto &tag=value.at("case");for(size_t ordinal=0;ordinal<cases.size();++ordinal){const auto &variant=cases[ordinal];if(tag!=variant.at("name"))continue;const auto &fields=variant.at("fields"),&payload=value.at("fields");
      if(payload.size()!=fields.size()||payload.size()>maxItems)reject("JSON enum has missing or unknown fields");
      auto data=std::make_shared<Data>(Data::Enum);data->text=name+"::"+tag.get<std::string>();data->ordinal=ordinal;
      for(const auto &field:fields){auto key=field.at("name").get<std::string>();if(!payload.contains(key))reject("JSON enum has missing or unknown fields");data->names.push_back(key);data->values.push_back(decode(payload.at(key),field.at("type"),records,enums,depth+2,nodes));}return Value(data);
    }
    reject("unknown JSON enum variant");
  }
  if(type.contains("record")){
    auto name=type.at("record").get<std::string>();const auto &fields=records.at(name);
    if(!value.is_object()||value.size()!=fields.size())reject("JSON record has missing or unknown fields");
    auto data=std::make_shared<Data>(Data::Record);data->text=name;
    for(const auto &field:fields){auto key=field.at("name").get<std::string>();if(!value.contains(key))reject("JSON record has missing or unknown fields");data->names.push_back(key);data->values.push_back(decode(value.at(key),field.at("type"),records,enums,depth+1,nodes));}
    return Value(data);
  }
  reject("unsupported wire type");return {};
}
}
void validateJSONText(const std::string &text){(void)parse(text,true);}
std::string encodeJSON(const Value &value){size_t nodes=0;auto text=encode(value,0,nodes);if(text.size()>maxBytes)reject("JSON value exceeds byte limit");return text;}
Value decodeJSON(const std::string &text,const std::string &schema){
  try{
    FloatEnvironment environment;
    auto contract=JSON::parse(schema);auto value=parse(text);size_t nodes=0;
    if(contract.at("schema")!="nex.wire/1"&&contract.at("schema")!="nex.wire/2")reject("unsupported wire schema");
    auto enums=contract.at("schema")=="nex.wire/2"?contract.at("enums"):JSON::object();return success(decode(value,contract.at("root"),contract.at("records"),enums,0,nodes));
  }catch(const DataError &error){return failure(error.code,error.message);}
  catch(const JSON::exception &){return failure("E_JSON","invalid JSON text or wire schema");}
}
}
