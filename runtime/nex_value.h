#pragma once
// Shared data primitives; evaluation and generated control flow remain independent.
#include <cstdint>
#include <string>
#include <vector>
#include <memory>
#include <stdexcept>
#include <limits>
#include <charconv>
#include <atomic>
#include "nex_profile.h"
#include "nex_float.h"
#include "nex_bytes.h"
#include "nex_file_resource.h"

namespace nexrt {
struct Data;
struct Value {
  enum Tag { Integer, Boolean, Object, Floating } tag = Integer;
  int64_t scalar = 0;
  std::shared_ptr<Data> object;
  Value()=default;
  Value(int64_t v,bool boolean=false):tag(boolean?Boolean:Integer),scalar(v){}
  static Value floating(double value){Value result;result.tag=Floating;result.scalar=floatBits(value);return result;}
  static Value taggedScalar(int64_t value,int64_t tag){
    if(tag==2)return floating(floatValue(value));
    if(tag!=0&&tag!=1)throw DataError("E_RUNTIME","invalid scalar tag");
    return Value(value,tag==1);
  }
  double floating()const{return floatValue(scalar);}
  explicit Value(std::shared_ptr<Data> v):tag(Object),object(std::move(v)){}
};
inline std::atomic<int64_t> liveObjects{0};
struct Data {
  enum Kind { String, List, Record, Success, Failure, Enum, Closure, Bytes, File, TaskScope, Task, Channel } kind;
  int64_t ordinal=0;
  std::string text;
  std::vector<Value> values;
  std::vector<std::string> names;
  void *code=nullptr;
  const void *taskCode=nullptr;
private:
  friend struct ByteData;
  friend struct FileData;
  friend struct TaskData;
  Data(Kind kind,size_t allocatedSize):kind(kind){profileAllocate(this,allocatedSize,1);++liveObjects;}
  static Kind copyKind(const Data &other){
    if(other.kind==Bytes||other.kind==File||other.kind==TaskScope||other.kind==Task||other.kind==Channel)throw DataError("E_RUNTIME","owned payloads cannot be copied as base Data");
    return other.kind;
  }
public:
  explicit Data(Kind kind):Data(kind,sizeof(Data)){
    if(kind==Bytes||kind==File||kind==TaskScope||kind==Task||kind==Channel)throw DataError("E_RUNTIME","value requires an owned payload");
  }
  Data(const Data &other):kind(copyKind(other)),ordinal(other.ordinal),text(other.text),values(other.values),names(other.names),code(other.code),taskCode(other.taskCode){profileAllocate(this,sizeof(Data),1);++liveObjects;}
  Data &operator=(const Data&)=delete;
  ~Data(){profileFree(this);--liveObjects;}
};
// The shared-pointer control block retains ByteData's real destructor. Existing
// string/list/record layouts do not pay for an unused binary payload or vtable.
struct ByteData final : Data {
  const ByteBuffer buffer;
  explicit ByteData(ByteBuffer buffer):Data(Bytes,sizeof(ByteData)),buffer(std::move(buffer)){}
  static ByteBuffer fromList(const std::vector<Value> &values){
    ByteBuffer::sizeAllowed(values.size());std::vector<uint8_t> storage;storage.reserve(values.size());
    for(const auto &value:values){
      if(value.tag!=Value::Integer)throw DataError("E_RUNTIME","byte construction requires an i64 list");
      storage.push_back(ByteBuffer::byte(value.scalar));
    }
    return ByteBuffer::owned(std::move(storage));
  }
};
inline const ByteBuffer &byteBuffer(const std::shared_ptr<Data> &data){
  if(!data||data->kind!=Data::Bytes)throw DataError("E_RUNTIME","expected an immutable byte value");
  return static_cast<const ByteData&>(*data).buffer;
}
inline std::shared_ptr<Data> bytes(ByteBuffer buffer){return std::make_shared<ByteData>(std::move(buffer));}
// The shared-pointer control block retains the complete FileData destructor;
// ordinary values keep the same base layout and never contain an unused owner.
struct FileData final : Data {
  const FileResource resource;
  const uint64_t diagnosticIdentity;
  explicit FileData(FileResource resource,uint64_t diagnosticIdentity=0):Data(File,sizeof(FileData)),resource(std::move(resource)),diagnosticIdentity(diagnosticIdentity){}
};
inline const FileResource &fileResource(const std::shared_ptr<Data> &data){
  if(!data||data->kind!=Data::File)throw DataError("E_RUNTIME","expected a file resource value");
  if(static_cast<const FileData&>(*data).diagnosticIdentity)throw DataError("E_RUNTIME","debug file values cannot authorize IO");
  return static_cast<const FileData&>(*data).resource;
}
inline std::shared_ptr<Data> fileValue(FileResource resource){return std::make_shared<FileData>(std::move(resource));}
inline std::shared_ptr<Data> diagnosticFile(uint64_t identity){
  if(!identity)throw DataError("E_DEBUG_VALUE","file debug identity must be nonzero");
  return std::make_shared<FileData>(FileResource(),identity);
}
inline uint64_t fileIdentity(const std::shared_ptr<Data> &data){
  if(!data||data->kind!=Data::File)throw DataError("E_RUNTIME","expected a file resource value");
  const auto &value=static_cast<const FileData&>(*data);return value.diagnosticIdentity?value.diagnosticIdentity:value.resource.identity();
}
inline std::vector<size_t> unicodeOffsets(const std::string &text,bool collect=true) {
  std::vector<size_t> offsets;
  for(size_t i=0;i<text.size();) {
    if(collect)offsets.push_back(i);auto first=static_cast<unsigned char>(text[i]);
    unsigned n=first<0x80?1:(first>=0xc2&&first<=0xdf)?2:(first>=0xe0&&first<=0xef)?3:(first>=0xf0&&first<=0xf4)?4:0;
    if(!n||n>text.size()-i)throw DataError("E_UTF8","invalid UTF-8 string",i);
    uint32_t code=first & (n==1?0x7f:n==2?0x1f:n==3?0x0f:0x07);
    for(unsigned j=1;j<n;++j){auto c=static_cast<unsigned char>(text[i+j]);if((c&0xc0)!=0x80)throw DataError("E_UTF8","invalid UTF-8 string",i+j);code=(code<<6)|(c&0x3f);}
    if((n==2&&code<0x80)||(n==3&&code<0x800)||(n==4&&code<0x10000)||code>0x10ffff||(code>=0xd800&&code<=0xdfff))throw DataError("E_UTF8","invalid Unicode scalar",i);
    i+=n;
  }
  if(collect)offsets.push_back(text.size());return offsets;
}
inline std::shared_ptr<Data> string(std::string text) {
  unicodeOffsets(text,false);auto d=std::make_shared<Data>(Data::String);d->text=std::move(text);return d;
}
inline Value success(Value value){auto d=std::make_shared<Data>(Data::Success);d->values.push_back(std::move(value));return Value(d);}
inline Value failure(std::string code,std::string message){
  auto d=std::make_shared<Data>(Data::Failure);d->text=std::move(code);d->values.emplace_back(string(std::move(message)));return Value(d);
}
inline Value bytesFromIntegers(const Value &list){
  if(list.tag!=Value::Object||!list.object||list.object->kind!=Data::List)
    throw DataError("E_RUNTIME","byte construction requires an i64 list");
  try{return success(Value(bytes(ByteData::fromList(list.object->values))));}
  catch(const DataError &error){if(error.code!="E_RANGE")throw;return failure(error.code,error.what());}
}
inline std::shared_ptr<Data> utf8Bytes(const std::string &text){
  unicodeOffsets(text,false);
  return bytes(ByteBuffer::copy({reinterpret_cast<const uint8_t*>(text.data()),text.size()}));
}
inline Value decodeUTF8(const ByteBuffer &buffer){
  try{
    auto view=buffer.view();std::string text;
    if(!view.empty())text.assign(reinterpret_cast<const char*>(view.data()),view.size());
    return success(Value(string(std::move(text))));
  }catch(const DataError &error){if(error.code!="E_UTF8")throw;return failure(error.code,error.what());}
}
inline Value decodeBase64(const std::string &text){
  try{return success(Value(bytes(ByteBuffer::fromBase64(text))));}
  catch(const DataError &error){if(error.code!="E_BASE64")throw;return failure(error.code,error.what());}
}
inline bool isSuccess(const Value &value){return value.object->kind==Data::Success;}
inline Value unwrap(const Value &value){
  if(!isSuccess(value))throw DataError("E_RESULT",value.object->text+": "+value.object->values[0].object->text);
  return value.object->values[0];
}
inline std::string decodeLiteral(const std::string &token) {
  if(token.size()<2||token.front()!='"'||token.back()!='"')throw DataError("E_STRING","invalid quoted literal");
  unicodeOffsets(token,false);std::string out;
  for(size_t i=1;i+1<token.size();++i){
    auto c=static_cast<unsigned char>(token[i]);
    if(c!='\\'){if(c<0x20||c=='"')throw DataError("E_STRING","unescaped character in string literal");out+=char(c);continue;}
    if(++i+1>=token.size())throw DataError("E_STRING","incomplete string escape");
    switch(token[i]){
    case '"':out+='"';break;case '\\':out+='\\';break;case '/':out+='/';break;
    case 'b':out+='\b';break;case 'f':out+='\f';break;case 'n':out+='\n';break;case 'r':out+='\r';break;case 't':out+='\t';break;
    case 'u':{
      auto hex=[&](){
        uint32_t code=0;
        for(unsigned n=0;n<4;++n){
          if(++i+1>=token.size())throw DataError("E_STRING","incomplete Unicode escape");
          char h=token[i];unsigned digit=h>='0'&&h<='9'?h-'0':h>='a'&&h<='f'?h-'a'+10:h>='A'&&h<='F'?h-'A'+10:16;
          if(digit==16)throw DataError("E_STRING","invalid Unicode escape");code=(code<<4)|digit;
        }
        return code;
      };
      uint32_t code=hex();
      if(code>=0xd800&&code<=0xdbff){
        if(i+2>=token.size()-1||token[i+1]!='\\'||token[i+2]!='u')throw DataError("E_STRING","unpaired high surrogate");
        i+=2;auto low=hex();if(low<0xdc00||low>0xdfff)throw DataError("E_STRING","invalid low surrogate");code=0x10000+((code-0xd800)<<10)+(low-0xdc00);
      }else if(code>=0xdc00&&code<=0xdfff)throw DataError("E_STRING","unpaired low surrogate");
      if(code<0x80)out+=char(code);
      else if(code<0x800){out+=char(0xc0|(code>>6));out+=char(0x80|(code&0x3f));}
      else if(code<0x10000){out+=char(0xe0|(code>>12));out+=char(0x80|((code>>6)&0x3f));out+=char(0x80|(code&0x3f));}
      else{out+=char(0xf0|(code>>18));out+=char(0x80|((code>>12)&0x3f));out+=char(0x80|((code>>6)&0x3f));out+=char(0x80|(code&0x3f));}
      break;
    }
    default:throw DataError("E_STRING","unknown string escape");
    }
  }
  return out;
}
inline int64_t length(const std::shared_ptr<Data> &d) {
  if(d->kind==Data::Bytes)return byteBuffer(d).length();
  return d->kind==Data::String?int64_t(unicodeOffsets(d->text).size()-1):int64_t(d->values.size());
}
inline void bounds(int64_t index,size_t size) {
  if(index<0||static_cast<uint64_t>(index)>=size)throw DataError("E_BOUNDS","index is outside collection bounds");
}
inline Value get(const std::shared_ptr<Data> &d,int64_t index) {
  if(d->kind==Data::Bytes)return Value(byteBuffer(d).at(index));
  if(d->kind==Data::String){auto offsets=unicodeOffsets(d->text);bounds(index,offsets.size()-1);return Value(string(d->text.substr(offsets[index],offsets[index+1]-offsets[index])));}
  bounds(index,d->values.size());return d->values[index];
}
inline std::shared_ptr<Data> slice(const std::shared_ptr<Data> &d,int64_t start,int64_t count) {
  if(d->kind==Data::Bytes)return bytes(byteBuffer(d).slice(start,count));
  auto offsets=unicodeOffsets(d->text);auto size=offsets.size()-1;
  if(start<0||count<0||static_cast<uint64_t>(start)>size||static_cast<uint64_t>(count)>size-static_cast<uint64_t>(start))throw DataError("E_BOUNDS","slice is outside string bounds");
  return string(d->text.substr(offsets[start],offsets[start+count]-offsets[start]));
}
inline bool equal(const Value &a,const Value &b) {
  if(a.tag!=b.tag)return false;
  if(a.tag!=Value::Object)return a.scalar==b.scalar;
  if(a.object==b.object)return true;
  const auto &x=*a.object,&y=*b.object;
  if(x.kind==Data::File||y.kind==Data::File)
    return x.kind==y.kind&&fileIdentity(a.object)==fileIdentity(b.object);
  if(x.kind==Data::Bytes||y.kind==Data::Bytes)
    return x.kind==y.kind&&byteBuffer(a.object)==byteBuffer(b.object);
  if(x.kind==Data::Closure||y.kind==Data::Closure||x.kind==Data::TaskScope||y.kind==Data::TaskScope||x.kind==Data::Task||y.kind==Data::Task||x.kind==Data::Channel||y.kind==Data::Channel)return false;
  if(x.kind!=y.kind||x.ordinal!=y.ordinal||x.text!=y.text||x.names!=y.names||x.values.size()!=y.values.size())return false;
  for(size_t i=0;i<x.values.size();++i)if(!equal(x.values[i],y.values[i]))return false;
  return true;
}
inline std::string quoted(const std::string &text) {
  static const char *hex="0123456789abcdef";std::string out="\"";
  for(unsigned char c:text){if(c=='"'||c=='\\'){out+='\\';out+=char(c);}else if(c<0x20){out+="\\u00";out+=hex[c>>4];out+=hex[c&15];}else out+=char(c);}
  return out+'"';
}
inline std::string representation(const Value &v) {
  if(v.tag==Value::Floating)return formatFloat(v.floating());
  if(v.tag==Value::Integer)return std::to_string(v.scalar);
  if(v.tag==Value::Boolean)return v.scalar?"true":"false";
  const auto &d=*v.object;
  if(d.kind==Data::Closure)return quoted("<function>");
  if(d.kind==Data::File)return quoted("<file>");
  if(d.kind==Data::TaskScope)return quoted("<task_scope>");
  if(d.kind==Data::Task)return quoted("<task>");
  if(d.kind==Data::Channel)return quoted("<channel>");
  if(d.kind==Data::String)return quoted(d.text);
  if(d.kind==Data::Bytes)return quoted(byteBuffer(v.object).base64());
  if(d.kind==Data::Success)return "{\"ok\":"+representation(d.values[0])+"}";
  if(d.kind==Data::Failure)return "{\"error\":{\"code\":"+quoted(d.text)+",\"message\":"+representation(d.values[0])+"}}";
  if(d.kind==Data::Enum){std::string fields="{";for(size_t i=0;i<d.values.size();++i){if(i)fields+=",";fields+=quoted(d.names[i])+":"+representation(d.values[i]);}return "{\"case\":"+quoted(d.text.substr(d.text.rfind("::")+2))+",\"fields\":"+fields+"}}";}
  std::string text=d.kind==Data::List?"[":"{";
  for(size_t i=0;i<d.values.size();++i){if(i)text+=",";if(d.kind==Data::Record)text+=quoted(d.names[i])+":";text+=representation(d.values[i]);}
  return text+(d.kind==Data::List?"]":"}");
}
inline std::string printable(const Value &v){return v.tag==Value::Object&&v.object->kind==Data::String?v.object->text:v.tag==Value::Object&&v.object->kind==Data::Closure?"<function>":v.tag==Value::Object&&v.object->kind==Data::File?"<file>":representation(v);}
}
