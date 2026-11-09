#include "nex_ffi_host.h"
#include "nex_ffi_types.h"
#include "nex_ffi_resources.h"
#include <algorithm>
#include <atomic>
#include <cstring>
#include <exception>
#include <map>
#include <mutex>
#include <thread>

namespace nexrt::foreign_detail {
struct Failure { nex_ffi_status status; };
[[noreturn]] void fail(nex_ffi_status status){throw Failure{status};}
void require(bool condition,nex_ffi_status status){if(!condition)fail(status);}
std::atomic<uint64_t> nextToken{1};
uint64_t token(){
  auto next=nextToken.load(std::memory_order_relaxed);
  for(;;){
    require(next!=UINT64_MAX,NEX_FFI_LIMIT);
    if(nextToken.compare_exchange_weak(next,next+1,std::memory_order_relaxed))return next;
  }
}
uint32_t kind(const Value &v){
  switch(v.tag){
  case Value::Integer:return NEX_FFI_I64;
  case Value::Floating:finiteFloat(v.floating());return NEX_FFI_F64;
  case Value::Boolean:require(v.scalar==0||v.scalar==1,NEX_FFI_RANGE);return NEX_FFI_BOOL;
  case Value::Object:break;
  default:fail(NEX_FFI_TYPE);
  }
  require(bool(v.object),NEX_FFI_TYPE);
  switch(v.object->kind){
  case Data::String:return NEX_FFI_STRING;case Data::Bytes:return NEX_FFI_BYTES;
  case Data::List:return NEX_FFI_LIST;case Data::Record:return NEX_FFI_RECORD;
  case Data::Enum:return NEX_FFI_ENUM;case Data::Success:return NEX_FFI_SUCCESS;
  case Data::Failure:return NEX_FFI_FAILURE;case Data::Closure:return NEX_FFI_FUNCTION;
  case Data::File:return NEX_FFI_FILE;
  case Data::External:return NEX_FFI_EXTERNAL_RESOURCE;
  case Data::TaskScope:case Data::Task:case Data::Channel:fail(NEX_FFI_TYPE);
  }
  fail(NEX_FFI_TYPE);
}
struct Entry { Value value;unsigned depth=0; };
struct State {
  const std::thread::id owner=std::this_thread::get_id();
  ForeignCallLimits limits;
  std::map<nex_ffi_ref,Entry> refs;
  std::shared_ptr<TypedContext> types;
  std::shared_ptr<ResourceContext> resources;
  std::vector<ExternalResourceBorrow> borrows;
  std::vector<Value> arguments;
  std::map<nex_ffi_type,size_t> typeRefs;
  std::map<size_t,nex_ffi_type> typeTokens;
  std::function<void()> poll;
  std::exception_ptr hostTrap;
  uint64_t operations=0,copiedBytes=0;
  bool polling=false;
  unsigned creating=0;
  explicit State(ForeignCallLimits limits,std::function<void()> poll):limits(limits),poll(std::move(poll)){}
  void charge(uint64_t count){require(count<=limits.copiedBytes-copiedBytes,NEX_FFI_LIMIT);copiedBytes+=count;}
  const Entry &entry(nex_ffi_ref ref) const {auto i=refs.find(ref);require(i!=refs.end(),NEX_FFI_REF);return i->second;}
  Value read(nex_ffi_ref ref) const {return entry(ref).value;}
  TypedContext &typed(){require(bool(types),NEX_FFI_TYPE);return *types;}
  nex_ffi_type typeToken(size_t index){
    typed();auto i=typeTokens.find(index);if(i!=typeTokens.end())return i->second;
    require(typeTokens.size()<4096,NEX_FFI_LIMIT);auto ref=token();typeRefs.emplace(ref,index);try{typeTokens.emplace(index,ref);}catch(...){typeRefs.erase(ref);throw;}return ref;
  }
  size_t type(nex_ffi_type ref){typed();auto i=typeRefs.find(ref);require(i!=typeRefs.end(),NEX_FFI_REF);return i->second;}
  nex_ffi_ref add(Value value,unsigned depth=0){
    (void)kind(value);require(refs.size()<limits.references&&depth<=128,NEX_FFI_LIMIT);
    auto ref=token();refs.emplace(ref,Entry{std::move(value),depth});return ref;
  }
  void hostPoll(){
    if(hostTrap)std::rethrow_exception(hostTrap);
    require(!polling,NEX_FFI_REENTRANT);
    if(!poll)return;
    polling=true;
    try{auto callback=poll;callback();polling=false;}
    catch(...){polling=false;hostTrap=std::current_exception();throw;}
  }
};
struct Registry { std::mutex mutex;std::map<nex_ffi_call,std::shared_ptr<State>> calls; };
Registry &registry(){static Registry value;return value;}
struct Registration {
  nex_ffi_call id;
  Registration(const std::shared_ptr<State> &state):id(token()){
    auto &r=registry();std::lock_guard lock(r.mutex);r.calls.emplace(id,state);
  }
  ~Registration(){
    // A concurrent wrong-thread API lookup may still retain State. Never destroy
    // its managed values or a callback target while holding the registry mutex.
    std::shared_ptr<State> retained;auto &r=registry();
    {std::lock_guard lock(r.mutex);auto i=r.calls.find(id);if(i!=r.calls.end()){retained=std::move(i->second);r.calls.erase(i);}}
    // Lookups on other threads can retain State, but never read these owner-only
    // fields. Release payloads and callback targets on the invoking thread.
    if(retained){retained->refs.clear();retained->arguments.clear();retained->borrows.clear();retained->resources.reset();retained->types.reset();retained->poll={};retained->hostTrap={};}
  }
};
template<class F> nex_ffi_status guarded(nex_ffi_call call,F body) noexcept {
  std::shared_ptr<State> state;
  try{
    auto &r=registry();{std::lock_guard lock(r.mutex);auto i=r.calls.find(call);if(i==r.calls.end())return NEX_FFI_SCOPE;state=i->second;}
    if(state->owner!=std::this_thread::get_id())return NEX_FFI_THREAD;
    if(state->hostTrap)return NEX_FFI_HOST_TRAP;
    if(state->operations==state->limits.operations)return NEX_FFI_LIMIT;
    ++state->operations;body(*state);return NEX_FFI_OK;
  }catch(const Failure &f){return state&&state->hostTrap?NEX_FFI_HOST_TRAP:f.status;}
  catch(const DataError &e){
    if(state&&state->hostTrap)return NEX_FFI_HOST_TRAP;
    if(e.code=="E_UTF8")return NEX_FFI_UTF8;
    if(e.code=="E_RANGE"||e.code=="E_FLOAT")return NEX_FFI_RANGE;
    if(e.code=="E_BOUNDS")return NEX_FFI_BOUNDS;
    if(e.code=="E_LIMIT")return NEX_FFI_LIMIT;
    if(e.code=="E_FFI_TYPE")return NEX_FFI_TYPE;
    if(e.code=="E_FFI_LIMIT")return NEX_FFI_LIMIT;
    if(e.code=="E_RESOURCE_TYPE")return NEX_FFI_TYPE;
    if(e.code=="E_RESOURCE_SCOPE")return NEX_FFI_SCOPE;
    if(e.code=="E_RESOURCE_CLOSED")return NEX_FFI_RESOURCE_CLOSED;
    if(e.code=="E_RESOURCE_LIMIT"||e.code=="E_RESOURCE_BYTES"||e.code=="E_RESOURCE_DEPENDENCY_LIMIT"||e.code=="E_RESOURCE_REGION_LIMIT")return NEX_FFI_LIMIT;
    return NEX_FFI_INTERNAL;
  }catch(const std::bad_alloc &){return state&&state->hostTrap?NEX_FFI_HOST_TRAP:NEX_FFI_LIMIT;}
  catch(...){return state&&state->hostTrap?NEX_FFI_HOST_TRAP:NEX_FFI_INTERNAL;}
}
template<class T> void output(T *pointer){require(pointer!=nullptr,NEX_FFI_ARGUMENT);}
std::span<const uint8_t> input(const uint8_t *pointer,uint64_t size){
  require(size==0||pointer!=nullptr,NEX_FFI_ARGUMENT);
  require(size<=SIZE_MAX,NEX_FFI_LIMIT);return {pointer,size_t(size)};
}
std::string importText(State &s,const uint8_t *pointer,uint64_t size){
  s.charge(size);auto view=input(pointer,size);std::string value;
  if(!view.empty())value.assign(reinterpret_cast<const char*>(view.data()),view.size());
  unicodeOffsets(value,false);return value;
}
std::span<const uint8_t> data(const Value &v){
  auto k=kind(v);require(k==NEX_FFI_STRING||k==NEX_FFI_BYTES,NEX_FFI_TYPE);
  if(k==NEX_FFI_BYTES)return byteBuffer(v.object).view();
  return {reinterpret_cast<const uint8_t*>(v.object->text.data()),v.object->text.size()};
}
std::span<const Value> children(const Value &v){
  auto k=kind(v);require(k==NEX_FFI_LIST||k==NEX_FFI_RECORD||k==NEX_FFI_ENUM||k==NEX_FFI_SUCCESS||k==NEX_FFI_FAILURE,NEX_FFI_TYPE);
  return v.object->values;
}
std::span<const uint8_t> label(const Value &v,uint64_t index){
  auto k=kind(v);require(k==NEX_FFI_RECORD||k==NEX_FFI_ENUM||k==NEX_FFI_FAILURE,NEX_FFI_TYPE);
  const std::string *text;
  if(k==NEX_FFI_RECORD){require(index<v.object->names.size(),NEX_FFI_BOUNDS);text=&v.object->names[size_t(index)];}
  else{require(index==0,NEX_FFI_BOUNDS);text=&v.object->text;}
  return {reinterpret_cast<const uint8_t*>(text->data()),text->size()};
}
void copy(State &s,std::span<const uint8_t> source,uint64_t offset,uint8_t *buffer,uint64_t capacity,uint64_t *written){
  output(written);require(offset<=source.size(),NEX_FFI_BOUNDS);
  auto count=std::min(capacity,uint64_t(source.size())-offset);
  require(count==0||buffer!=nullptr,NEX_FFI_ARGUMENT);s.charge(count);
  if(count)std::memcpy(buffer,source.data()+size_t(offset),size_t(count));
  *written=count;
}

nex_ffi_status getKind(nex_ffi_call c,nex_ffi_ref r,uint32_t *o) noexcept {return guarded(c,[&](State &s){output(o);auto v=s.read(r);*o=kind(v);});}
nex_ffi_status getI64(nex_ffi_call c,nex_ffi_ref r,int64_t *o) noexcept {return guarded(c,[&](State &s){output(o);auto v=s.read(r);require(kind(v)==NEX_FFI_I64,NEX_FFI_TYPE);*o=v.scalar;});}
nex_ffi_status getF64(nex_ffi_call c,nex_ffi_ref r,double *o) noexcept {return guarded(c,[&](State &s){output(o);auto v=s.read(r);require(kind(v)==NEX_FFI_F64,NEX_FFI_TYPE);*o=v.floating();});}
nex_ffi_status getBool(nex_ffi_call c,nex_ffi_ref r,uint32_t *o) noexcept {return guarded(c,[&](State &s){output(o);auto v=s.read(r);require(kind(v)==NEX_FFI_BOOL,NEX_FFI_TYPE);*o=uint32_t(v.scalar);});}
nex_ffi_status byteSize(nex_ffi_call c,nex_ffi_ref r,uint64_t *o) noexcept {return guarded(c,[&](State &s){output(o);auto v=s.read(r);*o=data(v).size();});}
nex_ffi_status copyBytes(nex_ffi_call c,nex_ffi_ref r,uint64_t off,uint8_t *p,uint64_t cap,uint64_t *o) noexcept {return guarded(c,[&](State &s){auto v=s.read(r);copy(s,data(v),off,p,cap,o);});}
nex_ffi_status childCount(nex_ffi_call c,nex_ffi_ref r,uint64_t *o) noexcept {return guarded(c,[&](State &s){output(o);auto v=s.read(r);*o=children(v).size();});}
nex_ffi_status child(nex_ffi_call c,nex_ffi_ref r,uint64_t i,nex_ffi_ref *o) noexcept {return guarded(c,[&](State &s){output(o);auto e=s.entry(r);auto values=children(e.value);require(i<values.size(),NEX_FFI_BOUNDS);*o=s.add(values[size_t(i)],e.depth?e.depth-1:0);});}
nex_ffi_status labelSize(nex_ffi_call c,nex_ffi_ref r,uint64_t i,uint64_t *o) noexcept {return guarded(c,[&](State &s){output(o);auto v=s.read(r);*o=label(v,i).size();});}
nex_ffi_status copyLabel(nex_ffi_call c,nex_ffi_ref r,uint64_t i,uint64_t off,uint8_t *p,uint64_t cap,uint64_t *o) noexcept {return guarded(c,[&](State &s){auto v=s.read(r);copy(s,label(v,i),off,p,cap,o);});}
nex_ffi_status identity(nex_ffi_call c,nex_ffi_ref r,uint64_t *o) noexcept {return guarded(c,[&](State &s){output(o);auto v=s.read(r);require(kind(v)==NEX_FFI_FILE,NEX_FFI_TYPE);*o=fileIdentity(v.object);});}
nex_ffi_status makeI64(nex_ffi_call c,int64_t v,nex_ffi_ref *o) noexcept {return guarded(c,[&](State &s){output(o);*o=s.add(Value(v));});}
nex_ffi_status makeF64(nex_ffi_call c,double v,nex_ffi_ref *o) noexcept {return guarded(c,[&](State &s){output(o);*o=s.add(Value::floating(v));});}
nex_ffi_status makeBool(nex_ffi_call c,uint32_t v,nex_ffi_ref *o) noexcept {return guarded(c,[&](State &s){output(o);require(v<=1,NEX_FFI_RANGE);*o=s.add(Value(int64_t(v),true));});}
nex_ffi_status makeString(nex_ffi_call c,const uint8_t *p,uint64_t n,nex_ffi_ref *o) noexcept {return guarded(c,[&](State &s){output(o);*o=s.add(Value(string(importText(s,p,n))));});}
nex_ffi_status makeBytes(nex_ffi_call c,const uint8_t *p,uint64_t n,nex_ffi_ref *o) noexcept {return guarded(c,[&](State &s){output(o);s.charge(n);*o=s.add(Value(bytes(ByteBuffer::copy(input(p,n)))));});}
nex_ffi_status makeList(nex_ffi_call c,const nex_ffi_ref *p,uint64_t n,nex_ffi_ref *o) noexcept {return guarded(c,[&](State &s){
  output(o);require(!n||p,NEX_FFI_ARGUMENT);require(n<=s.limits.references,NEX_FFI_LIMIT);s.charge(n*sizeof(Value));
  unsigned depth=1;auto value=std::make_shared<Data>(Data::List);value->values.reserve(size_t(n));
  for(uint64_t i=0;i<n;++i){auto &e=s.entry(p[i]);depth=std::max(depth,e.depth+1);value->values.push_back(e.value);}
  *o=s.add(Value(std::move(value)),depth);
});}
nex_ffi_status makeSuccess(nex_ffi_call c,nex_ffi_ref r,nex_ffi_ref *o) noexcept {return guarded(c,[&](State &s){output(o);auto e=s.entry(r);s.charge(sizeof(Value));*o=s.add(success(e.value),e.depth+1);});}
nex_ffi_status makeFailure(nex_ffi_call c,const uint8_t *code,uint64_t cn,const uint8_t *message,uint64_t mn,nex_ffi_ref *o) noexcept {return guarded(c,[&](State &s){
  output(o);auto a=importText(s,code,cn),b=importText(s,message,mn);s.charge(sizeof(Value));*o=s.add(failure(std::move(a),std::move(b)),1);
});}
nex_ffi_status retain(nex_ffi_call c,nex_ffi_ref r,nex_ffi_ref *o) noexcept {return guarded(c,[&](State &s){output(o);auto e=s.entry(r);*o=s.add(e.value,e.depth);});}
nex_ffi_status release(nex_ffi_call c,nex_ffi_ref r) noexcept {return guarded(c,[&](State &s){auto i=s.refs.find(r);require(i!=s.refs.end(),NEX_FFI_REF);s.refs.erase(i);});}
nex_ffi_status poll(nex_ffi_call c) noexcept {return guarded(c,[](State &s){s.hostPoll();});}
nex_ffi_status raiseTrap(nex_ffi_call c,const uint8_t *code,uint64_t codeSize,const uint8_t *message,uint64_t messageSize) noexcept {
  return guarded(c,[&](State &s){
    // Preserve the original request control before accepting a provider trap.
    s.hostPoll();
    require(codeSize>=3&&codeSize<=128&&messageSize<=2048,NEX_FFI_LIMIT);
    auto copiedCode=importText(s,code,codeSize),copiedMessage=importText(s,message,messageSize);
    require(copiedCode.starts_with("E_")&&std::all_of(copiedCode.begin()+2,copiedCode.end(),[](unsigned char ch){return (ch>='A'&&ch<='Z')||(ch>='0'&&ch<='9')||ch=='_';}),NEX_FFI_ARGUMENT);
    require(copiedMessage.find('\0')==std::string::npos,NEX_FFI_ARGUMENT);
    s.hostTrap=std::make_exception_ptr(DataError(std::move(copiedCode),std::move(copiedMessage)));
    std::rethrow_exception(s.hostTrap);
  });
}
nex_ffi_status argumentType(nex_ffi_call c,uint64_t i,nex_ffi_type *o) noexcept {return guarded(c,[&](State &s){output(o);*o=s.typeToken(s.typed().parameter(i));});}
nex_ffi_status resultType(nex_ffi_call c,nex_ffi_type *o) noexcept {return guarded(c,[&](State &s){output(o);*o=s.typeToken(s.typed().resultType());});}
nex_ffi_status typeKind(nex_ffi_call c,nex_ffi_type r,uint32_t *o) noexcept {return guarded(c,[&](State &s){output(o);*o=s.typed().kind(s.type(r));});}
nex_ffi_status typeChildCount(nex_ffi_call c,nex_ffi_type r,uint64_t v,uint64_t *o) noexcept {return guarded(c,[&](State &s){output(o);*o=s.typed().children(s.type(r),v);});}
nex_ffi_status typeChild(nex_ffi_call c,nex_ffi_type r,uint64_t v,uint64_t i,nex_ffi_type *o) noexcept {return guarded(c,[&](State &s){output(o);*o=s.typeToken(s.typed().child(s.type(r),v,i));});}
nex_ffi_status typeVariantCount(nex_ffi_call c,nex_ffi_type r,uint64_t *o) noexcept {return guarded(c,[&](State &s){output(o);*o=s.typed().variants(s.type(r));});}
nex_ffi_status makeNominal(nex_ffi_call c,nex_ffi_type r,uint64_t v,const nex_ffi_ref *p,uint64_t n,nex_ffi_ref *o) noexcept {return guarded(c,[&](State &s){
  output(o);auto type=s.type(r);require(!n||p,NEX_FFI_ARGUMENT);require(n<=1024,NEX_FFI_LIMIT);s.charge(s.typed().nominalBytes(type,v));
  std::vector<Value> values;values.reserve(size_t(n));unsigned depth=1;
  for(uint64_t i=0;i<n;++i){auto &e=s.entry(p[i]);values.push_back(e.value);depth=std::max(depth,e.depth+1);}
  auto result=s.typed().nominal(type,v,values,[&]{s.hostPoll();});*o=s.add(std::move(result),depth);
});}
nex_ffi_status signatureSize(nex_ffi_call c,uint64_t *o) noexcept {return guarded(c,[&](State &s){output(o);*o=s.typed().description().size();});}
nex_ffi_status copySignature(nex_ffi_call c,uint64_t off,uint8_t *p,uint64_t cap,uint64_t *o) noexcept {return guarded(c,[&](State &s){const auto &text=s.typed().description();copy(s,{reinterpret_cast<const uint8_t*>(text.data()),text.size()},off,p,cap,o);});}
extern const nex_ffi_api_v1 api;
const ExternalResource &resource(State &s,nex_ffi_ref ref){
  auto &v=s.entry(ref).value;require(kind(v)==NEX_FFI_EXTERNAL_RESOURCE,NEX_FFI_TYPE);
  const auto &r=externalResource(v.object);
  require(r.identity()&&s.typed().resourceDeclared(r.typeName(),r.typeHash()),NEX_FFI_TYPE);return r;
}
nex_ffi_status resourceCreateWithParents(nex_ffi_call c,nex_ffi_type t,uint64_t bytes,const nex_ffi_ref *parents,uint64_t parentCount,nex_ffi_resource_factory_v1 factory,nex_ffi_resource_destroy_v1 destroy,void *user,nex_ffi_ref *o)noexcept{return guarded(c,[&](State &s){
  output(o);auto type=s.type(t);auto [name,identity]=s.typed().resource(type);
  require(s.typed().resourceConstructible(type)&&bool(s.resources),NEX_FFI_TYPE);
  require(s.creating<16&&s.refs.size()+s.creating<s.limits.references,NEX_FFI_LIMIT);
  require(parentCount<=16,NEX_FFI_LIMIT);require(!parentCount||parents,NEX_FFI_ARGUMENT);
  std::vector<ExternalResource> captured;captured.reserve(size_t(parentCount));
  for(uint64_t i=0;i<parentCount;++i)captured.push_back(resource(s,parents[i]));
  s.resources->callbacks(factory,destroy);s.charge(sizeof(ExternalData));
  struct Creating {unsigned &count;explicit Creating(unsigned &n):count(n){++count;}~Creating(){--count;}} creating(s.creating);
  s.hostPoll();auto value=s.resources->create(name,identity,bytes,destroy,[&](void **object,const ResourcePermit &permit){
    permit.check();s.hostPoll();nex_ffi_status status;
    try{status=factory(&api,c,user,object);}
    catch(...){if(s.hostTrap)std::rethrow_exception(s.hostTrap);throw DataError("E_FFI_EXCEPTION","resource factory threw across its C boundary");}
    s.hostPoll();permit.check();if(status!=NEX_FFI_OK)fail(status);
  },captured);
  s.hostPoll();*o=s.add(Value(externalValue(std::move(value))));
});}
nex_ffi_status resourceCreate(nex_ffi_call c,nex_ffi_type t,uint64_t bytes,nex_ffi_resource_factory_v1 factory,nex_ffi_resource_destroy_v1 destroy,void *user,nex_ffi_ref *o)noexcept{
  return resourceCreateWithParents(c,t,bytes,nullptr,0,factory,destroy,user,o);
}
nex_ffi_status resourceBorrow(nex_ffi_call c,nex_ffi_ref r,nex_ffi_type t,void **o)noexcept{return guarded(c,[&](State &s){
  output(o);auto [name,identity]=s.typed().resource(s.type(t));
  require(bool(s.resources),NEX_FFI_TYPE);require(s.borrows.size()<s.limits.references,NEX_FFI_LIMIT);
  s.hostPoll();auto value=resource(s,r);
  require(value.typeName()==name&&value.typeHash()==identity,NEX_FFI_TYPE);
  auto lease=s.resources->borrow(value,name,identity);auto pointer=s.resources->pointer(lease,name,identity);
  // Native pointers last through this call even after release(ref), alias close,
  // request cancellation or catalogue revocation. The API grants no later use.
  s.borrows.push_back(std::move(lease));s.hostPoll();*o=pointer;
});}
nex_ffi_status resourceClose(nex_ffi_call c,nex_ffi_ref r,uint32_t *o)noexcept{return guarded(c,[&](State &s){output(o);s.hostPoll();auto value=resource(s,r);*o=value.close()?1:0;});}
nex_ffi_status resourceIsOpen(nex_ffi_call c,nex_ffi_ref r,uint32_t *o)noexcept{return guarded(c,[&](State &s){output(o);*o=resource(s,r).isOpen()?1:0;});}
nex_ffi_status resourceIdentity(nex_ffi_call c,nex_ffi_ref r,uint64_t *o)noexcept{return guarded(c,[&](State &s){output(o);*o=resource(s,r).identity();});}
const nex_ffi_api_v1 api={NEX_FFI_ABI_V1,uint32_t(sizeof(nex_ffi_api_v1)),getKind,getI64,getF64,getBool,byteSize,copyBytes,childCount,child,labelSize,copyLabel,identity,makeI64,makeF64,makeBool,makeString,makeBytes,makeList,makeSuccess,makeFailure,retain,release,poll,argumentType,resultType,typeKind,typeChildCount,typeChild,typeVariantCount,makeNominal,signatureSize,copySignature,resourceCreate,resourceBorrow,resourceClose,resourceIsOpen,resourceIdentity,resourceCreateWithParents,raiseTrap};
}

