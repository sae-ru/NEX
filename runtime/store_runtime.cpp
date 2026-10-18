#include "nex_host.h"
#include "nex_io.h"
using nexrt::Handle;
extern "C" {
static Handle * impl_nex_store_get(Handle *key,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return nexrt::hostValue(line,[&]{return nexrt::storageGet(nexrt::readHandle(key).object->text);});});
}
Handle * nex_store_get(Handle *key,int64_t line){return impl_nex_store_get(key, line);}
Handle * nex_store_get_at(Handle *key,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_store_get(key, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_store_put(Handle *key,Handle *value,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return nexrt::hostValue(line,[&]{return nexrt::storagePut(nexrt::readHandle(key).object->text,nexrt::readHandle(value).object->text);});});
}
Handle * nex_store_put(Handle *key,Handle *value,int64_t line){return impl_nex_store_put(key, value, line);}
Handle * nex_store_put_at(Handle *key,Handle *value,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_store_put(key, value, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_store_remove(Handle *key,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return nexrt::hostValue(line,[&]{return nexrt::storageRemove(nexrt::readHandle(key).object->text);});});
}
Handle * nex_store_remove(Handle *key,int64_t line){return impl_nex_store_remove(key, line);}
Handle * nex_store_remove_at(Handle *key,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_store_remove(key, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_store_keys(Handle *prefix,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return nexrt::hostValue(line,[&]{return nexrt::storageKeys(nexrt::readHandle(prefix).object->text);});});
}
Handle * nex_store_keys(Handle *prefix,int64_t line){return impl_nex_store_keys(prefix, line);}
Handle * nex_store_keys_at(Handle *prefix,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_store_keys(prefix, nexrt::SourceLocation{line,nex_site});}
}
