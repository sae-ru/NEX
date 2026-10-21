#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <limits>
#include "nex_host.h"
#include "nex_io.h"
#ifdef NEX_STRUCTURED_WORKERS
#include "nex_parallel.h"
#include <condition_variable>
#include <mutex>
#include <thread>
#endif
#include <chrono>
#include <unordered_set>
#include <algorithm>
#include <vector>
#include <map>
#include <cstring>

// A link-specific strong definition is emitted for executables/servers. Static
// NEX libraries retain the weak null fallback and do not collide at host link.
extern "C" __attribute__((weak)) const char *nex_application_identity()noexcept{return nullptr;}

namespace nexrt {
namespace {
thread_local RequestScope *currentRequest=nullptr;
struct ApplicationState {Handle *head=nullptr;};
thread_local ApplicationState *currentApplication=nullptr;
std::atomic<int64_t> liveHandles{0};
thread_local std::vector<void(*)() noexcept> resourceCleanups;
}
bool inRequestScope(){return currentRequest!=nullptr;}
void pollHostOperation(int64_t line){if(currentRequest)currentRequest->poll(line,true);}
void registerRuntimeCleanup(void (*cleanup)() noexcept){
  if(std::find(resourceCleanups.begin(),resourceCleanups.end(),cleanup)==resourceCleanups.end())resourceCleanups.push_back(cleanup);
}
void cleanupRuntimeResources(){while(!resourceCleanups.empty()){auto cleanup=resourceCleanups.back();resourceCleanups.pop_back();cleanup();}}
struct Handle {
  std::shared_ptr<Data> data;
  RequestScope *owner=currentRequest;
  ApplicationState *applicationOwner=owner?nullptr:currentApplication;
  Handle *previous=nullptr,*next=nullptr;
  explicit Handle(std::shared_ptr<Data> data):data(std::move(data)){
    // Profiling and request registration can allocate. Never leave a failed
    // constructor registered as a live handle in either ownership boundary.
    profileAllocate(this,sizeof(Handle),0);
    try{if(owner)owner->track(this);}
    catch(...){profileFree(this);throw;}
    if(applicationOwner){next=applicationOwner->head;if(next)next->previous=this;applicationOwner->head=this;}
    ++liveHandles;
  }
  ~Handle(){
    profileFree(this);if(owner)owner->untrack(this);
    if(applicationOwner){if(previous)previous->next=next;else applicationOwner->head=next;if(next)next->previous=previous;}
    --liveHandles;
  }
};
namespace {
// This ownership boundary does not grant request capabilities, budgets or
// cancellation. CLI file/foreign authorization and hosted RequestScope behavior
// remain independent. Intrusive tracking allocates no per-handle registry node.
struct ApplicationScope {
  ApplicationState state;
  ApplicationState *previous=currentApplication;
  ApplicationScope(){currentApplication=&state;}
  ~ApplicationScope(){
    profileUnwind();
    while(state.head)delete state.head;
    cleanupRuntimeResources();currentApplication=previous;
  }
};
}
struct RequestScope::Control {
  std::atomic<uint64_t> steps{0};
  uint64_t budget;
  std::chrono::steady_clock::time_point deadline;
  std::atomic<bool> cancelled{false},active{true},exhausted{false};
  Control(uint64_t budget,uint64_t timeoutMs):budget(budget),
    deadline(std::chrono::steady_clock::now()+std::chrono::milliseconds(timeoutMs)){}
};
struct RequestScope::Impl {
  std::unordered_set<Handle*> handles;
  ResourceDomain resources;
  std::map<const void*,std::unique_ptr<ResourceDomain>,std::less<>> resourceBindings;
  std::shared_ptr<Control> control;
  std::function<bool()> cancellation;
  bool worker=false;
  const std::atomic<bool> *workerStop=nullptr;
  explicit Impl(std::shared_ptr<Control> control):control(std::move(control)){}
};
RequestScope::RequestScope(uint64_t budget,uint64_t timeoutMs):impl(std::make_shared<Impl>(std::make_shared<Control>(budget,timeoutMs))){
  if(currentRequest)throw Trap("E_CONTEXT","nested request scope is not supported",0);
  currentRequest=this;
  resource_detail::requestBinder=[](const ResourceDomain &capability){return &currentRequest->bindResources(capability);};
}
RequestScope::RequestScope(std::shared_ptr<Control> control,const std::atomic<bool> *workerStop):impl(std::make_shared<Impl>(std::move(control))){
  if(currentRequest)throw Trap("E_CONTEXT","nested request scope is not supported",0);
  impl->worker=true;impl->workerStop=workerStop;currentRequest=this;
  resource_detail::requestBinder=[](const ResourceDomain &capability){return &currentRequest->bindResources(capability);};
}
RequestScope::~RequestScope(){
  if(!impl->worker)impl->control->active=false;
  profileUnwind();impl->resources.revoke();while(!impl->handles.empty())delete *impl->handles.begin();
  if(impl->worker)cleanupRuntimeResources();
  currentRequest=nullptr;resource_detail::requestBinder=nullptr;
}
void RequestScope::track(Handle *p){impl->handles.insert(p);}
void RequestScope::untrack(Handle *p){impl->handles.erase(p);}
void RequestScope::cancel(){impl->control->cancelled=true;impl->resources.revoke();}
ResourceDomain &RequestScope::bindResources(const ResourceDomain &capability){
  auto key=capability.scopeKey();auto found=impl->resourceBindings.find(key);
  if(found==impl->resourceBindings.end())found=impl->resourceBindings.emplace(key,std::make_unique<ResourceDomain>(impl->resources.combine(capability))).first;
  return *found->second;
}
void RequestScope::setCancellation(std::function<bool()> check){
  if(impl->worker)throw Trap("E_CONTEXT","worker cannot replace the request cancellation callback",0);
  impl->cancellation=std::move(check);
}
void RequestScope::poll(int64_t line,bool forceCancellation){checkExecution(line,forceCancellation,true);}
void RequestScope::checkExecution(int64_t line,bool forceCancellation,bool consumeStep){
  auto state=impl;auto control=state->control;
  // The host's cancellation callback belongs to the coordinator thread. Worker
  // polls only read shared atomic state; waiting coordinators still run it.
  if(!state->worker&&(forceCancellation||(control->steps.load()%64)==0)){
    auto cancellation=state->cancellation;
    if(cancellation&&cancellation())control->cancelled=true;
  }
  if(!control->active){state->resources.revoke();throw Trap("E_CANCELLED","request scope has ended",line);}
  if(control->cancelled){state->resources.revoke();throw Trap("E_CANCELLED","request was cancelled",line);}
  if(state->workerStop&&state->workerStop->load()){state->resources.revoke();throw Trap("E_CANCELLED","worker group was cancelled",line);}
  if(consumeStep){
    auto steps=control->steps.load();
    while(steps<control->budget&&!control->steps.compare_exchange_weak(steps,steps+1)){}
    if(steps>=control->budget)control->exhausted=true;
  }
  if(control->exhausted){state->resources.revoke();throw Trap("E_LIMIT","request execution budget exceeded",line);}
  if(std::chrono::steady_clock::now()>=control->deadline){state->resources.revoke();throw Trap("E_TIMEOUT","request deadline exceeded",line);}
}
#ifdef NEX_STRUCTURED_WORKERS
namespace {
thread_local size_t parallelDepth=0;
struct ParallelDepth {
  ParallelDepth(){++parallelDepth;}
  ~ParallelDepth(){--parallelDepth;}
};
void parallelValueCheck(const Value &value){
  std::vector<Value> pending{value};std::unordered_set<const Data*> seen;size_t members=1;
  while(!pending.empty()){
    auto next=std::move(pending.back());pending.pop_back();
    if(next.tag!=Value::Object)continue;
    if(!next.object)throw DataError("E_PARALLEL_VALUE","parallel value has a null object");
    if(!seen.insert(next.object.get()).second)continue;
    if(seen.size()>parallelMaximumNodes)throw DataError("E_LIMIT","parallel value graph exceeds its object limit");
    if((seen.size()%64)==0)pollHostOperation(0);
    if(next.object->kind==Data::File)throw DataError("E_PARALLEL_VALUE","parallel values cannot contain file resources");
    // All source-produced members of the other kinds are immutable after their
    // fresh-value construction. Retain shared Data, never a caller-owned Handle.
    if(next.object->values.size()>parallelMaximumNodes-members)throw DataError("E_LIMIT","parallel value graph exceeds its member limit");
    members+=next.object->values.size();
    pending.insert(pending.end(),next.object->values.begin(),next.object->values.end());
  }
}
}
struct ParallelAccess {
  static Value run(const Value &items,const Value &environment,int64_t workers,ParallelCallback callback,SourceLocation location){
    auto *owner=currentRequest;
    if(!owner)throw Trap("E_CONTEXT","parallel workers require an active request scope",location);
    return hostOperation(location,[&]{
      if(!callback)throw DataError("E_CONTEXT","parallel callback is missing");
      if(workers<1||workers>parallelMaximumWorkers)throw DataError("E_RANGE","parallel worker count must be in 1..16");
      if(items.tag!=Value::Object||!items.object||items.object->kind!=Data::List)throw DataError("E_TYPE","parallel input must be a list");
      if(items.object->values.size()>parallelMaximumItems)throw DataError("E_LIMIT","parallel input exceeds 65536 items");
      owner->checkExecution(location,true,false);
      parallelValueCheck(items);parallelValueCheck(environment);
      const Value inputs=items,captures=environment;
      auto output=std::make_shared<Data>(Data::List);output->values.resize(inputs.object->values.size());
      std::vector<std::exception_ptr> failures(output->values.size());
      auto invoke=[&](size_t index){
        auto value=hostOperation(location,[&]{
          pollHostOperation(location);
          auto result=callback(inputs.object->values[index],captures);
          parallelValueCheck(result);pollHostOperation(location);return result;
        });
        output->values[index]=std::move(value);
      };
      if(parallelDepth){
        // A nested pure group runs on its existing worker. It cannot multiply
        // operating-system threads or introduce a nested request capability.
        for(size_t i=0;i<output->values.size();++i)try{invoke(i);}catch(...){failures[i]=std::current_exception();}
      }else if(!output->values.empty()){
        std::atomic<size_t> next{0},finished{0};std::atomic<bool> stop{false};bool started=false;
        std::mutex mutex;std::condition_variable ready;
        auto control=owner->impl->control;
        const size_t count=std::min(size_t(workers),output->values.size());
        std::exception_ptr coordinatorFailure;
        // Declared last: every partial construction/failure joins before any
        // captured state, input, output or completion primitive can be destroyed.
        std::vector<std::jthread> threads;threads.reserve(count);
        try{
          for(size_t worker=0;worker<count;++worker)threads.emplace_back([&]{
            ParallelDepth depth;
            {std::unique_lock lock(mutex);ready.wait(lock,[&]{return started||stop.load();});}
            for(;;){
              if(stop.load())break;
              auto index=next.fetch_add(1);if(index>=output->values.size())break;
              try{RequestScope scope(control,&stop);invoke(index);}
              catch(...){failures[index]=std::current_exception();}
            }
            ++finished;ready.notify_all();
          });
          {std::lock_guard lock(mutex);started=true;}ready.notify_all();
          std::unique_lock lock(mutex);
          while(finished.load()!=count){
            lock.unlock();owner->checkExecution(location,true,false);lock.lock();
            ready.wait_for(lock,std::chrono::milliseconds(2),[&]{return finished.load()==count;});
          }
        }catch(...){
          coordinatorFailure=std::current_exception();
          {std::lock_guard lock(mutex);stop=true;}ready.notify_all();
        }
        for(auto &thread:threads)thread.join();
        if(coordinatorFailure)std::rethrow_exception(coordinatorFailure);
      }
      // Global cancellation, exhaustion and elapsed deadlines take precedence
      // over ordinary per-item errors. Waiting never adds execution steps.
      owner->checkExecution(location,true,false);
      for(const auto &failure:failures)if(failure)std::rethrow_exception(failure);
      return Value(std::move(output));
    });
  }
};
Value parallelValues(const Value &items,const Value &environment,int64_t workers,ParallelCallback callback,SourceLocation location){
  return ParallelAccess::run(items,environment,workers,callback,location);
}
#endif
Handle *makeHandle(const Value &value){if(value.tag!=Value::Object)throw DataError("E_RUNTIME","host handle requires an object");return new Handle(value.object);}
Value readHandle(const Handle *handle){return Value(handle->data);}
namespace {
std::string sourceRecord(const char *text)noexcept{
  try{if(!text)return {};auto size=::strnlen(text,16385);return size<=16384?std::string(text,size):std::string();}
  catch(...){return {};}
}
std::string sourceRecord(const NativeSite *site)noexcept{
  if(!site||!site->function)return {};
  try{
    const auto &function=*site->function;
    auto key=sourceRecord(site->site),kind=sourceRecord(site->kind),content=sourceRecord(function.functionHash),source=sourceRecord(function.sourceHash),compiler=sourceRecord(function.compilerBuild);
    if(key.size()!=64||content.size()!=64||source.size()!=64||compiler.size()!=64||kind.size()>128)return {};
    return "{\"schema\":\"nex.native-site/1\",\"operation_site\":"+nexrt::quoted(key)+",\"function_hash\":"+nexrt::quoted(content)+",\"function_source_hash\":"+nexrt::quoted(source)+",\"compiler_build\":"+nexrt::quoted(compiler)+",\"byte_begin\":"+std::to_string(site->begin)+",\"byte_end\":"+std::to_string(site->end)+",\"kind\":"+nexrt::quoted(kind)+"}";
  }catch(...){return {};}
}
std::pair<std::string,bool> diagnosticText(const char *text,size_t maximum){
  if(!text)return {{},false};size_t size=::strnlen(text,maximum+1);bool truncated=size>maximum;size=std::min(size,maximum);std::string result;
  for(size_t i=0;i<size;){auto first=static_cast<unsigned char>(text[i]);if(first<0x80){result+=char(first);++i;continue;}
    size_t count=first>=0xc2&&first<=0xdf?2:first>=0xe0&&first<=0xef?3:first>=0xf0&&first<=0xf4?4:0;
    bool valid=count&&count<=size-i;uint32_t scalar=count?first&((1u<<(7-count))-1):0;
    if(count&&count>size-i&&truncated)break;
    if(valid)for(size_t n=1;n<count;++n){auto byte=static_cast<unsigned char>(text[i+n]);if((byte&0xc0)!=0x80){valid=false;break;}scalar=(scalar<<6)|(byte&0x3f);}
    valid=valid&&!(count==2&&scalar<0x80)&&!(count==3&&scalar<0x800)&&!(count==4&&scalar<0x10000)&&scalar<=0x10ffff&&!(scalar>=0xd800&&scalar<=0xdfff);
    if(valid){result.append(text+i,count);i+=count;}else{result+="\xef\xbf\xbd";++i;}
  }
  return {std::move(result),truncated};
}
}
LocatedTrap::LocatedTrap(const Trap &trap,std::string source):Trap(trap.code,trap.what(),trap.line),source(std::move(source)){}
[[noreturn]] void propagateTrap(const Trap &trap,SourceLocation location){
  if(dynamic_cast<const LocatedTrap*>(&trap)||!location.site)throw;
  auto source=sourceRecord(location.site);if(source.empty())throw;throw LocatedTrap(trap,std::move(source));
}
void printNativeTrap(const char *code,const char *message,int64_t line,const std::string &source,const char *request)noexcept{
  if(source.empty())return;
  try{
    auto [safeCode,codeTruncated]=diagnosticText(code,128);auto [safeMessage,messageTruncated]=diagnosticText(message,4096);
    auto application=sourceRecord(nex_application_identity());
    std::string record="{\"schema\":\"nex.native-trap/1\",\"code\":"+nexrt::quoted(safeCode)+",\"message\":"+nexrt::quoted(safeMessage)+",\"reported_line\":"+std::to_string(line)+",\"message_truncated\":"+(messageTruncated?"true":"false")+",\"code_truncated\":"+(codeTruncated?"true":"false")+",\"source\":"+source+",\"application\":"+(application.empty()?"null":application);
    if(request)record+=",\"request_id\":"+nexrt::quoted(diagnosticText(request,256).first);record+="}";
    std::fprintf(stderr,"NEX_NATIVE_TRAP %s\n",record.c_str());
  }catch(...){/* Error reporting must not replace the original failure. */}
}
[[noreturn]] void runtimeFail(const char *code,const char *message,int64_t line){runtimeFail(code,message,SourceLocation{line});}
[[noreturn]] void runtimeFail(const char *code,const char *message,SourceLocation location){
  // Copy while the producing module is leased. Cleanup may unload its image.
  auto source=sourceRecord(location.site);auto line=location.line;
  profileUnwind();
  if(currentRequest||currentApplication){Trap trap(code,message,line);if(source.empty())throw trap;throw LocatedTrap(trap,std::move(source));}
  cleanupRuntimeResources();
  std::fflush(stdout);std::fprintf(stderr,"%s: %s at source line %lld\n",code,message,static_cast<long long>(line));printNativeTrap(code,message,line,source);std::exit(70);
}
}
using nexrt::Handle;
using nexrt::SourceLocation;
namespace {
[[noreturn]] void fail(const char *code,const char *message,SourceLocation line) {
  nexrt::runtimeFail(code,message,line);
}
template<class F> auto guarded(SourceLocation line,F operation)->decltype(operation()) {
  try{return operation();}
  catch(const nexrt::Trap &trap){nexrt::propagateTrap(trap,line);}
  catch(const nexrt::DataError &e){fail(e.code.c_str(),e.what(),line);}
  catch(const std::bad_alloc &){fail("E_MEMORY","allocation failed",line);}
  catch(const std::exception &e){fail("E_RUNTIME",e.what(),line);}
}
Handle *owned(std::shared_ptr<nexrt::Data> data){return new Handle(std::move(data));}
Handle *updated(Handle *list,int64_t index,nexrt::Value value,int64_t mode) {
  if(list->data->kind==nexrt::Data::Bytes){
    if(value.tag!=nexrt::Value::Integer)throw nexrt::DataError("E_RUNTIME","byte update requires an i64 value");
    const auto &buffer=nexrt::byteBuffer(list->data);
    return owned(nexrt::bytes(mode?buffer.set(index,value.scalar):buffer.append(value.scalar)));
  }
  auto data=std::make_shared<nexrt::Data>(*list->data);
  if(mode){nexrt::bounds(index,data->values.size());data->values[index]=std::move(value);}
  else data->values.push_back(std::move(value));
  return owned(data);
}
}
extern "C" {
static int64_t impl_nex_add(int64_t a,int64_t b,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> int64_t {int64_t r;if(__builtin_add_overflow(a,b,&r))fail("E_OVERFLOW","i64 arithmetic overflow",line);return r;});
}
int64_t nex_add(int64_t a,int64_t b,int64_t line){return impl_nex_add(a, b, line);}
int64_t nex_add_at(int64_t a,int64_t b,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_add(a, b, nexrt::SourceLocation{line,nex_site});}
static int64_t impl_nex_sub(int64_t a,int64_t b,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> int64_t {int64_t r;if(__builtin_sub_overflow(a,b,&r))fail("E_OVERFLOW","i64 arithmetic overflow",line);return r;});
}
int64_t nex_sub(int64_t a,int64_t b,int64_t line){return impl_nex_sub(a, b, line);}
int64_t nex_sub_at(int64_t a,int64_t b,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_sub(a, b, nexrt::SourceLocation{line,nex_site});}
static int64_t impl_nex_mul(int64_t a,int64_t b,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> int64_t {int64_t r;if(__builtin_mul_overflow(a,b,&r))fail("E_OVERFLOW","i64 arithmetic overflow",line);return r;});
}
int64_t nex_mul(int64_t a,int64_t b,int64_t line){return impl_nex_mul(a, b, line);}
int64_t nex_mul_at(int64_t a,int64_t b,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_mul(a, b, nexrt::SourceLocation{line,nex_site});}
static int64_t impl_nex_div(int64_t a,int64_t b,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> int64_t {if(!b)fail("E_DIV_ZERO","division by zero",line);if(a==std::numeric_limits<int64_t>::min()&&b==-1)fail("E_OVERFLOW","i64 arithmetic overflow",line);return a/b;});
}
int64_t nex_div(int64_t a,int64_t b,int64_t line){return impl_nex_div(a, b, line);}
int64_t nex_div_at(int64_t a,int64_t b,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_div(a, b, nexrt::SourceLocation{line,nex_site});}
static int64_t impl_nex_mod(int64_t a,int64_t b,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> int64_t {if(!b)fail("E_DIV_ZERO","division by zero",line);if(a==std::numeric_limits<int64_t>::min()&&b==-1)return 0;return a%b;});
}
int64_t nex_mod(int64_t a,int64_t b,int64_t line){return impl_nex_mod(a, b, line);}
int64_t nex_mod_at(int64_t a,int64_t b,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_mod(a, b, nexrt::SourceLocation{line,nex_site});}
static int64_t impl_nex_neg(int64_t a,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> int64_t {return impl_nex_sub(0,a,line);});
}
int64_t nex_neg(int64_t a,int64_t line){return impl_nex_neg(a, line);}
int64_t nex_neg_at(int64_t a,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_neg(a, nexrt::SourceLocation{line,nex_site});}
static double impl_nex_f64_add(double a,double b,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> double {return guarded(line,[&]{return nexrt::floatArithmetic(a,b,'+');});});
}
double nex_f64_add(double a,double b,int64_t line){return impl_nex_f64_add(a, b, line);}
double nex_f64_add_at(double a,double b,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_f64_add(a, b, nexrt::SourceLocation{line,nex_site});}
static double impl_nex_f64_sub(double a,double b,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> double {return guarded(line,[&]{return nexrt::floatArithmetic(a,b,'-');});});
}
double nex_f64_sub(double a,double b,int64_t line){return impl_nex_f64_sub(a, b, line);}
double nex_f64_sub_at(double a,double b,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_f64_sub(a, b, nexrt::SourceLocation{line,nex_site});}
static double impl_nex_f64_mul(double a,double b,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> double {return guarded(line,[&]{return nexrt::floatArithmetic(a,b,'*');});});
}
double nex_f64_mul(double a,double b,int64_t line){return impl_nex_f64_mul(a, b, line);}
double nex_f64_mul_at(double a,double b,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_f64_mul(a, b, nexrt::SourceLocation{line,nex_site});}
static double impl_nex_f64_div(double a,double b,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> double {return guarded(line,[&]{return nexrt::floatArithmetic(a,b,'/');});});
}
double nex_f64_div(double a,double b,int64_t line){return impl_nex_f64_div(a, b, line);}
double nex_f64_div_at(double a,double b,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_f64_div(a, b, nexrt::SourceLocation{line,nex_site});}
static double impl_nex_f64_mod(double a,double b,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> double {return guarded(line,[&]{return nexrt::floatArithmetic(a,b,'%');});});
}
double nex_f64_mod(double a,double b,int64_t line){return impl_nex_f64_mod(a, b, line);}
double nex_f64_mod_at(double a,double b,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_f64_mod(a, b, nexrt::SourceLocation{line,nex_site});}
static double impl_nex_f64_neg(double value,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> double {return guarded(line,[&]{return nexrt::negateFloat(value);});});
}
double nex_f64_neg(double value,int64_t line){return impl_nex_f64_neg(value, line);}
double nex_f64_neg_at(double value,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_f64_neg(value, nexrt::SourceLocation{line,nex_site});}
static double impl_nex_f64_validate(double value,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> double {return guarded(line,[&]{return nexrt::finiteFloat(value);});});
}
double nex_f64_validate(double value,int64_t line){return impl_nex_f64_validate(value, line);}
double nex_f64_validate_at(double value,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_f64_validate(value, nexrt::SourceLocation{line,nex_site});}
static int64_t impl_nex_f64_compare(double left,double right,int64_t operation,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> int64_t {return guarded(line,[&]{return int64_t(nexrt::compareFloat(left,right,operation));});});
}
int64_t nex_f64_compare(double left,double right,int64_t operation,int64_t line){return impl_nex_f64_compare(left, right, operation, line);}
int64_t nex_f64_compare_at(double left,double right,int64_t operation,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_f64_compare(left, right, operation, nexrt::SourceLocation{line,nex_site});}
static double impl_nex_as_f64(int64_t value,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> double {return guarded(line,[&]{return nexrt::integerToFloat(value);});});
}
double nex_as_f64(int64_t value,int64_t line){return impl_nex_as_f64(value, line);}
double nex_as_f64_at(int64_t value,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_as_f64(value, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_as_i64(double value,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return guarded(line,[&]{int64_t result=0;return owned((nexrt::floatToInteger(value,result)?nexrt::success(nexrt::Value(result)):nexrt::failure("E_RANGE","f64 value is outside i64 range")).object);});});
}
Handle * nex_as_i64(double value,int64_t line){return impl_nex_as_i64(value, line);}
Handle * nex_as_i64_at(double value,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_as_i64(value, nexrt::SourceLocation{line,nex_site});}
static void impl_nex_print_f64(double value, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> void {guarded(location,[&]{auto text=nexrt::formatFloat(value);std::puts(text.c_str());});});
}
void nex_print_f64(double value){return impl_nex_print_f64(value, nexrt::SourceLocation{});}
void nex_print_f64_at(double value, const nexrt::NativeSite *nex_site){return impl_nex_print_f64(value, nexrt::SourceLocation{0,nex_site});}
static void impl_nex_print_i64(int64_t a, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> void {std::printf("%lld\n",static_cast<long long>(a));});
}
void nex_print_i64(int64_t a){return impl_nex_print_i64(a, nexrt::SourceLocation{});}
void nex_print_i64_at(int64_t a, const nexrt::NativeSite *nex_site){return impl_nex_print_i64(a, nexrt::SourceLocation{0,nex_site});}
static void impl_nex_print_bool(int64_t a, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> void {std::puts(a?"true":"false");});
}
void nex_print_bool(int64_t a){return impl_nex_print_bool(a, nexrt::SourceLocation{});}
void nex_print_bool_at(int64_t a, const nexrt::NativeSite *nex_site){return impl_nex_print_bool(a, nexrt::SourceLocation{0,nex_site});}
static void impl_nex_assert(int64_t a,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> void {if(!a)fail("E_ASSERT","assertion failed",line);});
}
void nex_assert(int64_t a,int64_t line){return impl_nex_assert(a, line);}
void nex_assert_at(int64_t a,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_assert(a, nexrt::SourceLocation{line,nex_site});}
static void impl_nex_match_fail(nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> void {fail("E_MATCH","no checked match arm accepted the value",line);});
}
void nex_match_fail(int64_t line){return impl_nex_match_fail(line);}
void nex_match_fail_at(int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_match_fail(nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_retain(Handle *p, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> Handle * {return guarded(location,[&]{return p?owned(p->data):nullptr;});});
}
Handle * nex_retain(Handle *p){return impl_nex_retain(p, nexrt::SourceLocation{});}
Handle * nex_retain_at(Handle *p, const nexrt::NativeSite *nex_site){return impl_nex_retain(p, nexrt::SourceLocation{0,nex_site});}
static void impl_nex_release(Handle *p, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> void {delete p;});
}
void nex_release(Handle *p){return impl_nex_release(p, nexrt::SourceLocation{});}
void nex_release_at(Handle *p, const nexrt::NativeSite *nex_site){return impl_nex_release(p, nexrt::SourceLocation{0,nex_site});}
static Handle * impl_nex_string_new(const char *text,int64_t size,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return guarded(line,[&]{return owned(nexrt::string(std::string(text,size)));});});
}
Handle * nex_string_new(const char *text,int64_t size,int64_t line){return impl_nex_string_new(text, size, line);}
Handle * nex_string_new_at(const char *text,int64_t size,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_string_new(text, size, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_list_new(nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> Handle * {return guarded(location,[]{return owned(std::make_shared<nexrt::Data>(nexrt::Data::List));});});
}
Handle * nex_list_new(){return impl_nex_list_new(nexrt::SourceLocation{});}
Handle * nex_list_new_at(const nexrt::NativeSite *nex_site){return impl_nex_list_new(nexrt::SourceLocation{0,nex_site});}
static Handle * impl_nex_record_new(int64_t count, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> Handle * {return guarded(location,[&]{auto d=std::make_shared<nexrt::Data>(nexrt::Data::Record);d->values.resize(count);d->names.resize(count);return owned(d);});});
}
Handle * nex_record_new(int64_t count){return impl_nex_record_new(count, nexrt::SourceLocation{});}
Handle * nex_record_new_at(int64_t count, const nexrt::NativeSite *nex_site){return impl_nex_record_new(count, nexrt::SourceLocation{0,nex_site});}
static Handle * impl_nex_closure_new(void *code,int64_t count, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> Handle * {return guarded(location,[&]{if(!code||count<0||count>1024)throw nexrt::DataError("E_FUNCTION","invalid closure environment");auto d=std::make_shared<nexrt::Data>(nexrt::Data::Closure);d->code=code;d->values.resize(count);d->names.resize(count);return owned(d);});});
}
Handle * nex_closure_new(void *code,int64_t count){return impl_nex_closure_new(code, count, nexrt::SourceLocation{});}
Handle * nex_closure_new_at(void *code,int64_t count, const nexrt::NativeSite *nex_site){return impl_nex_closure_new(code, count, nexrt::SourceLocation{0,nex_site});}
static void * impl_nex_closure_code(Handle *value, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> void * {return guarded(location,[&]{if(!value||value->data->kind!=nexrt::Data::Closure||!value->data->code)throw nexrt::DataError("E_FUNCTION","invalid callable value");return value->data->code;});});
}
void * nex_closure_code(Handle *value){return impl_nex_closure_code(value, nexrt::SourceLocation{});}
void * nex_closure_code_at(Handle *value, const nexrt::NativeSite *nex_site){return impl_nex_closure_code(value, nexrt::SourceLocation{0,nex_site});}
static Handle * impl_nex_enum_new(int64_t count,int64_t ordinal, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> Handle * {return guarded(location,[&]{auto d=std::make_shared<nexrt::Data>(nexrt::Data::Enum);d->ordinal=ordinal;d->values.resize(count);d->names.resize(count);return owned(d);});});
}
Handle * nex_enum_new(int64_t count,int64_t ordinal){return impl_nex_enum_new(count, ordinal, nexrt::SourceLocation{});}
Handle * nex_enum_new_at(int64_t count,int64_t ordinal, const nexrt::NativeSite *nex_site){return impl_nex_enum_new(count, ordinal, nexrt::SourceLocation{0,nex_site});}
static int64_t impl_nex_enum_tag(Handle *value,int64_t count,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> int64_t {return guarded(line,[&]{if(value->data->kind!=nexrt::Data::Enum||value->data->ordinal<0||value->data->ordinal>=count)throw nexrt::DataError("E_ENUM","invalid enum discriminant");return value->data->ordinal;});});
}
int64_t nex_enum_tag(Handle *value,int64_t count,int64_t line){return impl_nex_enum_tag(value, count, line);}
int64_t nex_enum_tag_at(Handle *value,int64_t count,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_enum_tag(value, count, nexrt::SourceLocation{line,nex_site});}
static void impl_nex_record_name(Handle *p,const char *name,int64_t size, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> void {guarded(location,[&]{p->data->text.assign(name,size);});});
}
void nex_record_name(Handle *p,const char *name,int64_t size){return impl_nex_record_name(p, name, size, nexrt::SourceLocation{});}
void nex_record_name_at(Handle *p,const char *name,int64_t size, const nexrt::NativeSite *nex_site){return impl_nex_record_name(p, name, size, nexrt::SourceLocation{0,nex_site});}
static void impl_nex_record_field_name(Handle *p,int64_t index,const char *name,int64_t size, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> void {guarded(location,[&]{p->data->names.at(index).assign(name,size);});});
}
void nex_record_field_name(Handle *p,int64_t index,const char *name,int64_t size){return impl_nex_record_field_name(p, index, name, size, nexrt::SourceLocation{});}
void nex_record_field_name_at(Handle *p,int64_t index,const char *name,int64_t size, const nexrt::NativeSite *nex_site){return impl_nex_record_field_name(p, index, name, size, nexrt::SourceLocation{0,nex_site});}
static void impl_nex_list_append_i64(Handle *p,int64_t value,int64_t tag, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> void {guarded(location,[&]{p->data->values.push_back(nexrt::Value::taggedScalar(value,tag));});});
}
void nex_list_append_i64(Handle *p,int64_t value,int64_t tag){return impl_nex_list_append_i64(p, value, tag, nexrt::SourceLocation{});}
void nex_list_append_i64_at(Handle *p,int64_t value,int64_t tag, const nexrt::NativeSite *nex_site){return impl_nex_list_append_i64(p, value, tag, nexrt::SourceLocation{0,nex_site});}
static void impl_nex_list_append_heap(Handle *p,Handle *value, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> void {guarded(location,[&]{p->data->values.emplace_back(value->data);});});
}
void nex_list_append_heap(Handle *p,Handle *value){return impl_nex_list_append_heap(p, value, nexrt::SourceLocation{});}
void nex_list_append_heap_at(Handle *p,Handle *value, const nexrt::NativeSite *nex_site){return impl_nex_list_append_heap(p, value, nexrt::SourceLocation{0,nex_site});}
static void impl_nex_record_init_i64(Handle *p,int64_t index,int64_t value,int64_t tag, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> void {guarded(location,[&]{p->data->values.at(index)=nexrt::Value::taggedScalar(value,tag);});});
}
void nex_record_init_i64(Handle *p,int64_t index,int64_t value,int64_t tag){return impl_nex_record_init_i64(p, index, value, tag, nexrt::SourceLocation{});}
void nex_record_init_i64_at(Handle *p,int64_t index,int64_t value,int64_t tag, const nexrt::NativeSite *nex_site){return impl_nex_record_init_i64(p, index, value, tag, nexrt::SourceLocation{0,nex_site});}
static void impl_nex_record_init_heap(Handle *p,int64_t index,Handle *value, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> void {p->data->values.at(index)=nexrt::Value(value->data);});
}
void nex_record_init_heap(Handle *p,int64_t index,Handle *value){return impl_nex_record_init_heap(p, index, value, nexrt::SourceLocation{});}
void nex_record_init_heap_at(Handle *p,int64_t index,Handle *value, const nexrt::NativeSite *nex_site){return impl_nex_record_init_heap(p, index, value, nexrt::SourceLocation{0,nex_site});}
static int64_t impl_nex_collection_get_i64(Handle *p,int64_t index,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> int64_t {return guarded(line,[&]{return nexrt::get(p->data,index).scalar;});});
}
int64_t nex_collection_get_i64(Handle *p,int64_t index,int64_t line){return impl_nex_collection_get_i64(p, index, line);}
int64_t nex_collection_get_i64_at(Handle *p,int64_t index,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_collection_get_i64(p, index, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_collection_get_heap(Handle *p,int64_t index,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return guarded(line,[&]{return owned(nexrt::get(p->data,index).object);});});
}
Handle * nex_collection_get_heap(Handle *p,int64_t index,int64_t line){return impl_nex_collection_get_heap(p, index, line);}
Handle * nex_collection_get_heap_at(Handle *p,int64_t index,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_collection_get_heap(p, index, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_list_update_i64(Handle *p,int64_t index,int64_t value,int64_t tag,int64_t mode,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return guarded(line,[&]{return updated(p,index,nexrt::Value::taggedScalar(value,tag),mode);});});
}
Handle * nex_list_update_i64(Handle *p,int64_t index,int64_t value,int64_t tag,int64_t mode,int64_t line){return impl_nex_list_update_i64(p, index, value, tag, mode, line);}
Handle * nex_list_update_i64_at(Handle *p,int64_t index,int64_t value,int64_t tag,int64_t mode,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_list_update_i64(p, index, value, tag, mode, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_list_update_heap(Handle *p,int64_t index,Handle *value,int64_t mode,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return guarded(line,[&]{return updated(p,index,nexrt::Value(value->data),mode);});});
}
Handle * nex_list_update_heap(Handle *p,int64_t index,Handle *value,int64_t mode,int64_t line){return impl_nex_list_update_heap(p, index, value, mode, line);}
Handle * nex_list_update_heap_at(Handle *p,int64_t index,Handle *value,int64_t mode,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_list_update_heap(p, index, value, mode, nexrt::SourceLocation{line,nex_site});}
static int64_t impl_nex_length(Handle *p, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> int64_t {return guarded(location,[&]{return nexrt::length(p->data);});});
}
int64_t nex_length(Handle *p){return impl_nex_length(p, nexrt::SourceLocation{});}
int64_t nex_length_at(Handle *p, const nexrt::NativeSite *nex_site){return impl_nex_length(p, nexrt::SourceLocation{0,nex_site});}
static int64_t impl_nex_heap_equal(Handle *a,Handle *b, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> int64_t {return nexrt::equal(nexrt::Value(a->data),nexrt::Value(b->data));});
}
int64_t nex_heap_equal(Handle *a,Handle *b){return impl_nex_heap_equal(a, b, nexrt::SourceLocation{});}
int64_t nex_heap_equal_at(Handle *a,Handle *b, const nexrt::NativeSite *nex_site){return impl_nex_heap_equal(a, b, nexrt::SourceLocation{0,nex_site});}
static Handle * impl_nex_heap_concat(Handle *a,Handle *b,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return guarded(line,[&]{
  if(a->data->kind==nexrt::Data::Bytes)return owned(nexrt::bytes(nexrt::byteBuffer(a->data).concat(nexrt::byteBuffer(b->data))));
  if(a->data->kind==nexrt::Data::String)return owned(nexrt::string(a->data->text+b->data->text));
  auto d=std::make_shared<nexrt::Data>(*a->data);d->values.insert(d->values.end(),b->data->values.begin(),b->data->values.end());return owned(d);
});});
}
Handle * nex_heap_concat(Handle *a,Handle *b,int64_t line){return impl_nex_heap_concat(a, b, line);}
Handle * nex_heap_concat_at(Handle *a,Handle *b,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_heap_concat(a, b, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_string_slice(Handle *p,int64_t start,int64_t count,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return guarded(line,[&]{return owned(nexrt::slice(p->data,start,count));});});
}
Handle * nex_string_slice(Handle *p,int64_t start,int64_t count,int64_t line){return impl_nex_string_slice(p, start, count, line);}
Handle * nex_string_slice_at(Handle *p,int64_t start,int64_t count,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_string_slice(p, start, count, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_bytes_from_integers(Handle *value,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return nexrt::hostValue(line,[&]{return nexrt::bytesFromIntegers(nexrt::readHandle(value));});});
}
Handle * nex_bytes_from_integers(Handle *value,int64_t line){return impl_nex_bytes_from_integers(value, line);}
Handle * nex_bytes_from_integers_at(Handle *value,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_bytes_from_integers(value, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_utf8_bytes(Handle *value,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return nexrt::hostValue(line,[&]{return nexrt::Value(nexrt::utf8Bytes(value->data->text));});});
}
Handle * nex_utf8_bytes(Handle *value,int64_t line){return impl_nex_utf8_bytes(value, line);}
Handle * nex_utf8_bytes_at(Handle *value,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_utf8_bytes(value, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_decode_utf8(Handle *value,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return nexrt::hostValue(line,[&]{return nexrt::decodeUTF8(nexrt::byteBuffer(value->data));});});
}
Handle * nex_decode_utf8(Handle *value,int64_t line){return impl_nex_decode_utf8(value, line);}
Handle * nex_decode_utf8_at(Handle *value,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_decode_utf8(value, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_encode_base64(Handle *value,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return nexrt::hostValue(line,[&]{return nexrt::Value(nexrt::string(nexrt::byteBuffer(value->data).base64()));});});
}
Handle * nex_encode_base64(Handle *value,int64_t line){return impl_nex_encode_base64(value, line);}
Handle * nex_encode_base64_at(Handle *value,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_encode_base64(value, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_decode_base64(Handle *value,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return nexrt::hostValue(line,[&]{return nexrt::decodeBase64(value->data->text);});});
}
Handle * nex_decode_base64(Handle *value,int64_t line){return impl_nex_decode_base64(value, line);}
Handle * nex_decode_base64_at(Handle *value,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_decode_base64(value, nexrt::SourceLocation{line,nex_site});}
static int64_t impl_nex_string_contains(Handle *a,Handle *b, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> int64_t {return a->data->text.find(b->data->text)!=std::string::npos;});
}
int64_t nex_string_contains(Handle *a,Handle *b){return impl_nex_string_contains(a, b, nexrt::SourceLocation{});}
int64_t nex_string_contains_at(Handle *a,Handle *b, const nexrt::NativeSite *nex_site){return impl_nex_string_contains(a, b, nexrt::SourceLocation{0,nex_site});}
static Handle * impl_nex_format_i64(int64_t value,int64_t tag, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> Handle * {return guarded(location,[&]{return owned(nexrt::string(nexrt::representation(nexrt::Value::taggedScalar(value,tag))));});});
}
Handle * nex_format_i64(int64_t value,int64_t tag){return impl_nex_format_i64(value, tag, nexrt::SourceLocation{});}
Handle * nex_format_i64_at(int64_t value,int64_t tag, const nexrt::NativeSite *nex_site){return impl_nex_format_i64(value, tag, nexrt::SourceLocation{0,nex_site});}
static Handle * impl_nex_format_f64(double value, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> Handle * {return guarded(location,[&]{return owned(nexrt::string(nexrt::formatFloat(value)));});});
}
Handle * nex_format_f64(double value){return impl_nex_format_f64(value, nexrt::SourceLocation{});}
Handle * nex_format_f64_at(double value, const nexrt::NativeSite *nex_site){return impl_nex_format_f64(value, nexrt::SourceLocation{0,nex_site});}
static Handle * impl_nex_format_heap(Handle *p, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> Handle * {return guarded(location,[&]{return owned(nexrt::string(nexrt::printable(nexrt::Value(p->data))));});});
}
Handle * nex_format_heap(Handle *p){return impl_nex_format_heap(p, nexrt::SourceLocation{});}
Handle * nex_format_heap_at(Handle *p, const nexrt::NativeSite *nex_site){return impl_nex_format_heap(p, nexrt::SourceLocation{0,nex_site});}
static void impl_nex_print_heap(Handle *p, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> void {guarded(location,[&]{auto text=nexrt::printable(nexrt::Value(p->data));std::fwrite(text.data(),1,text.size(),stdout);std::fputc('\n',stdout);});});
}
void nex_print_heap(Handle *p){return impl_nex_print_heap(p, nexrt::SourceLocation{});}
void nex_print_heap_at(Handle *p, const nexrt::NativeSite *nex_site){return impl_nex_print_heap(p, nexrt::SourceLocation{0,nex_site});}
static void impl_nex_runtime_finish(nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> void {nexrt::cleanupRuntimeResources();if(nexrt::liveHandles||nexrt::liveObjects)fail("E_INTERNAL_LEAK","compiler did not release all managed values",location);});
}
void nex_runtime_finish(){return impl_nex_runtime_finish(nexrt::SourceLocation{});}
void nex_runtime_finish_at(const nexrt::NativeSite *nex_site){return impl_nex_runtime_finish(nexrt::SourceLocation{0,nex_site});}
static int64_t impl_nex_application_run(void *entry,int64_t argc,const char *const *argv,nexrt::SourceLocation location){
  try{
    nexrt::ApplicationScope scope;
    if(!entry)nexrt::runtimeFail("E_ENTRY","application entry is absent",location);
    auto result=reinterpret_cast<int64_t(*)(int64_t,const char *const *)>(entry)(argc,argv);
    impl_nex_runtime_finish(location);
    return result;
  }catch(const nexrt::Trap &trap){
    std::fflush(stdout);std::fprintf(stderr,"%s: %s at source line %lld\n",trap.code.c_str(),trap.what(),static_cast<long long>(trap.line));
    auto located=dynamic_cast<const nexrt::LocatedTrap*>(&trap);
    nexrt::printNativeTrap(trap.code.c_str(),trap.what(),trap.line,located?located->source:std::string());
  }catch(const std::bad_alloc &){
    std::fflush(stdout);std::fprintf(stderr,"E_MEMORY: allocation failed\n");
  }catch(const std::exception &){
    std::fflush(stdout);std::fprintf(stderr,"E_RUNTIME: application host operation failed\n");
  }
  return 70;
}
int64_t nex_application_run(void *entry,int64_t argc,const char *const *argv){return impl_nex_application_run(entry,argc,argv,nexrt::SourceLocation{});}
int64_t nex_application_run_at(void *entry,int64_t argc,const char *const *argv,const nexrt::NativeSite *site){return impl_nex_application_run(entry,argc,argv,nexrt::SourceLocation{0,site});}
static void impl_nex_poll(nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> void {if(nexrt::currentRequest)nexrt::currentRequest->poll(line,false);});
}
void nex_poll(int64_t line){return impl_nex_poll(line);}
void nex_poll_at(int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_poll(nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_ok_i64(int64_t value,int64_t tag, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> Handle * {return guarded(location,[&]{return owned(nexrt::success(nexrt::Value::taggedScalar(value,tag)).object);});});
}
Handle * nex_ok_i64(int64_t value,int64_t tag){return impl_nex_ok_i64(value, tag, nexrt::SourceLocation{});}
Handle * nex_ok_i64_at(int64_t value,int64_t tag, const nexrt::NativeSite *nex_site){return impl_nex_ok_i64(value, tag, nexrt::SourceLocation{0,nex_site});}
static Handle * impl_nex_ok_heap(Handle *value, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> Handle * {return guarded(location,[&]{return owned(nexrt::success(nexrt::Value(value->data)).object);});});
}
Handle * nex_ok_heap(Handle *value){return impl_nex_ok_heap(value, nexrt::SourceLocation{});}
Handle * nex_ok_heap_at(Handle *value, const nexrt::NativeSite *nex_site){return impl_nex_ok_heap(value, nexrt::SourceLocation{0,nex_site});}
static Handle * impl_nex_err(Handle *code,Handle *message, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> Handle * {return guarded(location,[&]{return owned(nexrt::failure(code->data->text,message->data->text).object);});});
}
Handle * nex_err(Handle *code,Handle *message){return impl_nex_err(code, message, nexrt::SourceLocation{});}
Handle * nex_err_at(Handle *code,Handle *message, const nexrt::NativeSite *nex_site){return impl_nex_err(code, message, nexrt::SourceLocation{0,nex_site});}
static int64_t impl_nex_is_ok(Handle *value, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> int64_t {return nexrt::isSuccess(nexrt::Value(value->data));});
}
int64_t nex_is_ok(Handle *value){return impl_nex_is_ok(value, nexrt::SourceLocation{});}
int64_t nex_is_ok_at(Handle *value, const nexrt::NativeSite *nex_site){return impl_nex_is_ok(value, nexrt::SourceLocation{0,nex_site});}
static int64_t impl_nex_unwrap_i64(Handle *value,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> int64_t {return guarded(line,[&]{return nexrt::unwrap(nexrt::Value(value->data)).scalar;});});
}
int64_t nex_unwrap_i64(Handle *value,int64_t line){return impl_nex_unwrap_i64(value, line);}
int64_t nex_unwrap_i64_at(Handle *value,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_unwrap_i64(value, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_unwrap_heap(Handle *value,nexrt::SourceLocation line){
  return nexrt::hostOperation(line,[&]() -> Handle * {return guarded(line,[&]{return owned(nexrt::unwrap(nexrt::Value(value->data)).object);});});
}
Handle * nex_unwrap_heap(Handle *value,int64_t line){return impl_nex_unwrap_heap(value, line);}
Handle * nex_unwrap_heap_at(Handle *value,int64_t line, const nexrt::NativeSite *nex_site){return impl_nex_unwrap_heap(value, nexrt::SourceLocation{line,nex_site});}
static Handle * impl_nex_error_text(Handle *value,int64_t message, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> Handle * {return guarded(location,[&]{return owned(nexrt::string(nexrt::isSuccess(nexrt::Value(value->data))?"":message?value->data->values[0].object->text:value->data->text));});});
}
Handle * nex_error_text(Handle *value,int64_t message){return impl_nex_error_text(value, message, nexrt::SourceLocation{});}
Handle * nex_error_text_at(Handle *value,int64_t message, const nexrt::NativeSite *nex_site){return impl_nex_error_text(value, message, nexrt::SourceLocation{0,nex_site});}
static Handle * impl_nex_read_env(Handle *name, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> Handle * {return nexrt::hostValue(location,[&]{return nexrt::readEnvironment(name->data->text);});});
}
Handle * nex_read_env(Handle *name){return impl_nex_read_env(name, nexrt::SourceLocation{});}
Handle * nex_read_env_at(Handle *name, const nexrt::NativeSite *nex_site){return impl_nex_read_env(name, nexrt::SourceLocation{0,nex_site});}
}
