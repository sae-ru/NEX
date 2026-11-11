#include <cstdint>
#include <cstdio>
#include <cstdlib>
#ifdef _WIN32
#include <fcntl.h>
#include <io.h>
#include <windows.h>
#endif
#include <limits>
#include "nex_host.h"
#include "nex_io.h"
#include "nex_source_error.h"
#ifdef NEX_ASYNC_TASKS
#include "nex_tasks.h"
#include "nex_task_values.h"
#endif
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
#ifdef NEX_SHARED_WINDOWS_RUNTIME
extern "C" const char *nex_application_identity()noexcept{
  // PE does not preempt a DLL's definition with the executable's strong one.
  // Resolve the final application's exported identity from its actual image.
  thread_local bool resolving=false;
  if(resolving)return nullptr;
  auto address=GetProcAddress(GetModuleHandleW(nullptr),"nex_application_identity");
  auto function=reinterpret_cast<const char *(*)()noexcept>(address);
  if(!function||function==nex_application_identity)return nullptr;
  resolving=true;auto result=function();resolving=false;return result;
}
#else
extern "C" __attribute__((weak)) const char *nex_application_identity()noexcept{return nullptr;}
#endif

namespace nexrt {
namespace {
thread_local RequestScope *currentRequest=nullptr;
struct ApplicationState {
  Handle *head=nullptr;ApplicationState *parent=nullptr;int64_t token=0;
  RequestScope *request=nullptr;ApplicationState *application=nullptr;
};
thread_local ApplicationState *currentApplication=nullptr;
struct FunctionOwners {
  ApplicationState *current=nullptr,*available=nullptr;size_t depth=0;
  ~FunctionOwners(){while(available){auto *next=available->parent;delete available;available=next;}}
  int64_t enter();
  void leave(Handle *kept)noexcept;
  void unwind(size_t baseline)noexcept{while(depth>baseline)leave(nullptr);}
};
thread_local FunctionOwners functionOwners;
std::atomic<int64_t> nextFunctionOwner{1};
ApplicationState *ownershipState(){
  auto *state=functionOwners.current;
  if(state&&state->request==currentRequest&&state->application==currentApplication)return state;
  return currentRequest?nullptr:currentApplication;
}
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
  ApplicationState *applicationOwner=ownershipState();
  Handle *previous=nullptr,*next=nullptr;
  explicit Handle(std::shared_ptr<Data> data):data(std::move(data)){
    // Profiling and request registration can allocate. Never leave a failed
    // constructor registered as a live handle in either ownership boundary.
    profileAllocate(this,sizeof(Handle),0);
    try{if(owner)owner->track(this);}
    catch(...){profileFree(this);throw;}
    if(applicationOwner)attach(applicationOwner);
    ++liveHandles;
  }
  ~Handle(){
    profileFree(this);if(owner)owner->untrack(this);
    detach();
    --liveHandles;
  }
  void detach()noexcept{
    if(applicationOwner){if(previous)previous->next=next;else applicationOwner->head=next;if(next)next->previous=previous;}
    applicationOwner=nullptr;previous=next=nullptr;
  }
  void attach(ApplicationState *state)noexcept{
    applicationOwner=state;previous=nullptr;next=state?state->head:nullptr;
    if(state){if(next)next->previous=this;state->head=this;}
  }
};
namespace {
int64_t FunctionOwners::enter(){
  if(!currentRequest&&!currentApplication)throw DataError("E_CONTEXT","function ownership requires an application or request scope");
  if(depth>=4096)throw DataError("E_LIMIT","function ownership depth exceeds 4096");
  auto token=nextFunctionOwner.load(std::memory_order_relaxed);
  while(token<std::numeric_limits<int64_t>::max()&&!nextFunctionOwner.compare_exchange_weak(token,token+1,std::memory_order_relaxed)){}
  if(token==std::numeric_limits<int64_t>::max())throw DataError("E_LIMIT","function ownership identities exhausted");
  // Reuse frames by depth. Enter may allocate; leave/unwind never allocate and
  // no extra field or per-value registry is added to managed Handle objects.
  auto *state=available;if(state)available=state->parent;else state=new ApplicationState;
  state->parent=current;state->head=nullptr;state->token=token;
  state->request=currentRequest;state->application=currentApplication;
  current=state;++depth;return token;
}
void FunctionOwners::leave(Handle *kept)noexcept{
  auto *state=current;bool transfer=kept&&kept->applicationOwner==state;
  if(transfer)kept->detach();
  current=state->parent;--depth;
  while(state->head)delete state->head;
  if(transfer)kept->attach(ownershipState());
  state->token=0;state->parent=available;available=state;
}
// This ownership boundary does not grant request capabilities, budgets or
// cancellation. CLI file/foreign authorization and hosted RequestScope behavior
// remain independent. Intrusive tracking allocates no per-handle registry node.
struct ApplicationScope {
  ApplicationState state;
  size_t functionBaseline=functionOwners.depth;
  ApplicationState *previous=currentApplication;
  ApplicationScope(){currentApplication=&state;}
  ~ApplicationScope(){
    profileUnwind();
    functionOwners.unwind(functionBaseline);
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
  bool preserveParentProfile=false;
  size_t functionBaseline=functionOwners.depth;
  const std::atomic<bool> *workerStop=nullptr;
#ifdef NEX_ASYNC_TASKS
  std::shared_ptr<const task_detail::Cancellation> taskStop;
#endif
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
  if(!impl->preserveParentProfile)profileUnwind();impl->resources.revoke();functionOwners.unwind(impl->functionBaseline);while(!impl->handles.empty())delete *impl->handles.begin();
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
std::chrono::steady_clock::time_point RequestScope::deadline()const noexcept{return impl->control->deadline;}
std::optional<std::chrono::steady_clock::time_point> currentRequestDeadline()noexcept{
  if(currentRequest)return currentRequest->deadline();
  return std::nullopt;
}
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
#ifdef NEX_ASYNC_TASKS
  if(state->taskStop&&state->taskStop->stopped())throw Trap("E_CANCELLED","task was cancelled",line);
#endif
}
#ifdef NEX_STRUCTURED_WORKERS
namespace {
thread_local size_t parallelDepth=0;
thread_local size_t parallelCallDepth=0;
struct ParallelDepth {
  ParallelDepth(){++parallelDepth;}
  ~ParallelDepth(){--parallelDepth;}
};
void parallelValueCheck(const Value &value){
  validateParallelValue(value,[]{pollHostOperation(0);});
}
}
#ifdef NEX_ASYNC_TASKS
size_t exchangeCompiledTaskDepth(size_t depth){
  if(depth>256)throw DataError("E_LIMIT","compiled task call depth exceeds 256");
  auto previous=parallelCallDepth;parallelCallDepth=depth;return previous;
}
#endif
struct ParallelAccess {
  static Value applicationCompiled(const Value &items,const Value &environment,int64_t workers,CompiledParallelBridge bridge,ParallelValueKind input,ParallelValueKind output,SourceLocation location){
    RequestScope scope;scope.impl->preserveParentProfile=true;
    return parallelCompiledValues(items,environment,workers,bridge,input,output,location);
  }
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
      // A callback can hit a resource bound without exhausting the shared step
      // counter (for example call depth or an output graph bound). Such failures
      // must not be hidden by an ordinary lower-index arithmetic error.
      for(const auto &failure:failures)if(failure)try{std::rethrow_exception(failure);}
      catch(const Trap &error){
        if(error.code=="E_LIMIT"||error.code=="E_TIMEOUT"||error.code=="E_CANCELLED"||error.code=="E_MEMORY")throw;
      }catch(const std::bad_alloc &){throw;}catch(...){/* Ordinary trusted callback failure: select by input order below. */}
      for(const auto &failure:failures)if(failure)std::rethrow_exception(failure);
      return Value(std::move(output));
    });
  }
};
Value parallelValues(const Value &items,const Value &environment,int64_t workers,ParallelCallback callback,SourceLocation location){
  return ParallelAccess::run(items,environment,workers,callback,location);
}
namespace {
struct CompiledParallelResult {Value value;bool assigned=false;};
thread_local CompiledParallelResult *activeParallelResult=nullptr;
struct CompiledParallelCall {
  const size_t baseline=functionOwners.depth;
  const size_t callBaseline=parallelCallDepth;
  CompiledParallelResult *previous=activeParallelResult;
  explicit CompiledParallelCall(CompiledParallelResult &result){
    functionOwners.enter();activeParallelResult=&result;
  }
  CompiledParallelCall(const CompiledParallelCall&)=delete;
  CompiledParallelCall &operator=(const CompiledParallelCall&)=delete;
  ~CompiledParallelCall(){activeParallelResult=previous;functionOwners.unwind(baseline);parallelCallDepth=callBaseline;}
};
bool parallelKindValid(ParallelValueKind kind){
  return kind==ParallelValueKind::I64||kind==ParallelValueKind::Bool||
    kind==ParallelValueKind::F64||kind==ParallelValueKind::Heap;
}
void parallelKindCheck(const Value &value,ParallelValueKind kind){
  bool valid=kind==ParallelValueKind::Heap?value.tag==Value::Object:
    kind==ParallelValueKind::F64?value.tag==Value::Floating:
    kind==ParallelValueKind::Bool?value.tag==Value::Boolean:value.tag==Value::Integer;
  if(!valid)throw DataError("E_PARALLEL_VALUE","compiled worker value differs from its checked ABI kind");
  if(value.tag==Value::Boolean&&(value.scalar<0||value.scalar>1))
    throw DataError("E_PARALLEL_VALUE","compiled worker boolean is not canonical");
  if(value.tag==Value::Floating)(void)value.floating();
}
void assignParallelResult(void *destination,Value value){
  // Check thread/nesting identity before dereferencing the opaque destination.
  if(!destination||destination!=activeParallelResult)
    throw DataError("E_CONTEXT","compiled worker result is outside its callback");
  if(activeParallelResult->assigned)
    throw DataError("E_PARALLEL_RESULT","compiled worker returned more than one value");
  activeParallelResult->value=std::move(value);activeParallelResult->assigned=true;
}
Value compiledParallelInvoke(const Value &item,const Value &context){
  auto bridge=reinterpret_cast<CompiledParallelBridge>(context.object->code);
  CompiledParallelResult result;
  {
    CompiledParallelCall call(result);
    auto *environment=makeHandle(context.object->values[0]);
    auto *heap=item.tag==Value::Object?makeHandle(item):nullptr;
    bridge(environment,item.tag==Value::Object?0:item.scalar,heap,&result);
    if(parallelCallDepth!=call.callBaseline)throw DataError("E_INTERNAL_SCOPE","compiled worker did not close every call scope");
    if(!result.assigned)throw DataError("E_PARALLEL_RESULT","compiled worker returned no value");
    parallelKindCheck(result.value,ParallelValueKind(context.object->values[1].scalar));
    // Result Value retains the immutable payload before job-local handles and
    // every unfinished nested ownership frame are released on this scope exit.
  }
  return std::move(result.value);
}
}
Value parallelCompiledValues(const Value &items,const Value &environment,int64_t workers,
    CompiledParallelBridge bridge,ParallelValueKind input,ParallelValueKind output,SourceLocation location){
  return hostOperation(location,[&]{
    if(!currentRequest)throw DataError("E_CONTEXT","compiled workers require an active request scope");
    if(!bridge||!parallelKindValid(input)||!parallelKindValid(output))
      throw DataError("E_CONTEXT","invalid compiled worker bridge or ABI kind");
    if(workers<1||workers>parallelMaximumWorkers)
      throw DataError("E_RANGE","parallel worker count must be in 1..16");
    if(environment.tag!=Value::Object||!environment.object||
       environment.object->kind!=Data::Closure||!environment.object->code)
      throw DataError("E_FUNCTION","compiled worker requires a callable environment");
    if(items.tag!=Value::Object||!items.object||items.object->kind!=Data::List)
      throw DataError("E_TYPE","compiled worker input must be a list");
    if(items.object->values.size()>parallelMaximumItems)
      throw DataError("E_LIMIT","parallel input exceeds 65536 items");
    for(size_t i=0;i<items.object->values.size();++i){
      parallelKindCheck(items.object->values[i],input);
      if((i%64)==0)pollHostOperation(location);
    }
    auto context=std::make_shared<Data>(Data::Closure);
    context->code=reinterpret_cast<void*>(bridge);
    context->values={environment,Value(int64_t(output))};
    return parallelValues(items,Value(std::move(context)),workers,compiledParallelInvoke,location);
  });
}
#endif
#ifdef NEX_ASYNC_TASKS
#include "nex_tasks_impl.h"
#include "nex_task_values_impl.h"
#endif
Handle *makeHandle(const Value &value){if(value.tag!=Value::Object)throw DataError("E_RUNTIME","host handle requires an object");return new Handle(value.object);}
Value readHandle(const Handle *handle){return Value(handle->data);}
Handle *makeSourceErrorHandle(const NativeSourceException &error){return makeHandle(nativeSourceErrorRecord(error));}
NativeSourceException readSourceErrorHandle(const Handle *handle){
  if(!handle)throw DataError("E_RUNTIME","invalid private source error");
  return nativeSourceErrorException(readHandle(handle));
}
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
std::pair<std::string,bool> diagnosticText(std::string_view text,size_t maximum){
  size_t size=text.size();bool truncated=size>maximum;size=std::min(size,maximum);std::string result;
  for(size_t i=0;i<size;){auto first=static_cast<unsigned char>(text[i]);if(first<0x80){result+=char(first);++i;continue;}
    size_t count=first>=0xc2&&first<=0xdf?2:first>=0xe0&&first<=0xef?3:first>=0xf0&&first<=0xf4?4:0;
    bool valid=count&&count<=size-i;uint32_t scalar=count?first&((1u<<(7-count))-1):0;
    if(count&&count>size-i&&truncated)break;
    if(valid)for(size_t n=1;n<count;++n){auto byte=static_cast<unsigned char>(text[i+n]);if((byte&0xc0)!=0x80){valid=false;break;}scalar=(scalar<<6)|(byte&0x3f);}
    valid=valid&&!(count==2&&scalar<0x80)&&!(count==3&&scalar<0x800)&&!(count==4&&scalar<0x10000)&&scalar<=0x10ffff&&!(scalar>=0xd800&&scalar<=0xdfff);
    if(valid){result.append(text.data()+i,count);i+=count;}else{result+="\xef\xbf\xbd";++i;}
  }
  return {std::move(result),truncated};
}
}
std::string copyNativeSourceRecord(const NativeSite *site)noexcept{return sourceRecord(site);}
LocatedTrap::LocatedTrap(const Trap &trap,std::string source):Trap(trap.code,trap.what(),trap.line),source(std::move(source)){}
[[noreturn]] void propagateTrap(const Trap &trap,SourceLocation location){
  if(dynamic_cast<const LocatedTrap*>(&trap)||!location.site)throw;
  auto source=sourceRecord(location.site);if(source.empty())throw;throw LocatedMessageTrap(trap.code,std::string(trapMessage(trap)),trap.line,std::move(source));
}
void printNativeTrapText(std::string_view code,std::string_view message,int64_t line,const std::string &source,const char *request)noexcept{
  if(source.empty())return;
  try{
    auto [safeCode,codeTruncated]=diagnosticText(code,128);auto [safeMessage,messageTruncated]=diagnosticText(message,4096);
    auto application=sourceRecord(nex_application_identity());
    std::string record="{\"schema\":\"nex.native-trap/1\",\"code\":"+nexrt::quoted(safeCode)+",\"message\":"+nexrt::quoted(safeMessage)+",\"reported_line\":"+std::to_string(line)+",\"message_truncated\":"+(messageTruncated?"true":"false")+",\"code_truncated\":"+(codeTruncated?"true":"false")+",\"source\":"+source+",\"application\":"+(application.empty()?"null":application);
    if(request)record+=",\"request_id\":"+nexrt::quoted(diagnosticText(std::string_view(request,::strnlen(request,257)),256).first);record+="}";
    std::fprintf(stderr,"NEX_NATIVE_TRAP %s\n",record.c_str());
  }catch(...){/* Error reporting must not replace the original failure. */}
}
void printNativeTrap(const char *code,const char *message,int64_t line,const std::string &source,const char *request)noexcept{
  printNativeTrapText(code?std::string_view(code,::strnlen(code,129)):std::string_view{},message?std::string_view(message,::strnlen(message,4097)):std::string_view{},line,source,request);
}
void printNativeSourceException(const NativeSourceException &error,const char *request)noexcept{
  try{
    std::string record="NEX_SOURCE_EXCEPTION {\"code\":"+quoted(error.code)+",\"message\":"+quoted(error.message)+",\"line\":"+std::to_string(error.line)+",\"source\":"+(error.source.empty()?"null":error.source);
    if(request)record+=",\"request_id\":"+quoted(request);record+="}\n";
    std::fwrite(record.data(),1,record.size(),stderr);
  }catch(...){/* Reporting must not replace the original source failure. */}
}
[[noreturn]] void runtimeFail(const char *code,const char *message,int64_t line){runtimeFail(code,message,SourceLocation{line});}
[[noreturn]] void runtimeFail(const char *code,const char *message,SourceLocation location){runtimeFailText(code?std::string_view(code):std::string_view{},message?std::string_view(message):std::string_view{},location);}
[[noreturn]] void runtimeFailText(std::string_view code,std::string_view message,SourceLocation location){
  // Own the message while the producing module is leased; cleanup can unload it.
  auto source=sourceRecord(location.site);auto line=location.line;
  profileUnwind();
  if(currentRequest||currentApplication){
    if(!source.empty())throw LocatedMessageTrap(std::string(code),std::string(message),line,std::move(source));
    throw MessageTrap(std::string(code),std::string(message),line);
  }
  std::string ownedCode(code),ownedMessage(message);cleanupRuntimeResources();
  std::fflush(stdout);std::fwrite(ownedCode.data(),1,ownedCode.size(),stderr);std::fputs(": ",stderr);std::fwrite(ownedMessage.data(),1,ownedMessage.size(),stderr);std::fprintf(stderr," at source line %lld\n",static_cast<long long>(line));printNativeTrapText(ownedCode,ownedMessage,line,source);std::exit(70);
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
  catch(const nexrt::DataError &e){nexrt::runtimeFailText(e.code,e.message,line);}
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
#ifdef NEX_STRUCTURED_WORKERS
static Handle *impl_nex_parallel_map(Handle *items,Handle *environment,int64_t workers,void *bridge,int64_t input,int64_t output,nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]{
    if(!items||!environment)throw nexrt::DataError("E_PARALLEL_VALUE","parallel_map requires input and callback handles");
    if(!nexrt::inRequestScope()&&!nexrt::currentApplication)throw nexrt::DataError("E_CONTEXT","parallel_map requires an application or request scope");
    auto values=nexrt::readHandle(items),captures=nexrt::readHandle(environment);nexrt::Value result;
    auto run=[&]{return nexrt::parallelCompiledValues(values,captures,workers,reinterpret_cast<nexrt::CompiledParallelBridge>(bridge),nexrt::ParallelValueKind(input),nexrt::ParallelValueKind(output),location);};
    if(nexrt::inRequestScope())result=run();
    else result=nexrt::ParallelAccess::applicationCompiled(values,captures,workers,reinterpret_cast<nexrt::CompiledParallelBridge>(bridge),nexrt::ParallelValueKind(input),nexrt::ParallelValueKind(output),location);
    // A CLI group's scope has ended. Allocate the coordinator result under its
    // original application/function owner, never under the expired request.
    return nexrt::makeHandle(result);
  });
}
Handle *nex_parallel_map(Handle *items,Handle *environment,int64_t workers,void *bridge,int64_t input,int64_t output,int64_t line){return impl_nex_parallel_map(items,environment,workers,bridge,input,output,{line});}
Handle *nex_parallel_map_at(Handle *items,Handle *environment,int64_t workers,void *bridge,int64_t input,int64_t output,int64_t line,const nexrt::NativeSite *site){return impl_nex_parallel_map(items,environment,workers,bridge,input,output,{line,site});}
static void impl_nex_parallel_enter(nexrt::SourceLocation location){
  nexrt::hostOperation(location,[&]{if(nexrt::parallelDepth){if(nexrt::parallelCallDepth>=256)throw nexrt::DataError("E_LIMIT","parallel callback call depth exceeds 256");++nexrt::parallelCallDepth;}});
}
void nex_parallel_enter(){impl_nex_parallel_enter({});}
void nex_parallel_enter_at(const nexrt::NativeSite *site){impl_nex_parallel_enter({0,site});}
static void impl_nex_parallel_leave(nexrt::SourceLocation location){
  nexrt::hostOperation(location,[&]{if(nexrt::parallelDepth){if(!nexrt::parallelCallDepth)throw nexrt::DataError("E_CONTEXT","parallel callback call scope is unbalanced");--nexrt::parallelCallDepth;}});
}
void nex_parallel_leave(){impl_nex_parallel_leave({});}
void nex_parallel_leave_at(const nexrt::NativeSite *site){impl_nex_parallel_leave({0,site});}
static void impl_nex_parallel_return_i64(void *destination,int64_t value,int64_t tag,nexrt::SourceLocation location){
  nexrt::hostOperation(location,[&]{nexrt::assignParallelResult(destination,nexrt::Value::taggedScalar(value,tag));});
}
void nex_parallel_return_i64(void *destination,int64_t value,int64_t tag){impl_nex_parallel_return_i64(destination,value,tag,{});}
void nex_parallel_return_i64_at(void *destination,int64_t value,int64_t tag,const nexrt::NativeSite *site){impl_nex_parallel_return_i64(destination,value,tag,{0,site});}
static void impl_nex_parallel_return_heap(void *destination,Handle *value,nexrt::SourceLocation location){
  nexrt::hostOperation(location,[&]{
    if(!value)throw nexrt::DataError("E_PARALLEL_RESULT","compiled worker returned a null heap handle");
    nexrt::assignParallelResult(destination,nexrt::readHandle(value));
  });
}
void nex_parallel_return_heap(void *destination,Handle *value){impl_nex_parallel_return_heap(destination,value,{});}
void nex_parallel_return_heap_at(void *destination,Handle *value,const nexrt::NativeSite *site){impl_nex_parallel_return_heap(destination,value,{0,site});}
#else
// Project-library objects can be reused by a consumer with no reachable map.
// Keep their call-scope ABI available without enabling a worker runtime.
void nex_parallel_enter(){}
void nex_parallel_enter_at(const nexrt::NativeSite*){}
void nex_parallel_leave(){}
void nex_parallel_leave_at(const nexrt::NativeSite*){}
#endif
static int64_t impl_nex_owned_enter(nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]{return nexrt::functionOwners.enter();});
}
int64_t nex_owned_enter(){return impl_nex_owned_enter(nexrt::SourceLocation{});}
int64_t nex_owned_enter_at(const nexrt::NativeSite *site){return impl_nex_owned_enter(nexrt::SourceLocation{0,site});}
static void impl_nex_owned_leave(int64_t token,Handle *kept,nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]{
    auto *frame=nexrt::functionOwners.current;
    if(!frame||frame->token!=token||frame->request!=nexrt::currentRequest||frame->application!=nexrt::currentApplication)
      throw nexrt::DataError("E_CONTEXT","function ownership token does not match the current scope");
    nexrt::functionOwners.leave(kept);
  });
}
void nex_owned_leave(int64_t token,Handle *kept){return impl_nex_owned_leave(token,kept,nexrt::SourceLocation{});}
void nex_owned_leave_at(int64_t token,Handle *kept,const nexrt::NativeSite *site){return impl_nex_owned_leave(token,kept,nexrt::SourceLocation{0,site});}
// Private source errors are immutable managed records, never host traps. Their
// source strings retain length and the copied native site survives rethrow.
// Typed records additionally retain the complete owned value and concrete key.
extern "C++" { namespace {
constexpr const char *sourceErrorMarker=nexrt::sourceErrorRecordV1;
using NativeSourceException=nexrt::NativeSourceException;
const nexrt::Data &sourceError(Handle *handle){
  if(!handle)throw nexrt::DataError("E_RUNTIME","invalid private source error");
  return nexrt::checkedSourceErrorRecord(nexrt::Value(handle->data));
}
} }
static void impl_nex_owned_promote(Handle *handle,int64_t token,SourceLocation location){
  nexrt::hostOperation(location,[&]{
    if(!handle)return;
    auto *target=nexrt::functionOwners.current;
    while(target&&target->token!=token)target=target->parent;
    if(!target||target->request!=nexrt::currentRequest||target->application!=nexrt::currentApplication)
      throw nexrt::DataError("E_CONTEXT","slot owner is not an active enclosing scope");
    // Slots receive owned handles, never a caller's borrowed parameter handle.
    auto *owner=nexrt::functionOwners.current;
    while(owner&&owner!=handle->applicationOwner)owner=owner->parent;
    if(!owner)throw nexrt::DataError("E_CONTEXT","stored handle has no active owner");
    if(handle->applicationOwner!=target){handle->detach();handle->attach(target);}
  });
}
void nex_owned_promote(Handle *handle,int64_t token){impl_nex_owned_promote(handle,token,{});}
void nex_owned_promote_at(Handle *handle,int64_t token,const nexrt::NativeSite *site){impl_nex_owned_promote(handle,token,{0,site});}
static Handle *impl_nex_source_error_new(Handle *code,Handle *message,SourceLocation location){
  return nexrt::hostOperation(location,[&]{
    if(!code||!message||code->data->kind!=nexrt::Data::String||message->data->kind!=nexrt::Data::String)
      throw nexrt::DataError("E_RUNTIME","source error payload must contain strings");
    auto data=std::make_shared<nexrt::Data>(nexrt::Data::Record);
    data->text=sourceErrorMarker+nexrt::sourceRecord(location.site);data->ordinal=location.line;
    data->values={nexrt::Value(code->data),nexrt::Value(message->data)};return owned(std::move(data));
  });
}
Handle *nex_source_error_new(Handle *code,Handle *message,int64_t line){return impl_nex_source_error_new(code,message,{line});}
Handle *nex_source_error_new_at(Handle *code,Handle *message,int64_t line,const nexrt::NativeSite *site){return impl_nex_source_error_new(code,message,{line,site});}
// Checked compiler-private typed packet ABI. Wire scalar tags remain0/1/2;
// heap kinds are Data::Kind, with -1 reserved for success-or-failure Result.
static const std::string &sourceTypeString(Handle *value){
  if(!value||!value->data||value->data->kind!=nexrt::Data::String)throw nexrt::DataError("E_SOURCE_TYPE","typed source metadata must be strings");
  return value->data->text;
}
static Handle *typedSourcePacket(Handle *key,Handle *name,nexrt::Value value,SourceLocation location){
  auto payload=std::make_shared<const nexrt::SourceErrorPayload>(sourceTypeString(key),std::move(value));
  return nexrt::makeSourceErrorHandle(nexrt::NativeSourceException(sourceTypeString(name),"typed source error",nexrt::sourceRecord(location.site),location.line,std::move(payload)));
}
static Handle *impl_nex_source_error_typed_scalar(Handle *key,Handle *name,int64_t value,int64_t tag,SourceLocation location){
  return nexrt::hostOperation(location,[&]{return typedSourcePacket(key,name,nexrt::Value::taggedScalar(value,tag),location);});
}
Handle *nex_source_error_typed_scalar(Handle *key,Handle *name,int64_t value,int64_t tag,int64_t line){return impl_nex_source_error_typed_scalar(key,name,value,tag,{line});}
Handle *nex_source_error_typed_scalar_at(Handle *key,Handle *name,int64_t value,int64_t tag,int64_t line,const nexrt::NativeSite *site){return impl_nex_source_error_typed_scalar(key,name,value,tag,{line,site});}
static Handle *impl_nex_source_error_typed_heap(Handle *key,Handle *name,Handle *value,SourceLocation location){
  return nexrt::hostOperation(location,[&]{if(!value||!value->data)throw nexrt::DataError("E_SOURCE_TYPE","typed source payload requires a nonnull owned value");return typedSourcePacket(key,name,nexrt::readHandle(value),location);});
}
Handle *nex_source_error_typed_heap(Handle *key,Handle *name,Handle *value,int64_t line){return impl_nex_source_error_typed_heap(key,name,value,{line});}
Handle *nex_source_error_typed_heap_at(Handle *key,Handle *name,Handle *value,int64_t line,const nexrt::NativeSite *site){return impl_nex_source_error_typed_heap(key,name,value,{line,site});}
static int64_t impl_nex_source_error_matches(Handle *error,Handle *key,SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> int64_t {sourceError(error);return nexrt::sourceErrorRecordMatches(nexrt::readHandle(error),sourceTypeString(key));});
}
int64_t nex_source_error_matches(Handle *error,Handle *key,int64_t line){return impl_nex_source_error_matches(error,key,{line});}
int64_t nex_source_error_matches_at(Handle *error,Handle *key,int64_t line,const nexrt::NativeSite *site){return impl_nex_source_error_matches(error,key,{line,site});}
static int64_t impl_nex_source_error_scalar(Handle *error,Handle *key,int64_t tag,SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> int64_t {
    if(tag<0||tag>2)throw nexrt::DataError("E_SOURCE_TYPE","invalid checked source scalar kind");
    sourceError(error);auto payload=nexrt::sourceErrorRecordPayload(nexrt::readHandle(error),sourceTypeString(key));
    return payload.getScalar(payload.typeKey,tag==0?nexrt::Value::Integer:tag==1?nexrt::Value::Boolean:nexrt::Value::Floating).scalar;
  });
}
int64_t nex_source_error_scalar(Handle *error,Handle *key,int64_t tag,int64_t line){return impl_nex_source_error_scalar(error,key,tag,{line});}
int64_t nex_source_error_scalar_at(Handle *error,Handle *key,int64_t tag,int64_t line,const nexrt::NativeSite *site){return impl_nex_source_error_scalar(error,key,tag,{line,site});}
static Handle *impl_nex_source_error_heap(Handle *error,Handle *key,int64_t kind,SourceLocation location){
  return nexrt::hostOperation(location,[&]{
    sourceError(error);auto payload=nexrt::sourceErrorRecordPayload(nexrt::readHandle(error),sourceTypeString(key));
    if(kind==-1){const auto &v=payload.get(payload.typeKey);if(v.tag!=nexrt::Value::Object||!v.object||(v.object->kind!=nexrt::Data::Success&&v.object->kind!=nexrt::Data::Failure))throw nexrt::DataError("E_SOURCE_TYPE","source result payload kind differs");kind=v.object->kind;}
    if(kind<0||kind>nexrt::Data::External)throw nexrt::DataError("E_SOURCE_TYPE","invalid checked source heap kind");
    return nexrt::makeHandle(payload.getObject(payload.typeKey,static_cast<nexrt::Data::Kind>(kind)));
  });
}
Handle *nex_source_error_heap(Handle *error,Handle *key,int64_t kind,int64_t line){return impl_nex_source_error_heap(error,key,kind,{line});}
Handle *nex_source_error_heap_at(Handle *error,Handle *key,int64_t kind,int64_t line,const nexrt::NativeSite *site){return impl_nex_source_error_heap(error,key,kind,{line,site});}
void nex_source_error_unmatched(int64_t line){nexrt::runtimeFail("E_SOURCE_TYPE","typed packet escaped statically total source handlers",line);}
void nex_source_error_unmatched_at(int64_t line,const nexrt::NativeSite *site){nexrt::runtimeFail("E_SOURCE_TYPE","typed packet escaped statically total source handlers",nexrt::SourceLocation{line,site});}
static Handle *impl_nex_source_error_field(Handle *error,size_t index,SourceLocation location){return nexrt::hostOperation(location,[&]{return owned(sourceError(error).values.at(index).object);});}
Handle *nex_source_error_code(Handle *error){return impl_nex_source_error_field(error,0,{});}
Handle *nex_source_error_code_at(Handle *error,const nexrt::NativeSite *site){return impl_nex_source_error_field(error,0,{0,site});}
Handle *nex_source_error_message(Handle *error){return impl_nex_source_error_field(error,1,{});}
Handle *nex_source_error_message_at(Handle *error,const nexrt::NativeSite *site){return impl_nex_source_error_field(error,1,{0,site});}
static void impl_nex_source_error_unhandled(Handle *error,SourceLocation location){
  auto exception=nexrt::hostOperation(location,[&]{return nexrt::readSourceErrorHandle(error);});
  throw exception;
}
void nex_source_error_unhandled(Handle *error){impl_nex_source_error_unhandled(error,{});}
void nex_source_error_unhandled_at(Handle *error,const nexrt::NativeSite *site){impl_nex_source_error_unhandled(error,{0,site});}
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
static Handle * impl_nex_text_join(Handle *p, nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> Handle * {return guarded(location,[&]{
    if(!p||!p->data||p->data->kind!=nexrt::Data::List)throw nexrt::DataError("E_INTERNAL","text builder requires its private list");
    size_t total=0;
    for(const auto &value:p->data->values){
      if(value.tag!=nexrt::Value::Object||!value.object||value.object->kind!=nexrt::Data::String)throw nexrt::DataError("E_INTERNAL","text builder item is not a string");
      if(value.object->text.size()>std::numeric_limits<size_t>::max()-total)throw nexrt::DataError("E_LIMIT","text builder exceeds addressable bytes");
      total+=value.object->text.size();
    }
    std::string text;text.reserve(total);
    for(const auto &value:p->data->values)text+=value.object->text;
    return owned(nexrt::string(std::move(text)));
  });});
}
Handle * nex_text_join(Handle *p){return impl_nex_text_join(p, nexrt::SourceLocation{});}
Handle * nex_text_join_at(Handle *p, const nexrt::NativeSite *nex_site){return impl_nex_text_join(p, nexrt::SourceLocation{0,nex_site});}
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
static Handle * impl_nex_bytes_from_octets(Handle *list,nexrt::SourceLocation location){
  return nexrt::hostOperation(location,[&]() -> Handle * {return guarded(location,[&]{
    if(!list||!list->data||list->data->kind!=nexrt::Data::List)throw nexrt::DataError("E_RUNTIME","byte construction requires an i64 list");
    return owned(nexrt::bytes(nexrt::ByteData::fromList(list->data->values)));
  });});
}
Handle * nex_bytes_from_octets(Handle *list){return impl_nex_bytes_from_octets(list, nexrt::SourceLocation{});}
Handle * nex_bytes_from_octets_at(Handle *list, const nexrt::NativeSite *nex_site){return impl_nex_bytes_from_octets(list, nexrt::SourceLocation{0,nex_site});}
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
  return nexrt::hostOperation(location,[&]() -> void {
    if(nexrt::functionOwners.depth)fail("E_INTERNAL_SCOPE","compiler did not close every function ownership scope",location);
    nexrt::cleanupRuntimeResources();if(nexrt::liveHandles||nexrt::liveObjects)fail("E_INTERNAL_LEAK","compiler did not release all managed values",location);
  });
}
void nex_runtime_finish(){return impl_nex_runtime_finish(nexrt::SourceLocation{});}
void nex_runtime_finish_at(const nexrt::NativeSite *nex_site){return impl_nex_runtime_finish(nexrt::SourceLocation{0,nex_site});}
static int64_t impl_nex_application_run(void *entry,int64_t argc,const char *const *argv,nexrt::SourceLocation location){
#ifdef _WIN32
  // NEX print preserves UTF-8 bytes, including explicit CR/LF in strings.
  // Flush before restoring the modes of a trusted embedding host.
  struct OutputModes {
    int output=::_setmode(::_fileno(stdout),_O_BINARY);
    int errors=::_setmode(::_fileno(stderr),_O_BINARY);
    ~OutputModes(){
      std::fflush(stdout);std::fflush(stderr);
      if(output!=-1)::_setmode(::_fileno(stdout),output);
      if(errors!=-1)::_setmode(::_fileno(stderr),errors);
    }
  } outputModes;
#endif
  try{
    nexrt::ApplicationScope scope;
    if(!entry)nexrt::runtimeFail("E_ENTRY","application entry is absent",location);
    auto result=reinterpret_cast<int64_t(*)(int64_t,const char *const *)>(entry)(argc,argv);
    impl_nex_runtime_finish(location);
    return result;
  }catch(const NativeSourceException &error){
    std::fflush(stdout);
    nexrt::printNativeSourceException(error);
  }catch(const nexrt::Trap &trap){
    auto message=nexrt::trapMessage(trap);std::fflush(stdout);std::fwrite(trap.code.data(),1,trap.code.size(),stderr);std::fputs(": ",stderr);std::fwrite(message.data(),1,message.size(),stderr);std::fprintf(stderr," at source line %lld\n",static_cast<long long>(trap.line));
    auto located=dynamic_cast<const nexrt::LocatedTrap*>(&trap);
    nexrt::printNativeTrapText(trap.code,nexrt::trapMessage(trap),trap.line,located?located->source:std::string());
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
