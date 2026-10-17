#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include "nex_host.h"
#include "nex_io.h"
#include <chrono>
#include <unordered_set>

namespace nexrt {
namespace {
thread_local RequestScope *currentRequest=nullptr;
std::atomic<int64_t> liveHandles{0};
}
struct Handle {
  std::shared_ptr<Data> data;
  RequestScope *owner=currentRequest;
  explicit Handle(std::shared_ptr<Data> data):data(std::move(data)){if(owner)owner->track(this);profileAllocate(this,sizeof(Handle),0);++liveHandles;}
  ~Handle(){profileFree(this);if(owner)owner->untrack(this);--liveHandles;}
};
struct RequestScope::Impl {
  std::unordered_set<Handle*> handles;
  uint64_t steps=0,budget;
  std::chrono::steady_clock::time_point deadline;
  std::atomic<bool> cancelled{false};
  std::function<bool()> cancellation;
};
RequestScope::RequestScope(uint64_t budget,uint64_t timeoutMs):impl(std::make_unique<Impl>()){
  if(currentRequest)throw Trap("E_CONTEXT","nested request scope is not supported",0);
  impl->budget=budget;impl->deadline=std::chrono::steady_clock::now()+std::chrono::milliseconds(timeoutMs);currentRequest=this;
}
RequestScope::~RequestScope(){profileUnwind();while(!impl->handles.empty())delete *impl->handles.begin();currentRequest=nullptr;}
void RequestScope::track(Handle *p){impl->handles.insert(p);}
void RequestScope::untrack(Handle *p){impl->handles.erase(p);}
void RequestScope::cancel(){impl->cancelled=true;}
void RequestScope::setCancellation(std::function<bool()> check){impl->cancellation=std::move(check);}
void RequestScope::poll(int64_t line,bool forceCancellation){
  if((forceCancellation||(impl->steps%64)==0)&&impl->cancellation&&impl->cancellation())impl->cancelled=true;
  if(impl->cancelled)throw Trap("E_CANCELLED","request was cancelled",line);
  if(++impl->steps>impl->budget)throw Trap("E_LIMIT","request execution budget exceeded",line);
  if(std::chrono::steady_clock::now()>=impl->deadline)throw Trap("E_TIMEOUT","request deadline exceeded",line);
}
Handle *makeHandle(const Value &value){if(value.tag!=Value::Object)throw DataError("E_RUNTIME","host handle requires an object");return new Handle(value.object);}
Value readHandle(const Handle *handle){return Value(handle->data);}
[[noreturn]] void runtimeFail(const char *code,const char *message,int64_t line){
  profileUnwind();
  if(currentRequest)throw Trap(code,message,line);
  std::fflush(stdout);std::fprintf(stderr,"%s: %s at source line %lld\n",code,message,static_cast<long long>(line));std::exit(70);
}
}
using nexrt::Handle;
namespace {
[[noreturn]] void fail(const char *code,const char *message,int64_t line) {
  nexrt::runtimeFail(code,message,line);
}
template<class F> auto guarded(int64_t line,F operation)->decltype(operation()) {
  try{return operation();}
  catch(const nexrt::Trap &){throw;}
  catch(const nexrt::DataError &e){fail(e.code.c_str(),e.what(),line);}
  catch(const std::bad_alloc &){fail("E_MEMORY","allocation failed",line);}
  catch(const std::exception &e){fail("E_RUNTIME",e.what(),line);}
}
Handle *owned(std::shared_ptr<nexrt::Data> data){return new Handle(std::move(data));}
Handle *updated(Handle *list,int64_t index,nexrt::Value value,int64_t mode) {
  auto data=std::make_shared<nexrt::Data>(*list->data);
  if(mode){nexrt::bounds(index,data->values.size());data->values[index]=std::move(value);}
  else data->values.push_back(std::move(value));
  return owned(data);
}
}
extern "C" {
int64_t nex_add(int64_t a,int64_t b,int64_t line){int64_t r;if(__builtin_add_overflow(a,b,&r))fail("E_OVERFLOW","i64 arithmetic overflow",line);return r;}
int64_t nex_sub(int64_t a,int64_t b,int64_t line){int64_t r;if(__builtin_sub_overflow(a,b,&r))fail("E_OVERFLOW","i64 arithmetic overflow",line);return r;}
int64_t nex_mul(int64_t a,int64_t b,int64_t line){int64_t r;if(__builtin_mul_overflow(a,b,&r))fail("E_OVERFLOW","i64 arithmetic overflow",line);return r;}
int64_t nex_div(int64_t a,int64_t b,int64_t line){if(!b)fail("E_DIV_ZERO","division by zero",line);if(a==std::numeric_limits<int64_t>::min()&&b==-1)fail("E_OVERFLOW","i64 arithmetic overflow",line);return a/b;}
int64_t nex_mod(int64_t a,int64_t b,int64_t line){if(!b)fail("E_DIV_ZERO","division by zero",line);if(a==std::numeric_limits<int64_t>::min()&&b==-1)return 0;return a%b;}
int64_t nex_neg(int64_t a,int64_t line){return nex_sub(0,a,line);}
void nex_print_i64(int64_t a){std::printf("%lld\n",static_cast<long long>(a));}
void nex_print_bool(int64_t a){std::puts(a?"true":"false");}
void nex_assert(int64_t a,int64_t line){if(!a)fail("E_ASSERT","assertion failed",line);}
Handle *nex_retain(Handle *p){return guarded(0,[&]{return p?owned(p->data):nullptr;});}
void nex_release(Handle *p){delete p;}
Handle *nex_string_new(const char *text,int64_t size,int64_t line){return guarded(line,[&]{return owned(nexrt::string(std::string(text,size)));});}
Handle *nex_list_new(){return guarded(0,[]{return owned(std::make_shared<nexrt::Data>(nexrt::Data::List));});}
Handle *nex_record_new(int64_t count){return guarded(0,[&]{auto d=std::make_shared<nexrt::Data>(nexrt::Data::Record);d->values.resize(count);d->names.resize(count);return owned(d);});}
Handle *nex_enum_new(int64_t count,int64_t ordinal){return guarded(0,[&]{auto d=std::make_shared<nexrt::Data>(nexrt::Data::Enum);d->ordinal=ordinal;d->values.resize(count);d->names.resize(count);return owned(d);});}
int64_t nex_enum_tag(Handle *value,int64_t count,int64_t line){return guarded(line,[&]{if(value->data->kind!=nexrt::Data::Enum||value->data->ordinal<0||value->data->ordinal>=count)throw nexrt::DataError("E_ENUM","invalid enum discriminant");return value->data->ordinal;});}
void nex_record_name(Handle *p,const char *name,int64_t size){guarded(0,[&]{p->data->text.assign(name,size);});}
void nex_record_field_name(Handle *p,int64_t index,const char *name,int64_t size){guarded(0,[&]{p->data->names.at(index).assign(name,size);});}
void nex_list_append_i64(Handle *p,int64_t value,int64_t boolean){guarded(0,[&]{p->data->values.emplace_back(value,boolean);});}
void nex_list_append_heap(Handle *p,Handle *value){guarded(0,[&]{p->data->values.emplace_back(value->data);});}
void nex_record_init_i64(Handle *p,int64_t index,int64_t value,int64_t boolean){p->data->values.at(index)=nexrt::Value(value,boolean);}
void nex_record_init_heap(Handle *p,int64_t index,Handle *value){p->data->values.at(index)=nexrt::Value(value->data);}
int64_t nex_collection_get_i64(Handle *p,int64_t index,int64_t line){return guarded(line,[&]{return nexrt::get(p->data,index).scalar;});}
Handle *nex_collection_get_heap(Handle *p,int64_t index,int64_t line){return guarded(line,[&]{return owned(nexrt::get(p->data,index).object);});}
Handle *nex_list_update_i64(Handle *p,int64_t index,int64_t value,int64_t boolean,int64_t mode,int64_t line){return guarded(line,[&]{return updated(p,index,nexrt::Value(value,boolean),mode);});}
Handle *nex_list_update_heap(Handle *p,int64_t index,Handle *value,int64_t mode,int64_t line){return guarded(line,[&]{return updated(p,index,nexrt::Value(value->data),mode);});}
int64_t nex_length(Handle *p){return guarded(0,[&]{return nexrt::length(p->data);});}
int64_t nex_heap_equal(Handle *a,Handle *b){return nexrt::equal(nexrt::Value(a->data),nexrt::Value(b->data));}
Handle *nex_heap_concat(Handle *a,Handle *b,int64_t line){return guarded(line,[&]{
  if(a->data->kind==nexrt::Data::String)return owned(nexrt::string(a->data->text+b->data->text));
  auto d=std::make_shared<nexrt::Data>(*a->data);d->values.insert(d->values.end(),b->data->values.begin(),b->data->values.end());return owned(d);
});}
Handle *nex_string_slice(Handle *p,int64_t start,int64_t count,int64_t line){return guarded(line,[&]{return owned(nexrt::slice(p->data,start,count));});}
int64_t nex_string_contains(Handle *a,Handle *b){return a->data->text.find(b->data->text)!=std::string::npos;}
Handle *nex_format_i64(int64_t value,int64_t boolean){return guarded(0,[&]{return owned(nexrt::string(nexrt::representation(nexrt::Value(value,boolean))));});}
Handle *nex_format_heap(Handle *p){return guarded(0,[&]{return owned(nexrt::string(nexrt::printable(nexrt::Value(p->data))));});}
void nex_print_heap(Handle *p){guarded(0,[&]{auto text=nexrt::printable(nexrt::Value(p->data));std::fwrite(text.data(),1,text.size(),stdout);std::fputc('\n',stdout);});}
void nex_runtime_finish(){if(nexrt::liveHandles||nexrt::liveObjects)fail("E_INTERNAL_LEAK","compiler did not release all managed values",0);}
void nex_poll(int64_t line){if(nexrt::currentRequest)nexrt::currentRequest->poll(line,false);}
Handle *nex_ok_i64(int64_t value,int64_t boolean){return guarded(0,[&]{return owned(nexrt::success(nexrt::Value(value,boolean)).object);});}
Handle *nex_ok_heap(Handle *value){return guarded(0,[&]{return owned(nexrt::success(nexrt::Value(value->data)).object);});}
Handle *nex_err(Handle *code,Handle *message){return guarded(0,[&]{return owned(nexrt::failure(code->data->text,message->data->text).object);});}
int64_t nex_is_ok(Handle *value){return nexrt::isSuccess(nexrt::Value(value->data));}
int64_t nex_unwrap_i64(Handle *value,int64_t line){return guarded(line,[&]{return nexrt::unwrap(nexrt::Value(value->data)).scalar;});}
Handle *nex_unwrap_heap(Handle *value,int64_t line){return guarded(line,[&]{return owned(nexrt::unwrap(nexrt::Value(value->data)).object);});}
Handle *nex_error_text(Handle *value,int64_t message){return guarded(0,[&]{return owned(nexrt::string(nexrt::isSuccess(nexrt::Value(value->data))?"":message?value->data->values[0].object->text:value->data->text));});}
Handle *nex_read_env(Handle *name){return nexrt::hostValue(0,[&]{return nexrt::readEnvironment(name->data->text);});}
}
