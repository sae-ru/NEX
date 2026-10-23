#pragma once
#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
#include "nex_ffi_module.h"
#include "third_party/json.hpp"
#include <algorithm>
#include <bit>
#include <chrono>
#include <cmath>
#include <cstdint>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <filesystem>
#include <fstream>
#include <limits>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>
#include <unistd.h>
#include "model-config.inc"
using JSON=nlohmann::json;
struct Failure:std::runtime_error{std::string code;Failure(std::string c,std::string s):std::runtime_error(std::move(s)),code(std::move(c)){};};
struct Library{
 void *value=nullptr;
 Library(const char *path,int flags=RTLD_NOW|RTLD_LOCAL){value=dlopen(path,flags);if(!value)throw Failure("E_MODEL_UNAVAILABLE",dlerror());}
 ~Library(){if(value)dlclose(value);}
 template<class T>T symbol(const char *name){dlerror();void *p=dlsym(value,name);auto e=dlerror();if(e||!p)throw Failure("E_MODEL_ABI",e?e:name);return reinterpret_cast<T>(p);}
 Library(const Library&)=delete;
};
inline const JSON&config(){static const JSON value=JSON::parse(modelConfiguration);return value;}
inline uint32_t dtype(const JSON &port){const auto &s=port.at("dtype");if(s=="f32")return 1;if(s=="u8")return 2;if(s=="i8")return 3;if(s=="i32")return 6;throw Failure("E_MODEL_CONFIGURATION","unknown tensor dtype");}
inline uint32_t tensorBytes(const JSON &port){
 auto shape=port.at("shape").get<std::vector<int64_t>>();if(shape.empty()||shape.size()>4)throw Failure("E_MODEL_CONFIGURATION","rank outside1..4");uint32_t n=1;
 for(auto d:shape){if(d<1||d>262144||n>262144/uint32_t(d))throw Failure("E_MODEL_CONFIGURATION","tensor element bound exceeded");n*=uint32_t(d);}return n*(dtype(port)==1||dtype(port)==6?4:1);
}
inline void validateBytes(const std::vector<uint8_t>&data,const JSON &port){
 if(data.size()!=tensorBytes(port))throw Failure("E_MODEL_SIZE","tensor bytes disagree with prepared port");
 if(dtype(port)==1){static_assert(sizeof(float)==4&&std::numeric_limits<float>::is_iec559);static_assert(std::endian::native==std::endian::little);for(size_t i=0;i<data.size();i+=4){float f;std::memcpy(&f,data.data()+i,4);if(!std::isfinite(f))throw Failure("E_MODEL_NONFINITE","binary32 tensor must be finite");}}
}
inline void validateConfiguration(){
 auto precision=config().at("precision").get<std::string>();if(precision!="match-cpu"&&precision!="vendor")throw Failure("E_MODEL_CONFIGURATION","unknown explicit model precision policy");
 uint32_t total=0;
 for(auto key:{"inputs","outputs"}){const auto&ports=config().at(key);if(!ports.is_array()||ports.empty()||ports.size()>16)throw Failure("E_MODEL_CONFIGURATION","model needs1..16 ports per direction");for(const auto&p:ports){auto size=tensorBytes(p);if(size>786432-total)throw Failure("E_MODEL_CONFIGURATION","combined IO exceeds786432 bytes");total+=size;}}
}
inline void trace(const JSON &entry){if(auto name=std::getenv("NEX_MODEL_TRACE_FILE")){std::ofstream out(name,std::ios::app);if(!out)throw Failure("E_MODEL_TRACE","cannot append model trace");out<<entry.dump()<<'\n';if(!out)throw Failure("E_MODEL_TRACE","cannot write model trace");}}
inline void put32(std::ostream &out,uint32_t v){for(int i=0;i<4;++i)out.put(char(uint8_t(v>>(i*8))));}
inline uint32_t get32(const std::vector<uint8_t>&data,size_t &cursor){if(data.size()-std::min(cursor,data.size())<4)throw Failure("E_MODEL_PROTOCOL","truncated model frame");uint32_t n=0;for(int i=0;i<4;++i)n|=uint32_t(data[cursor++])<<(8*i);return n;}
inline nex_ffi_status failure(const nex_ffi_api_v1 *a,nex_ffi_call call,nex_ffi_ref *out,const std::string &code,const std::string &message){auto text=message.substr(0,2048);return a->make_failure(call,reinterpret_cast<const uint8_t*>(code.data()),code.size(),reinterpret_cast<const uint8_t*>(text.data()),text.size(),out);}
#define FFI(expression) do{auto status=(expression);if(status)return status;}while(0)
