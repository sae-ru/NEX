#include "nex_ffi_module.h"
#include "nex_resource.h"
#include "operator_targets.h"
#include "resolver.hpp"
#include <ares.h>
#include <algorithm>
#include <array>
#include <atomic>
#include <cerrno>
#include <chrono>
#include <climits>
#include <cstdio>
#include <cstring>
#include <memory>
#include <string>
#include <vector>

namespace {
using nex_dns::Library;
using nex_dns::hostname;
struct HostStatus {nex_ffi_status status;};
void checked(nex_ffi_status status){if(status!=NEX_FFI_OK)throw HostStatus{status};}
struct CallSlot {};
struct State {
  Library library;
  nexrt::ResourceDomain lifetime{NEX_DNS_MAX_CALLS};
  std::atomic<size_t> opened{0},closed{0},live{0},maximumLive{0};
  ~State()noexcept{
#if NEX_DNS_DIAGNOSTICS
    std::fprintf(stderr,"NEX_DNS_RETIRE {\"opened\":%zu,\"closed\":%zu,\"live\":%zu,\"maximum_live\":%zu}\n",opened.load(),closed.load(),live.load(),maximumLive.load());
#endif
  }
};
State &state(){static State value;return value;}
void authorize(const std::string &authority,const std::string &name){
  for(const auto &rule:operatorAuthorities)if(rule.name==authority){
    if(rule.domain=="*"||rule.domain==name||(rule.subdomains&&name.size()>rule.domain.size()+1&&name.ends_with("."+rule.domain)))return;
    throw nexrt::DataError("CAPABILITY","hostname is outside the selected DNS authority");
  }
  throw nexrt::DataError("CAPABILITY","DNS authority is unavailable");
}
std::string string(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref value,uint64_t maximum){
  uint32_t kind=0;checked(api->kind(call,value,&kind));if(kind!=NEX_FFI_STRING)throw HostStatus{NEX_FFI_TYPE};
  uint64_t size=0,copied=0;checked(api->byte_size(call,value,&size));if(size>maximum)throw nexrt::DataError("VALIDATION","DNS string exceeds its declared limit");
  std::string result(size,'\0');checked(api->copy_bytes(call,value,0,reinterpret_cast<uint8_t*>(result.data()),size,&copied));if(copied!=size)throw HostStatus{NEX_FFI_INTERNAL};return result;
}
nex_ffi_status failure(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref *out,const std::string &code,const char *reason){
  static constexpr char hex[]="0123456789abcdef";std::string text;
  for(size_t i=0;reason[i]&&text.size()<2000;++i){auto c=static_cast<unsigned char>(reason[i]);if(c>=32&&c<127)text+=char(c);else{text+="\\x";text+=hex[c>>4];text+=hex[c&15];}}
  return api->make_failure(call,reinterpret_cast<const uint8_t*>(code.data()),code.size(),reinterpret_cast<const uint8_t*>(text.data()),text.size(),out);
}
nex_ffi_status resolveBody(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){
  try{
    if(!api||api->abi_version!=1||api->struct_size<NEX_FFI_V1_TYPED_SIZE||count!=4||!args||!out||!user)return NEX_FFI_ARGUMENT;
    checked(api->poll(call));auto &owner=*static_cast<State*>(user);
    int64_t limit=0,timeout=0;checked(api->get_i64(call,args[2],&limit));checked(api->get_i64(call,args[3],&timeout));
    if(limit<1||limit>64||timeout<1||timeout>30000)return failure(api,call,out,"VALIDATION","invalid DNS answer limit or timeout");
    auto slot=owner.lifetime.make<CallSlot>([](const nexrt::ResourcePermit &permit){permit.check();return std::make_unique<CallSlot>();});auto lease=slot.acquire();lease.check();
    // Keep the capacity lease until either successful or ordinary error values
    // have been constructed. Host failures unwind it without publishing a value.
    try{
      auto authority=string(api,call,args[0],64);auto name=hostname(string(api,call,args[1],254));authorize(authority,name);
      auto addresses=nex_dns::lookup(owner,name,size_t(limit),unsigned(timeout),operatorServers,[&]{checked(api->poll(call));});checked(api->poll(call));
      std::array<nex_ffi_ref,64> values{};
      for(size_t i=0;i<addresses.size();++i)checked(api->make_string(call,reinterpret_cast<const uint8_t*>(addresses[i].data()),addresses[i].size(),&values[i]));
      nex_ffi_ref list=0;checked(api->make_list(call,values.data(),addresses.size(),&list));return api->make_success(call,list,out);
    }catch(const nexrt::DataError &error){
      if(error.code=="CAPABILITY"||error.code=="VALIDATION"||error.code=="E_DNS"||error.code=="E_DNS_TIMEOUT"||error.code=="E_DNS_LIMIT")return failure(api,call,out,error.code,error.what());
      return NEX_FFI_INTERNAL;
    }
  }catch(const HostStatus &error){return error.status;}
  catch(const nexrt::DataError &error){
    if(error.code=="E_RESOURCE_LIMIT")return failure(api,call,out,"E_DNS_BUSY","DNS provider capacity is occupied");
    return NEX_FFI_INTERNAL;
  }catch(const std::bad_alloc &){return NEX_FFI_LIMIT;}catch(...){return NEX_FFI_INTERNAL;}
}
nex_ffi_status resolve(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user)noexcept{
  try{return resolveBody(api,call,args,count,out,user);}catch(const std::bad_alloc &){return NEX_FFI_LIMIT;}catch(...){return NEX_FFI_INTERNAL;}
}
nex_ffi_status statistics(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *,uint64_t count,nex_ffi_ref *out,void *user)noexcept{
  try{
    if(!api||api->abi_version!=1||api->struct_size<NEX_FFI_V1_TYPED_SIZE||count||!out||!user)return NEX_FFI_ARGUMENT;checked(api->poll(call));auto &s=*static_cast<State*>(user);
    size_t numbers[]{s.opened.load(),s.closed.load(),s.live.load(),s.maximumLive.load()};std::array<nex_ffi_ref,4> values{};
    for(size_t i=0;i<4;++i){if(numbers[i]>size_t(INT64_MAX))return NEX_FFI_RANGE;checked(api->make_i64(call,int64_t(numbers[i]),&values[i]));}return api->make_list(call,values.data(),values.size(),out);
  }catch(const HostStatus &error){return error.status;}catch(const std::bad_alloc &){return NEX_FFI_LIMIT;}catch(...){return NEX_FFI_INTERNAL;}
}
}
extern "C" NEX_FFI_MODULE_EXPORT const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t size){
  if(abi!=1||size<NEX_FFI_V1_TYPED_SIZE)return nullptr;
  try{auto &owner=state();static const nex_ffi_export_v1 exports[]={{sizeof(nex_ffi_export_v1),0,"lookup",PIN_LOOKUP,resolve,&owner},{sizeof(nex_ffi_export_v1),0,"statistics",PIN_STATISTICS,statistics,&owner}};static const nex_ffi_module_v1 module{NEX_FFI_MODULE_ABI_V1,sizeof(nex_ffi_module_v1),2,sizeof(nex_ffi_export_v1),exports};return &module;}catch(...){return nullptr;}
}
