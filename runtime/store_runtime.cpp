#include "nex_host.h"
#include "nex_io.h"
using nexrt::Handle;
extern "C" {
Handle *nex_store_get(Handle *key,int64_t line){return nexrt::hostValue(line,[&]{return nexrt::storageGet(nexrt::readHandle(key).object->text);});}
Handle *nex_store_put(Handle *key,Handle *value,int64_t line){return nexrt::hostValue(line,[&]{return nexrt::storagePut(nexrt::readHandle(key).object->text,nexrt::readHandle(value).object->text);});}
Handle *nex_store_remove(Handle *key,int64_t line){return nexrt::hostValue(line,[&]{return nexrt::storageRemove(nexrt::readHandle(key).object->text);});}
Handle *nex_store_keys(Handle *prefix,int64_t line){return nexrt::hostValue(line,[&]{return nexrt::storageKeys(nexrt::readHandle(prefix).object->text);});}
}
