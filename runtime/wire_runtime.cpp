#include "nex_host.h"
#include "nex_json.h"
using nexrt::Handle;
extern "C" {
static Handle * impl_nex_encode_json_i64(int64_t value,int64_t tag,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return nexrt::hostValue(line,[&]{return nexrt::Value(nexrt::string(nexrt::encodeJSON(nexrt::Value::taggedScalar(value,tag))));});});
}
Handle * nex_encode_json_i64(int64_t value,int64_t tag,int64_t line){return impl_nex_encode_json_i64(value, tag, line);}
Handle * nex_encode_json_i64_at(int64_t value,int64_t tag,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_encode_json_i64(value, tag, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_encode_json_heap(Handle *value,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return nexrt::hostValue(line,[&]{return nexrt::Value(nexrt::string(nexrt::encodeJSON(nexrt::readHandle(value))));});});
}
Handle * nex_encode_json_heap(Handle *value,int64_t line){return impl_nex_encode_json_heap(value, line);}
Handle * nex_encode_json_heap_at(Handle *value,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_encode_json_heap(value, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_decode_json(Handle *value,const char *schema,int64_t size,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return nexrt::hostValue(line,[&]{return nexrt::decodeJSON(nexrt::readHandle(value).object->text,std::string(schema,size));});});
}
Handle * nex_decode_json(Handle *value,const char *schema,int64_t size,int64_t line){return impl_nex_decode_json(value, schema, size, line);}
Handle * nex_decode_json_at(Handle *value,const char *schema,int64_t size,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_decode_json(value, schema, size, nexrt::SourceLocation{line,nex_site});}
}
