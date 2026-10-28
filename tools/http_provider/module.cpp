#include "nex_ffi_module.h"
#include "nex_resource.h"
#include "transport.hpp"
#include "operator_targets.h"
#include <climits>
#include <cstdio>

namespace {
struct HostStatus {nex_ffi_status status;};
void checked(nex_ffi_status status){if(status!=NEX_FFI_OK)throw HostStatus{status};}
struct CallSlot {};
struct State:nex_http::Context {
 nexrt::ResourceDomain lifetime{NEX_HTTP_MAX_CALLS};
 ~State()noexcept{
#if NEX_HTTP_DIAGNOSTICS
  std::fprintf(stderr,"NEX_HTTP_RETIRE {\"dns_opened\":%zu,\"dns_closed\":%zu,\"dns_live\":%zu,\"sockets_opened\":%zu,\"sockets_closed\":%zu,\"sockets_live\":%zu}\n",opened.load(),closed.load(),live.load(),socketsOpened.load(),socketsClosed.load(),socketsLive.load());
#endif
 }
};
State &state(){static State owner;return owner;}
nex_ffi_ref child(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref value,uint64_t index){nex_ffi_ref result=0;checked(api->child(call,value,index,&result));return result;}
uint64_t count(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref value,uint32_t wanted,uint64_t maximum){uint32_t kind=0;checked(api->kind(call,value,&kind));if(kind!=wanted)throw HostStatus{NEX_FFI_TYPE};uint64_t size=0;checked(api->child_count(call,value,&size));if(size>maximum)throw nexrt::DataError("VALIDATION","HTTP aggregate exceeds its field limit");return size;}
std::vector<uint8_t> bytes(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref value,uint32_t wanted,uint64_t maximum){uint32_t kind=0;checked(api->kind(call,value,&kind));if(kind!=wanted)throw HostStatus{NEX_FFI_TYPE};uint64_t size=0,copied=0;checked(api->byte_size(call,value,&size));if(size>maximum)throw nexrt::DataError("VALIDATION","HTTP string or bytes exceed the field limit");std::vector<uint8_t> result(size);checked(api->copy_bytes(call,value,0,result.data(),size,&copied));if(copied!=size)throw HostStatus{NEX_FFI_INTERNAL};return result;}
std::string string(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref value,uint64_t maximum){auto data=bytes(api,call,value,NEX_FFI_STRING,maximum);return {data.begin(),data.end()};}
int64_t integer(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref value){int64_t result=0;checked(api->get_i64(call,value,&result));return result;}
nex_http::Request request(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref value){
 if(count(api,call,value,NEX_FFI_RECORD,9)!=9)throw HostStatus{NEX_FFI_TYPE};nex_http::Request r;
 r.authority=string(api,call,child(api,call,value,0),64);r.method=string(api,call,child(api,call,value,1),32);r.url=string(api,call,child(api,call,value,2),8192);auto headers=child(api,call,value,3);auto size=count(api,call,headers,NEX_FFI_LIST,64);
 for(uint64_t i=0;i<size;++i){auto entry=child(api,call,headers,i);if(count(api,call,entry,NEX_FFI_RECORD,2)!=2)throw HostStatus{NEX_FFI_TYPE};r.headers.push_back({string(api,call,child(api,call,entry,0),128),bytes(api,call,child(api,call,entry,1),NEX_FFI_BYTES,8192)});}
 r.body=bytes(api,call,child(api,call,value,4),NEX_FFI_BYTES,524288);r.replyLimit=integer(api,call,child(api,call,value,5));r.timeout=integer(api,call,child(api,call,value,6));r.redirectLimit=integer(api,call,child(api,call,value,7));r.protocol=string(api,call,child(api,call,value,8),4);return r;
}
nex_ffi_type typeChild(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_type value,uint64_t index){nex_ffi_type result=0;checked(api->type_child(call,value,0,index,&result));return result;}
nex_ffi_status response(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_http::Response &value,nex_ffi_ref *out){
 nex_ffi_type resultType=0;checked(api->result_type(call,&resultType));auto recordType=typeChild(api,call,resultType,0);auto headersType=typeChild(api,call,recordType,1);auto headerType=typeChild(api,call,headersType,0);std::array<nex_ffi_ref,64> headers{};
 for(size_t i=0;i<value.headers.size();++i){const auto &header=value.headers[i];std::array<nex_ffi_ref,2> fields{};checked(api->make_string(call,reinterpret_cast<const uint8_t*>(header.name.data()),header.name.size(),&fields[0]));checked(api->make_bytes(call,header.value.data(),header.value.size(),&fields[1]));checked(api->make_nominal(call,headerType,0,fields.data(),fields.size(),&headers[i]));}
 std::array<nex_ffi_ref,5> fields{};checked(api->make_i64(call,value.status,&fields[0]));checked(api->make_list(call,headers.data(),value.headers.size(),&fields[1]));checked(api->make_bytes(call,value.body.data(),value.body.size(),&fields[2]));checked(api->make_string(call,reinterpret_cast<const uint8_t*>(value.protocol.data()),value.protocol.size(),&fields[3]));checked(api->make_string(call,reinterpret_cast<const uint8_t*>(value.url.data()),value.url.size(),&fields[4]));nex_ffi_ref record=0;checked(api->make_nominal(call,recordType,0,fields.data(),fields.size(),&record));return api->make_success(call,record,out);
}
nex_ffi_status failure(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref *out,const std::string &code,const char *reason){static constexpr char hex[]="0123456789abcdef";std::string text;for(size_t i=0;reason[i]&&text.size()<2000;++i){auto c=static_cast<unsigned char>(reason[i]);if(c>=32&&c<127)text+=char(c);else{text+="\\x";text+=hex[c>>4];text+=hex[c&15];}}return api->make_failure(call,reinterpret_cast<const uint8_t*>(code.data()),code.size(),reinterpret_cast<const uint8_t*>(text.data()),text.size(),out);}
nex_ffi_status sendBody(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t size,nex_ffi_ref *out,void *user){
 try{
  if(!api||api->abi_version!=1||api->struct_size<NEX_FFI_V1_TYPED_SIZE||size!=1||!args||!out||!user)return NEX_FFI_ARGUMENT;checked(api->poll(call));auto &owner=*static_cast<State*>(user);auto slot=owner.lifetime.make<CallSlot>([](const nexrt::ResourcePermit &permit){permit.check();return std::make_unique<CallSlot>();});auto lease=slot.acquire();lease.check();
  try{auto value=request(api,call,args[0]);auto result=nex_http::execute(owner,operatorConfig,std::move(value),[&]{checked(api->poll(call));});checked(api->poll(call));return response(api,call,result,out);}
  catch(const nexrt::DataError &error){if(error.code=="VALIDATION"||error.code=="CAPABILITY"||error.code=="E_HTTP"||error.code=="E_TLS"||error.code=="E_HTTP_LIMIT"||error.code=="E_HTTP_TIMEOUT"||error.code=="E_HTTP_REDIRECT"||error.code=="E_DNS"||error.code=="E_DNS_LIMIT")return failure(api,call,out,error.code,error.what());return NEX_FFI_INTERNAL;}
 }catch(const HostStatus &error){return error.status;}catch(const nexrt::DataError &error){if(error.code=="E_RESOURCE_LIMIT")return failure(api,call,out,"E_HTTP_BUSY","HTTP provider capacity is occupied");return NEX_FFI_INTERNAL;}
}
nex_ffi_status send(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t size,nex_ffi_ref *out,void *user)noexcept{try{return sendBody(api,call,args,size,out,user);}catch(const std::bad_alloc&){return NEX_FFI_LIMIT;}catch(...){return NEX_FFI_INTERNAL;}}
nex_ffi_status statistics(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *,uint64_t size,nex_ffi_ref *out,void *user)noexcept{
 try{if(!api||api->abi_version!=1||api->struct_size<NEX_FFI_V1_TYPED_SIZE||size||!out||!user)return NEX_FFI_ARGUMENT;checked(api->poll(call));auto &s=*static_cast<State*>(user);size_t values[]{s.opened.load(),s.closed.load(),s.live.load(),s.maximumLive.load(),s.socketsOpened.load(),s.socketsClosed.load(),s.socketsLive.load(),s.maximumSocketsLive.load()};std::array<nex_ffi_ref,8> refs{};for(size_t i=0;i<8;++i){if(values[i]>size_t(INT64_MAX))return NEX_FFI_RANGE;checked(api->make_i64(call,int64_t(values[i]),&refs[i]));}return api->make_list(call,refs.data(),refs.size(),out);}catch(const HostStatus &error){return error.status;}catch(const std::bad_alloc&){return NEX_FFI_LIMIT;}catch(...){return NEX_FFI_INTERNAL;}
}
}
extern "C" NEX_FFI_MODULE_EXPORT const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t size){
 if(abi!=1||size<NEX_FFI_V1_TYPED_SIZE)return nullptr;try{auto &owner=state();static const nex_ffi_export_v1 exports[]={{sizeof(nex_ffi_export_v1),0,"send",PIN_SEND,send,&owner},{sizeof(nex_ffi_export_v1),0,"statistics",PIN_STATISTICS,statistics,&owner}};static const nex_ffi_module_v1 module{NEX_FFI_MODULE_ABI_V1,sizeof(nex_ffi_module_v1),2,sizeof(nex_ffi_export_v1),exports};return &module;}catch(...){return nullptr;}
}
