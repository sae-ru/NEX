#include "nex_task_session.h"
#ifndef NEX_MANAGED_TASKS
#error NativeTaskSession requires the matching owner-thread reference runtime
#endif
#include <algorithm>
#include <thread>

namespace nexrt {
namespace {
[[noreturn]] void sessionFailure(std::string code,std::string message,SourceLocation location){
  auto source=copyNativeSourceRecord(location.site);
  if(!source.empty())throw LocatedMessageTrap(std::move(code),std::move(message),location.line,std::move(source));
  throw MessageTrap(std::move(code),std::move(message),location.line);
}
template<class F> auto sessionOperation(SourceLocation location,F action)->decltype(action()){
  try{return action();}
  catch(const NativeSourceException &){throw;}
  catch(const Trap &error){propagateTrap(error,location);}
  catch(const DataError &error){sessionFailure(error.code,error.message,location);}
  catch(const std::bad_alloc &){sessionFailure("E_MEMORY","native session allocation failed",location);}
  catch(const std::exception &){sessionFailure("E_RUNTIME","native session host operation failed",location);}
}
struct Invocation {
  NativeTaskFrame &frame;
};
TaskBody invocationTask(TaskGroup &group,Value input,Value,const void *context){
  if(!context||input.tag!=Value::Object||!input.object||input.object->kind!=Data::List)
    throw DataError("E_TASK_STATE","native session invocation arguments are absent");
  const auto &call=*static_cast<const Invocation*>(context);
  return executeTaskFrame(group,std::move(call.frame));
}
void descriptor(const TaskCodeDescriptor &code,const std::shared_ptr<const TaskFrameHostContext> &host){
  if(code.abi!=taskCodeManagedReferencesABI||!validTaskCodeRequirements(code.abi,code.requirements)||
     (code.requirements&~taskManagedReferenceProviderRequirementsMask)||code.captureCount)
    throw DataError("E_TASK_SESSION_ABI","native session requires a checked capture-free030 ABI8 provider descriptor");
  if((code.requirements&(taskCodeImageFileRead|taskCodeImageFileWrite|taskCodeImageFileStream))&&!host)
    throw DataError("E_TASK_HOST","native session file operations require an explicit persistent host context");
}
void promote(TaskGroup &group,const Value &value,const ResourceRegionAuthority &target){
  auto resources=collectTaskSnapshot(group,value,{});
  ExternalResource::transferRegions(resources.external,group.resourceAuthority(),target,true,resources.files);
}
bool abortBeforeAdmission(const Trap &error){
  return error.code=="E_CANCELLED"||error.code=="E_TIMEOUT"||error.code=="E_LIMIT"||error.code=="E_MEMORY"||error.code=="E_RUNTIME";
}
}
struct NativeTaskSession::Impl {
  const std::thread::id thread=std::this_thread::get_id();
  PersistentRequestContext context;
  const NativeTaskSessionOptions options;
  std::shared_ptr<const TaskFrameHostContext> host;
  ResourceRegion resources;
  std::optional<ResourceRegionRetirement> retirement;
  bool active=false,initialized=false;
  uint64_t invocations=0,sourceErrors=0,fatalExits=0;
  Impl(NativeTaskSessionOptions options,std::shared_ptr<const TaskFrameHostContext> host)
    :context(options.resources.owners),options(options),host(std::move(host)),resources(ResourceRegionFamily::Request,options.resources){
    if(options.maximumTasks<1||options.maximumTasks>65536||!validTaskExternalLimits(options.external)||
       !options.heap.maximumCells||!options.heap.maximumNodes||!options.heap.maximumEdges)
      throw DataError("E_OPTION","native session requires valid heap, task and external-operation bounds");
  }
  void requireThread()const{if(thread!=std::this_thread::get_id())throw DataError("E_CONTEXT","native session belongs to another thread");}
  void requireIdle(bool allowClosed=false)const{
    requireThread();if(active)throw DataError("E_CONTEXT","native session cannot nest or reenter");
    if(!allowClosed&&context.closed())throw DataError("E_CONTEXT","native session has ended");
  }
  void retire(){if(context.closed()&&!active&&!retirement){retirement.emplace(resources.beginClose());retirement->requestClose();}}
  void close(){requireThread();context.close();retire();}
  struct Operation {
    Impl &owner;
    explicit Operation(Impl &owner):owner(owner){owner.requireIdle();owner.active=true;}
    ~Operation(){owner.active=false;owner.retire();}
  };
  void initialize(){if(!initialized){configureManagedCellHeap(options.heap);initialized=true;}}
};
NativeTaskSession::NativeTaskSession(NativeTaskSessionOptions options,std::shared_ptr<const TaskFrameHostContext> host)
  :impl(sessionOperation({},[&]{return std::make_shared<Impl>(options,std::move(host));})){}
NativeTaskSession::~NativeTaskSession(){try{impl->close();}catch(...){std::terminate();}}
Value NativeTaskSession::invoke(const TaskCodeDescriptor &code,const std::vector<Value> &arguments,
    NativeTaskInvocationOptions options,SourceLocation location){
  auto state=impl;
  return sessionOperation(location,[&]() -> Value {
    state->requireIdle();descriptor(code,state->host);
    if(!validTaskExecutionLimits(options.limits))throw DataError("E_OPTION","invalid native session invocation limits");
    // Constructor validation is independent of the session's heap and source
    // admission. A wrong physical argument kind must not discard existing state.
    NativeTaskFrame checked(code,arguments,{},state->host);
    Impl::Operation operation(*state);
    bool callbackFailed=false,callbackAllocationFailed=false;
    RequestScope request(state->context,options.limits.steps,options.limits.timeoutMs);
    if(options.cancelled)request.setCancellation([check=std::move(options.cancelled),&callbackFailed,&callbackAllocationFailed]{
      try{return check();}
      catch(const std::bad_alloc &){callbackFailed=callbackAllocationFailed=true;return true;}
      catch(...){callbackFailed=true;return true;}
    });
    bool admitted=false;
    try{
      state->initialize();auto external=state->options.external;
      external.workers=std::min(external.workers,size_t(options.limits.workers));
      TaskGroup group(managedTaskOwnerExecution(),state->options.maximumTasks,external,true,true);
      group.enableResourceRegions(state->resources.authority(),true,true);
      auto inputs=Data::make(Data::List);inputs->values=arguments;
      Invocation invocation{checked};
      auto root=group.spawnWithContext(invocationTask,&invocation,Value(std::move(inputs)),{});
      admitted=true;++state->invocations;
      Value result;
      try{result=group.join(root);}
      catch(const NativeSourceException &error){
        if(error.payload)promote(group,error.payload->value,state->resources.authority());
        group.finish();request.poll();++state->sourceErrors;throw;
      }
      promote(group,result,state->resources.authority());group.finish();request.poll();
      return result;
    }catch(const NativeSourceException &){throw;}
    catch(const Trap &error){
      if(admitted||abortBeforeAdmission(error)){++state->fatalExits;state->close();}
      if(callbackFailed)sessionFailure(callbackAllocationFailed?"E_MEMORY":"E_RUNTIME","native session cancellation callback failed",location);
      throw;
    }
    catch(...){++state->fatalExits;state->close();throw;}
  });
}
NativeTaskSessionStats NativeTaskSession::statistics(){
  auto state=impl;
  return sessionOperation({},[&]{
    state->requireIdle(true);NativeTaskSessionStats result{{},state->invocations,state->sourceErrors,state->fatalExits,state->context.closed()};
    if(!result.closed&&state->initialized){Impl::Operation operation(*state);RequestScope request(state->context,1000000,5000);
      try{result.heap=managedCellHeapStats();}catch(...){state->close();throw;}
    }
    return result;
  });
}
CellCollection NativeTaskSession::collect(){
  auto state=impl;
  return sessionOperation({},[&]{
    Impl::Operation operation(*state);RequestScope request(state->context,1000000,5000);
    try{state->initialize();return collectManagedCells();}catch(...){state->close();throw;}
  });
}
bool NativeTaskSession::cancel()noexcept{auto state=impl;return state->context.cancel();}
bool NativeTaskSession::closed()const noexcept{return impl->context.closed();}
void NativeTaskSession::close(){auto state=impl;sessionOperation({},[&]{state->close();});}
void NativeTaskSession::finish(){
  auto state=impl;
  sessionOperation({},[&]{state->requireIdle(true);state->close();
    while(state->retirement&&!state->retirement->ready())std::this_thread::sleep_for(std::chrono::milliseconds(1));
  });
}
}
