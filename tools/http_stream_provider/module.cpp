#include "nex_ffi_module.h"
#include "nex_resource.h"
#include "stream.hpp"
#include "operator_targets.h"
#include <climits>
#include <cstdio>
namespace {
struct HostStatus {nex_ffi_status status;};
void checked(nex_ffi_status status){if(status!=NEX_FFI_OK)throw HostStatus{status};}
nex_ffi_ref child(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref value,uint64_t index){nex_ffi_ref result=0;checked(api->child(call,value,index,&result));return result;}
uint64_t count(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref value,uint32_t wanted,uint64_t maximum){uint32_t kind=0;checked(api->kind(call,value,&kind));if(kind!=wanted)throw HostStatus{NEX_FFI_TYPE};uint64_t size=0;checked(api->child_count(call,value,&size));if(size>maximum)throw nexrt::DataError("VALIDATION","HTTP aggregate exceeds its field limit");return size;}
std::vector<uint8_t> bytes(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref value,uint32_t wanted,uint64_t maximum){uint32_t kind=0;checked(api->kind(call,value,&kind));if(kind!=wanted)throw HostStatus{NEX_FFI_TYPE};uint64_t size=0,copied=0;checked(api->byte_size(call,value,&size));if(size>maximum)throw nexrt::DataError("VALIDATION","HTTP string or bytes exceed the field limit");std::vector<uint8_t> result(size);checked(api->copy_bytes(call,value,0,result.data(),size,&copied));if(copied!=size)throw HostStatus{NEX_FFI_INTERNAL};return result;}
std::string string(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref value,uint64_t maximum){auto data=bytes(api,call,value,NEX_FFI_STRING,maximum);return {data.begin(),data.end()};}
int64_t integer(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref value){int64_t result=0;checked(api->get_i64(call,value,&result));return result;}
nex_ffi_type typeChild(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_type value,uint64_t index){nex_ffi_type result=0;checked(api->type_child(call,value,0,index,&result));return result;}
nex_ffi_status failure(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref *out,const std::string &code,const char *reason){static constexpr char hex[]="0123456789abcdef";std::string text;for(size_t i=0;reason[i]&&text.size()<2000;++i){auto c=static_cast<unsigned char>(reason[i]);if(c>=32&&c<127)text+=char(c);else{text+="\\x";text+=hex[c>>4];text+=hex[c&15];}}return api->make_failure(call,reinterpret_cast<const uint8_t*>(code.data()),code.size(),reinterpret_cast<const uint8_t*>(text.data()),text.size(),out);}
struct Slot{};
struct State:nex_http::Context {
 nexrt::ResourceDomain lifetime{NEX_HTTP_MAX_CALLS};std::atomic<size_t> bodies{0},retired{0};
 std::atomic<size_t> readsStarted{0},readsFinished{0},activeReaders{0},maximumReaders{0};
 ~State()noexcept{
#if NEX_HTTP_DIAGNOSTICS
  std::fprintf(stderr,"NEX_HTTP_STREAM_RETIRE {\"created\":%zu,\"retired\":%zu,\"dns_live\":%zu,\"sockets_live\":%zu}\n",bodies.load(),retired.load(),live.load(),socketsLive.load());
#endif
 }
};
State &state(){static State value;return value;}
struct ReadCall {
 State &owner;
 explicit ReadCall(State &owner):owner(owner){
  owner.readsStarted.fetch_add(1);auto active=owner.activeReaders.fetch_add(1)+1;auto maximum=owner.maximumReaders.load();
  while(maximum<active&&!owner.maximumReaders.compare_exchange_weak(maximum,active)){}
#if NEX_HTTP_DIAGNOSTICS
  if(active>1)std::fprintf(stderr,"NEX_HTTP_STREAM_READ_ACTIVE {\"current\":%zu}\n",active);
#endif
 }
 ~ReadCall()noexcept{owner.activeReaders.fetch_sub(1);owner.readsFinished.fetch_add(1);}
};
struct OwnedBody {
 State &owner;nexrt::ResourceOwner<Slot> slot;std::unique_ptr<nex_http_stream::Stream> stream;
 OwnedBody(State &owner,nex_http::Request request,int64_t total,const std::function<void()> &poll):owner(owner),slot(owner.lifetime.make<Slot>([](const nexrt::ResourcePermit &permit){permit.check();return std::make_unique<Slot>();})){
  stream=std::make_unique<nex_http_stream::Stream>(owner,operatorConfig,std::move(request),total,poll);owner.bodies.fetch_add(1);
 }
 ~OwnedBody()noexcept{stream.reset();owner.retired.fetch_add(1);}
};
struct Creation {std::unique_ptr<OwnedBody> value;};
nex_ffi_status create(const nex_ffi_api_v1 *api,nex_ffi_call call,void *user,void **out)noexcept{
 try{checked(api->poll(call));auto &input=*static_cast<Creation*>(user);*out=input.value.release();return api->poll(call);}catch(const HostStatus &e){return e.status;}catch(...){return NEX_FFI_INTERNAL;}
}
void destroy(void *value)noexcept{delete static_cast<OwnedBody*>(value);}
nex_http::Request request(const nex_ffi_api_v1 *api,nex_ffi_call call,nex_ffi_ref value,int64_t &total){
 if(count(api,call,value,NEX_FFI_RECORD,9)!=9)throw HostStatus{NEX_FFI_TYPE};nex_http::Request result;
 result.authority=string(api,call,child(api,call,value,0),64);result.method=string(api,call,child(api,call,value,1),32);result.url=string(api,call,child(api,call,value,2),8192);auto list=child(api,call,value,3);auto size=count(api,call,list,NEX_FFI_LIST,64);
 for(uint64_t i=0;i<size;++i){auto entry=child(api,call,list,i);if(count(api,call,entry,NEX_FFI_RECORD,2)!=2)throw HostStatus{NEX_FFI_TYPE};result.headers.push_back({string(api,call,child(api,call,entry,0),128),bytes(api,call,child(api,call,entry,1),NEX_FFI_BYTES,8192)});}
 result.body=bytes(api,call,child(api,call,value,4),NEX_FFI_BYTES,524288);total=integer(api,call,child(api,call,value,5));result.replyLimit=65536;result.timeout=integer(api,call,child(api,call,value,6));result.redirectLimit=integer(api,call,child(api,call,value,7));result.protocol=string(api,call,child(api,call,value,8),4);return result;
}
nex_ffi_status opened(const nex_ffi_api_v1 *api,nex_ffi_call call,Creation &input,nex_ffi_ref *out){
 auto &metadata=input.value->stream->metadata;auto retained=input.value->stream->retainedBytes();nex_ffi_type resultType=0;checked(api->result_type(call,&resultType));auto recordType=typeChild(api,call,resultType,0);auto headersType=typeChild(api,call,recordType,1);auto headerType=typeChild(api,call,headersType,0);auto bodyType=typeChild(api,call,recordType,2);
 std::array<nex_ffi_ref,64> headers{};
 for(size_t i=0;i<metadata.headers.size();++i){const auto &h=metadata.headers[i];std::array<nex_ffi_ref,2> fields{};checked(api->make_string(call,reinterpret_cast<const uint8_t*>(h.name.data()),h.name.size(),&fields[0]));checked(api->make_bytes(call,h.value.data(),h.value.size(),&fields[1]));checked(api->make_nominal(call,headerType,0,fields.data(),fields.size(),&headers[i]));}
 std::array<nex_ffi_ref,5> fields{};checked(api->make_i64(call,metadata.status,&fields[0]));checked(api->make_list(call,headers.data(),metadata.headers.size(),&fields[1]));checked(api->make_string(call,reinterpret_cast<const uint8_t*>(metadata.protocol.data()),metadata.protocol.size(),&fields[3]));checked(api->make_string(call,reinterpret_cast<const uint8_t*>(metadata.url.data()),metadata.url.size(),&fields[4]));
 checked(api->resource_create(call,bodyType,retained,create,destroy,&input,&fields[2]));nex_ffi_ref record=0;checked(api->make_nominal(call,recordType,0,fields.data(),fields.size(),&record));return api->make_success(call,record,out);
}
nex_ffi_status open(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t size,nex_ffi_ref *out,void *user)noexcept{
 try{
  if(!api||api->struct_size<NEX_FFI_V1_RESOURCE_SIZE||size!=1||!args||!out||!user)return NEX_FFI_ARGUMENT;checked(api->poll(call));int64_t total=0;auto value=request(api,call,args[0],total);Creation input;input.value=std::make_unique<OwnedBody>(*static_cast<State*>(user),std::move(value),total,[&]{checked(api->poll(call));});checked(api->poll(call));return opened(api,call,input,out);
 }catch(const HostStatus &e){return e.status;}catch(const nexrt::DataError &e){return failure(api,call,out,e.code=="E_RESOURCE_LIMIT"?"E_HTTP_STREAM_BUSY":e.code,e.what());}catch(const std::bad_alloc&){return NEX_FFI_LIMIT;}catch(...){return NEX_FFI_INTERNAL;}
}
nex_ffi_status read(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *args,uint64_t size,nex_ffi_ref *out,void *)noexcept{
 try{
  if(!api||api->struct_size<NEX_FFI_V1_RESOURCE_SIZE||size!=2||!args||!out)return NEX_FFI_ARGUMENT;checked(api->poll(call));nex_ffi_type bodyType=0;checked(api->argument_type(call,0,&bodyType));void *pointer=nullptr;checked(api->resource_borrow(call,args[0],bodyType,&pointer));auto maximum=integer(api,call,args[1]);auto &body=*static_cast<OwnedBody*>(pointer);ReadCall observation(body.owner);
  try{
   auto value=body.stream->read(size_t(maximum),[&]{checked(api->poll(call));uint32_t alive=0;checked(api->resource_is_open(call,args[0],&alive));if(!alive)throw HostStatus{NEX_FFI_RESOURCE_CLOSED};});checked(api->poll(call));
   nex_ffi_type resultType=0;checked(api->result_type(call,&resultType));auto recordType=typeChild(api,call,resultType,0);std::array<nex_ffi_ref,2> fields{};checked(api->make_bytes(call,value.bytes.data(),value.bytes.size(),&fields[0]));checked(api->make_bool(call,value.done,&fields[1]));nex_ffi_ref record=0;checked(api->make_nominal(call,recordType,0,fields.data(),fields.size(),&record));return api->make_success(call,record,out);
  }catch(...){uint32_t ignored=0;(void)api->resource_close(call,args[0],&ignored);throw;}
 }catch(const HostStatus &e){return e.status;}catch(const nexrt::DataError &e){return failure(api,call,out,e.code,e.what());}catch(const std::bad_alloc&){return NEX_FFI_LIMIT;}catch(...){return NEX_FFI_INTERNAL;}
}
nex_ffi_status statistics(const nex_ffi_api_v1 *api,nex_ffi_call call,const nex_ffi_ref *,uint64_t size,nex_ffi_ref *out,void *user)noexcept{
 try{if(!api||size||!out||!user)return NEX_FFI_ARGUMENT;checked(api->poll(call));auto &s=*static_cast<State*>(user);size_t counters[]{s.opened.load(),s.closed.load(),s.live.load(),s.maximumLive.load(),s.socketsOpened.load(),s.socketsClosed.load(),s.socketsLive.load(),s.maximumSocketsLive.load(),s.bodies.load(),s.retired.load(),s.readsStarted.load(),s.readsFinished.load(),s.activeReaders.load(),s.maximumReaders.load()};std::array<nex_ffi_ref,14> values{};for(size_t i=0;i<14;++i){if(counters[i]>size_t(INT64_MAX))return NEX_FFI_RANGE;checked(api->make_i64(call,int64_t(counters[i]),&values[i]));}return api->make_list(call,values.data(),values.size(),out);}catch(const HostStatus &e){return e.status;}catch(...){return NEX_FFI_INTERNAL;}
}
}
extern "C" NEX_FFI_MODULE_EXPORT const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t size){
 if(abi!=1||size<NEX_FFI_V1_RESOURCE_SIZE)return nullptr;try{auto &owner=state();static const nex_ffi_export_v1 exports[]={{sizeof(nex_ffi_export_v1),0,"open",PIN_OPEN,open,&owner},{sizeof(nex_ffi_export_v1),0,"read",PIN_READ,read,&owner},{sizeof(nex_ffi_export_v1),0,"statistics",PIN_STATISTICS,statistics,&owner}};static const nex_ffi_module_v1 module{NEX_FFI_MODULE_ABI_V1,sizeof(nex_ffi_module_v1),3,sizeof(nex_ffi_export_v1),exports};return &module;}catch(...){return nullptr;}
}