extern "C" const nex_ffi_api_v1 *nex_ffi_get_api(uint32_t abi,uint32_t minimum){
  return abi==NEX_FFI_ABI_V1&&minimum<=sizeof(nex_ffi_api_v1)?&nexrt::foreign_detail::api:nullptr;
}
namespace nexrt {
namespace {
Value invoke(nex_ffi_callback_v1 callback,std::span<const Value> arguments,void *user,std::function<void()> poll,ForeignCallLimits limits,std::shared_ptr<foreign_detail::TypedContext> types,std::shared_ptr<foreign_detail::ResourceContext> resources={}){
  if(!callback||!limits.references||limits.references>65536||!limits.copiedBytes||limits.copiedBytes>67108864||!limits.operations||limits.operations>1048576)
    throw DataError("E_FFI_CONFIG","invalid foreign callback or limits");
  if(arguments.size()>4096||arguments.size()>limits.references)throw DataError("E_FFI_LIMIT","too many foreign arguments");
  using namespace foreign_detail;
  try{
    auto state=std::make_shared<State>(limits,std::move(poll));std::vector<nex_ffi_ref> refs;refs.reserve(arguments.size());
    for(const auto &value:arguments)refs.push_back(state->add(value));
    state->types=std::move(types);state->resources=std::move(resources);if(state->types)state->arguments.assign(arguments.begin(),arguments.end());
    Registration registration(state);state->hostPoll();
    if(state->types)state->types->arguments(state->arguments,[&]{state->hostPoll();});
    nex_ffi_ref out=0;nex_ffi_status status;
    try{status=callback(&api,registration.id,refs.data(),refs.size(),&out,user);}
    catch(...){if(state->hostTrap)std::rethrow_exception(state->hostTrap);throw DataError("E_FFI_EXCEPTION","foreign callback threw across its C boundary");}
    state->hostPoll();
    if(status!=NEX_FFI_OK)throw DataError("E_FFI","foreign callback returned status "+std::to_string(status));
    if(state->types&&state->types->unitResult()){if(out)throw DataError("E_FFI_TYPE","unit foreign callback returned a value");return Value();}
    auto result=state->read(out);if(state->types)state->types->result(result,[&]{state->hostPoll();});return result;
  }catch(const Failure &f){throw DataError("E_FFI","invalid foreign value or call state (status "+std::to_string(f.status)+")");}
}
}
Value invokeForeign(nex_ffi_callback_v1 callback,std::span<const Value> arguments,void *user,std::function<void()> poll,ForeignCallLimits limits){return invoke(callback,arguments,user,std::move(poll),limits,{});}
Value invokeForeignTyped(nex_ffi_callback_v1 callback,std::span<const Value> arguments,const ForeignSignature &signature,void *user,std::function<void()> poll,ForeignCallLimits limits){return invoke(callback,arguments,user,std::move(poll),limits,std::make_shared<foreign_detail::TypedContext>(signature));}
namespace foreign_detail {
Value invokeForeignTypedResources(nex_ffi_callback_v1 callback,std::span<const Value> arguments,const ForeignSignature &signature,void *user,std::function<void()> poll,ForeignCallLimits limits,std::shared_ptr<ResourceContext> resources){return invoke(callback,arguments,user,std::move(poll),limits,std::make_shared<TypedContext>(signature),std::move(resources));}
}
}
