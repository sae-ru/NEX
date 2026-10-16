#include "nex_host.h"
#include "nex_json.h"
using nexrt::Handle;
extern "C" {
Handle *nex_encode_json_i64(int64_t value,int64_t boolean,int64_t line){return nexrt::hostValue(line,[&]{return nexrt::Value(nexrt::string(nexrt::encodeJSON(nexrt::Value(value,boolean))));});}
Handle *nex_encode_json_heap(Handle *value,int64_t line){return nexrt::hostValue(line,[&]{return nexrt::Value(nexrt::string(nexrt::encodeJSON(nexrt::readHandle(value))));});}
Handle *nex_decode_json(Handle *value,const char *schema,int64_t size,int64_t line){return nexrt::hostValue(line,[&]{return nexrt::decodeJSON(nexrt::readHandle(value).object->text,std::string(schema,size));});}
}
