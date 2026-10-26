#include "nex_ffi_module.h"
#include "nex_task_network.h"
#include "operator_targets.h"
#include <array>
#include <climits>
#include <cstdio>
#include <cstring>
#include <limits>

namespace {
struct HostStatus {nex_ffi_status status;};
void checked(nex_ffi_status status){if(status!=NEX_FFI_OK)throw HostStatus{status};}
struct CallSlot {};
struct State {
  nexrt::ResourceDomain lifetime;
  nexrt::TaskNetworkGrant grant;
  State():lifetime(NEX_TCP_MAX_CONNECTIONS),grant(lifetime.access(),operatorTargets){}
  ~State()noexcept{
#if NEX_TCP_DIAGNOSTICS
    auto s=grant.stats();std::fprintf(stderr,"NEX_TCP_RETIRE {\"opened\":%llu,\"closed\":%llu,\"live\":%llu,\"maximum_live\":%llu}\n",static_cast<unsigned long long>(s.opened),static_cast<unsigned long long>(s.closed),static_cast<unsigned long long>(s.live),static_cast<unsigned long long>(s.maximumLive));
#endif
  }
};
State &state(){static State instance;return instance;}
void kind(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref value,uint32_t expected){uint32_t actual=0;checked(api->kind(call,value,&actual));if(actual!=expected)throw HostStatus{NEX_FFI_TYPE};}
std::vector<uint8_t> copy(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref value,size_t limit){
  uint64_t length=0;checked(api->byte_size(call,value,&length));if(length>limit)throw nexrt::DataError("E_RANGE","provider input exceeds its declared limit");
  std::vector<uint8_t> result(size_t(length),0);uint64_t copied=0;checked(api->copy_bytes(call,value,0,result.data(),length,&copied));if(copied!=length)throw HostStatus{NEX_FFI_INTERNAL};return result;
}
nex_ffi_status failure(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref *out,const std::string &code,const char *reason){
  // OS diagnostic text can follow the host locale. Preserve its bytes as ASCII
  // escapes instead of passing invalid UTF-8 into a source string builder.
  static constexpr char hex[]="0123456789abcdef";std::string message;
  for(size_t i=0;reason[i]&&message.size()<2000;++i){auto c=static_cast<unsigned char>(reason[i]);if(c>=32&&c<127)message+=char(c);else{message+="\\x";message+=hex[c>>4];message+=hex[c&15];}}
  return api->make_failure(call,reinterpret_cast<const uint8_t*>(code.data()),code.size(),reinterpret_cast<const uint8_t*>(message.data()),message.size(),out);
}
nex_ffi_status exchangeBody(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user){
  try{
    if(!api||api->abi_version!=1||api->struct_size<NEX_FFI_V1_TYPED_SIZE||count!=4||!args||!out||!user)return NEX_FFI_ARGUMENT;
    checked(api->poll(call));kind(api,call,args[0],NEX_FFI_STRING);kind(api,call,args[1],NEX_FFI_BYTES);kind(api,call,args[2],NEX_FFI_I64);kind(api,call,args[3],NEX_FFI_I64);
    uint64_t bodySize=0;checked(api->byte_size(call,args[1],&bodySize));
    if(bodySize>524288)return failure(api,call,out,"LIMIT","TCP request exceeds512KiB");
    int64_t reply=0,timeout=0;checked(api->get_i64(call,args[2],&reply));checked(api->get_i64(call,args[3],&timeout));
    if(reply<1||reply>524288||timeout<1||timeout>30000)return failure(api,call,out,"VALIDATION","invalid TCP reply limit or timeout");
    if(bodySize+uint64_t(reply)>1044480)return failure(api,call,out,"LIMIT","TCP copied request and declared reply exceed1020KiB");
    auto &owner=*static_cast<State*>(user);
    // One shared provider image can serve several request-owned IO pools.
    // Reserve its operator-selected provider-instance call capacity before copying
    // the body or opening a socket. The physical lease survives logical close
    // and stays held until inline transport settlement and result construction.
    auto slot=owner.lifetime.make<CallSlot>([](const nexrt::ResourcePermit &permit){permit.check();return std::make_unique<CallSlot>();});
    auto lease=slot.acquire();lease.check();
    auto endpoint=copy(api,call,args[0],64);auto body=copy(api,call,args[1],524288);
    nexrt::PreparedTaskTcpExchange work(owner.grant,std::string(endpoint.begin(),endpoint.end()),body,size_t(reply),unsigned(timeout));
    // Source task/ffi creates this call's fresh tokens on its IO worker. The
    // transport runs inline there; no live token is submitted to another pool.
    nexrt::TaskExternalControl control([&]{checked(api->poll(call));});
    auto operation=work.operation();auto raw=operation->run(control);auto result=work.admit(std::move(raw),control);checked(api->poll(call));
    if(!result.errorCode.empty())return failure(api,call,out,result.errorCode,result.errorMessage.c_str());
    nex_ffi_ref bytes=0;checked(api->make_bytes(call,result.bytes.data(),result.bytes.size(),&bytes));return api->make_success(call,bytes,out);
  }catch(const HostStatus &error){return error.status;}
  catch(const nexrt::DataError &error){
    // Parent poll failures are HostStatus with sticky host diagnostics, so only
    // the transport's own deadline is translated into an ordinary call result.
    if(error.code=="E_TIMEOUT")return failure(api,call,out,"E_NETWORK_TIMEOUT",error.what());
    if(error.code=="E_LIMIT")return failure(api,call,out,"E_NETWORK_LIMIT",error.what());
    if(error.code=="E_RANGE")return failure(api,call,out,"VALIDATION",error.what());
    if(error.code=="E_RESOURCE_LIMIT")return failure(api,call,out,"E_NETWORK_BUSY","TCP provider call capacity is occupied");
    if(error.code=="CAPABILITY"||error.code=="E_NETWORK")return failure(api,call,out,error.code,error.what());
    return NEX_FFI_INTERNAL;
  }catch(const std::bad_alloc &){return NEX_FFI_LIMIT;}catch(...){return NEX_FFI_INTERNAL;}
}
nex_ffi_status exchange(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void *user)noexcept{
  try{return exchangeBody(api,call,args,count,out,user);}catch(const std::bad_alloc &){return NEX_FFI_LIMIT;}catch(...){return NEX_FFI_INTERNAL;}
}
nex_ffi_status statistics(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *,uint64_t count,nex_ffi_ref *out,void *user){
  try{
    if(!api||api->abi_version!=1||api->struct_size<NEX_FFI_V1_TYPED_SIZE||count||!out||!user)return NEX_FFI_ARGUMENT;checked(api->poll(call));auto values=static_cast<State*>(user)->grant.stats();
    size_t numbers[]{values.opened,values.closed,values.live,values.maximumLive};std::array<nex_ffi_ref,4> output{};
    for(size_t i=0;i<4;++i){if(numbers[i]>size_t(INT64_MAX))return NEX_FFI_RANGE;checked(api->make_i64(call,int64_t(numbers[i]),&output[i]));}return api->make_list(call,output.data(),output.size(),out);
  }catch(const HostStatus &error){return error.status;}catch(const std::bad_alloc &){return NEX_FFI_LIMIT;}catch(...){return NEX_FFI_INTERNAL;}
}
}
extern "C" NEX_FFI_MODULE_EXPORT const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t size){
  if(abi!=1||size<NEX_FFI_V1_TYPED_SIZE)return nullptr;
  try{
    auto &owner=state();
    static const nex_ffi_export_v1 exports[]={{sizeof(nex_ffi_export_v1),0,"exchange",PIN_EXCHANGE,exchange,&owner},{sizeof(nex_ffi_export_v1),0,"statistics",PIN_STATISTICS,statistics,&owner}};
    static const nex_ffi_module_v1 module{NEX_FFI_MODULE_ABI_V1,sizeof(nex_ffi_module_v1),2,sizeof(nex_ffi_export_v1),exports};return &module;
  }catch(...){return nullptr;}
}
