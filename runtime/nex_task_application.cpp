#include "nex_task_application.h"
#include <limits>

namespace nexrt {
namespace {
TaskBody applicationTask(TaskGroup &group,Value,Value closure,const void *context){
  if(closure.tag!=Value::Object||!closure.object||closure.object->kind!=Data::Closure||!closure.object->taskCode)
    throw DataError("E_TASK_STATE","application task descriptor is absent");
  auto &code=*static_cast<const TaskCodeDescriptor*>(closure.object->taskCode);
  if(!context)throw DataError("E_TASK_STATE","application task host context is absent");
  auto host=*static_cast<const std::shared_ptr<const TaskFrameHostContext>*>(context);
  return executeTaskFrame(group,NativeTaskFrame(code,{},closure,std::move(host)));
}
struct ConfiguredTaskHost {
  std::unique_ptr<FileScope> files;
  std::shared_ptr<TaskFrameHostContext> context;
};
ConfiguredTaskHost configuredTaskHost(const TaskCodeDescriptor &code){
  ConfiguredTaskHost result;
  auto context=std::make_shared<TaskFrameHostContext>();

  if(code.requirements&(taskCodeImageFileRead|taskCodeImageFileWrite)){
    if(!inFileScope())result.files=std::make_unique<FileScope>(true);
    if(code.requirements&taskCodeImageFileRead)context->fileReads=captureFileReadGrant(true);
    if(code.requirements&taskCodeImageFileWrite)context->fileWrites=captureFileWriteGrant(true);
  }
  if(code.requirements&taskCodeImageForeign){
#ifdef NEX_FOREIGN_ENABLED
    context->foreign=captureForeignScope(true);
    context->foreignCleanup=std::make_shared<ResourceExecutor>(ResourceExecutorLimits{4096,64,8*1048576});
#else
    throw DataError("E_TASK_STATE","task foreign image has no linked foreign adapter");
#endif
  }
  if(code.requirements&taskCodeImageFileStream){
#ifdef NEX_FOREIGN_ENABLED
    context->fileCleanup=context->foreignCleanup;
#endif
    if(!context->fileCleanup)context->fileCleanup=std::make_shared<ResourceExecutor>(ResourceExecutorLimits{64,64,8*1048576});
  }
  result.context=std::move(context);return result;
}
struct HttpTaskInvocation {
  const TaskCodeDescriptor &code;
  std::shared_ptr<const TaskFrameHostContext> host;
};
TaskBody httpRequestTask(TaskGroup &group,Value request,Value,const void *context){
  if(!context)throw DataError("E_TASK_STATE","HTTP task invocation is absent");
  const auto &invocation=*static_cast<const HttpTaskInvocation*>(context);
  return executeTaskFrame(group,NativeTaskFrame(invocation.code,{std::move(request)},Value{},invocation.host));
}
bool httpString(const Value &value){return value.tag==Value::Object&&value.object&&value.object->kind==Data::String;}
void httpRequestValue(const Value &value){
  static const std::vector<std::string> names={"method","path","query","body","user","request_id"};
  if(value.tag!=Value::Object||!value.object||value.object->kind!=Data::Record||value.object->text!="std::http::Request"||value.object->names!=names||value.object->values.size()!=names.size())
    throw DataError("E_TASK_HTTP_REQUEST","HTTP task requires the exact checked Request layout");
  for(const auto &field:value.object->values)if(!httpString(field))
    throw DataError("E_TASK_HTTP_REQUEST","HTTP task Request fields must be strings");
}
void httpResponseValue(const Value &value){
  static const std::vector<std::string> names={"status","body","content_type"};
  if(value.tag!=Value::Object||!value.object||value.object->kind!=Data::Record||value.object->text!="std::http::Response"||value.object->names!=names||value.object->values.size()!=names.size()||
     value.object->values[0].tag!=Value::Integer||!httpString(value.object->values[1])||!httpString(value.object->values[2]))
    throw DataError("E_TASK_HTTP_RESPONSE","HTTP task must return the exact checked Response layout");
}
}
static Handle *executeTaskHttpRequestImpl(const TaskCodeDescriptor &code,Handle *request,
    std::shared_ptr<const TaskFrameHostContext> host,unsigned workers,bool sourceErrors){
  if(!inRequestScope())throw DataError("E_TASK_SCOPE","HTTP task requires its caller's active request scope");
  return hostValue({},[&]{
    if(workers<1||workers>maximumTaskExecutionWorkers)throw DataError("E_OPTION","HTTP task requires1..16 workers");
    if((sourceErrors?!sourceExceptionTaskABI(code.abi):code.abi!=taskCodeStreamABI)||!validTaskCodeRequirements(code.abi,code.requirements)||
       (code.requirements&(taskCodeDeclaredTask|taskCodeServer))!=(taskCodeDeclaredTask|taskCodeServer)||
       code.parameterCount!=1||code.captureCount||code.resultKind!=3)
      throw DataError("E_TASK_HTTP_ABI",sourceErrors?"private source HTTP task requires a private025 server/task Request-to-Response descriptor":"HTTP task requires a server/task ABI5 Request-to-Response descriptor");
    if(!request)throw DataError("E_TASK_HTTP_REQUEST","HTTP task Request handle is absent");
    auto input=readHandle(request);httpRequestValue(input);
    const auto operations=code.requirements&(taskCodeImageFileRead|taskCodeImageFileWrite|taskCodeImageForeign|taskCodeImageFileStream);
    if(operations&&!host)throw DataError("E_TASK_HOST","HTTP task IO requires an explicit captured host context");
#ifndef NEX_FOREIGN_ENABLED
    if(code.requirements&taskCodeImageForeign)throw DataError("E_TASK_HOST","HTTP task image has no linked foreign adapter");
#endif
    if(!host)host=std::make_shared<TaskFrameHostContext>();
    HttpTaskInvocation invocation{code,std::move(host)};
    TaskGroup group(workers,4096,{},bool(operations),sourceErrors);
    if(code.requirements&(taskCodeImageForeign|taskCodeImageFileStream))
      group.enableResourceRegions({},true,bool(code.requirements&taskCodeImageFileStream));
    auto root=group.spawnWithContext(httpRequestTask,&invocation,std::move(input),{});
    auto result=group.join(root);group.finish();httpResponseValue(result);
    return result;
  });
}
Handle *executeTaskHttpRequest(const TaskCodeDescriptor &code,Handle *request,
    std::shared_ptr<const TaskFrameHostContext> host,unsigned workers){return executeTaskHttpRequestImpl(code,request,std::move(host),workers,publicSourceExceptionTaskABI(code.abi));}
Handle *executeSourceExceptionTaskHttpRequest(const TaskCodeDescriptor &code,Handle *request,
    std::shared_ptr<const TaskFrameHostContext> host,unsigned workers){return executeTaskHttpRequestImpl(code,request,std::move(host),workers,true);}
Handle *executeConfiguredSourceExceptionTaskHttpRequest(const TaskCodeDescriptor &code,Handle *request,unsigned workers){
  if(!inRequestScope())throw DataError("E_TASK_SCOPE","HTTP task requires its caller's active request scope");
  auto configured=configuredTaskHost(code);
  return executeSourceExceptionTaskHttpRequest(code,request,configured.context,workers);
}
Handle *executeConfiguredTaskHttpRequest(const TaskCodeDescriptor &code,Handle *request,unsigned workers){
  if(!inRequestScope())throw DataError("E_TASK_SCOPE","HTTP task requires its caller's active request scope");
  auto configured=configuredTaskHost(code);
  return executeTaskHttpRequest(code,request,configured.context,workers);
}
int64_t executeTaskApplication(const TaskCodeDescriptor &code,SourceLocation location){
  return executeTaskApplication(code,TaskExecutionLimits{},location);
}
static int64_t executeTaskApplicationImpl(const TaskCodeDescriptor &code,const TaskExecutionLimits &limits,SourceLocation location,bool sourceErrors){
  return hostOperation(location,[&]() -> int64_t {
    if(!validTaskExecutionLimits(limits))throw DataError("E_OPTION","invalid task execution limits");
    // NativeTaskFrame performs the full ABI/slot validation before scheduling.
    // The public process entry has the same no-argument i64/unit contract as an
    // ordinary executable, regardless of whether its entry suspends.
    if(code.parameterCount||code.captureCount||(code.resultKind!=0&&code.resultKind!=4))
      throw DataError("E_ENTRY","task application entry must take no arguments and return i64 or unit");
    if(!validTaskCodeRequirements(code.abi,code.requirements)||sourceExceptionTaskABI(code.abi)!=sourceErrors)
      throw DataError("E_TASK_STATE","invalid task application descriptor ABI/requirements");
#ifdef NEX_TASK_PROFILE_ENABLED
    taskProfileEffectiveLimits(limits);
#endif
    RequestScope request(limits.steps,limits.timeoutMs);
    auto configured=configuredTaskHost(code);auto context=configured.context;
    TaskGroup group(limits.workers,4096,{},bool(code.requirements&(taskCodeImageFileRead|taskCodeImageFileWrite|taskCodeImageForeign|taskCodeImageFileStream)),sourceErrors);
    if(code.requirements&(taskCodeImageForeign|taskCodeImageFileStream))group.enableResourceRegions({},true,bool(code.requirements&taskCodeImageFileStream));
    auto environment=std::make_shared<Data>(Data::Closure);
    environment->taskCode=&code;
    std::shared_ptr<const TaskFrameHostContext> retained=context;
    auto root=group.spawnWithContext(applicationTask,&retained,{},Value(std::move(environment)));
    auto result=group.join(root);
    group.finish();
    if(result.tag!=Value::Integer||(code.resultKind==4&&result.scalar!=0))
      throw DataError("E_TASK_STATE","task application returned an invalid process result");
    // Local Value, TaskGroup and RequestScope destruct in that order. Every
    // worker, parked frame and owned scope is gone before application_finish
    // checks the process-wide managed-value invariant.
    return result.scalar;
  });
}
int64_t executeTaskApplication(const TaskCodeDescriptor &code,const TaskExecutionLimits &limits,SourceLocation location){return executeTaskApplicationImpl(code,limits,location,publicSourceExceptionTaskABI(code.abi));}
int64_t executeSourceExceptionTaskApplication(const TaskCodeDescriptor &code,const TaskExecutionLimits &limits,SourceLocation location){return executeTaskApplicationImpl(code,limits,location,true);}
}
extern "C" {
int64_t nex_task_source_exception_application_execute_limits_at(const nexrt::TaskCodeDescriptor *code,int64_t argc,const char *const *argv,int64_t steps,int64_t timeoutMs,int64_t workers,const nexrt::NativeSite *site){
  return nexrt::hostOperation({0,site},[&]() -> int64_t {
    if(!code||argc<0||argc>std::numeric_limits<int>::max()||steps<=0||timeoutMs<=0||workers<=0||workers>nexrt::maximumTaskExecutionWorkers)throw nexrt::DataError("E_OPTION","invalid private source-task application arguments");
    auto limits=nexrt::parseTaskExecutionArguments({uint64_t(steps),uint64_t(timeoutMs),unsigned(workers)},int(argc),argv);
    return nexrt::executeSourceExceptionTaskApplication(*code,limits,{0,site});
  });
}
int64_t nex_task_application_execute_at(const nexrt::TaskCodeDescriptor *code,const nexrt::NativeSite *site){
  auto location=nexrt::SourceLocation{0,site};
  return nexrt::hostOperation(location,[&]() -> int64_t {
    if(!code)throw nexrt::DataError("E_ENTRY","task application descriptor is absent");
    return nexrt::executeTaskApplication(*code,location);
  });
}
int64_t nex_task_application_execute(const nexrt::TaskCodeDescriptor *code){return nex_task_application_execute_at(code,nullptr);}
int64_t nex_task_application_execute_limits_at(const nexrt::TaskCodeDescriptor *code,int64_t argc,const char *const *argv,int64_t steps,int64_t timeoutMs,int64_t workers,const nexrt::NativeSite *site){
  auto location=nexrt::SourceLocation{0,site};
  return nexrt::hostOperation(location,[&]() -> int64_t {
    if(steps<=0||timeoutMs<=0||workers<=0||workers>nexrt::maximumTaskExecutionWorkers||argc<0||argc>std::numeric_limits<int>::max())
      throw nexrt::DataError("E_OPTION","invalid compiled task limits or application argument count");
    const nexrt::TaskExecutionLimits configured{uint64_t(steps),uint64_t(timeoutMs),unsigned(workers)};
    auto limits=nexrt::parseTaskExecutionArguments(configured,int(argc),argv);
#ifdef NEX_TASK_PROFILE_ENABLED
    nexrt::taskProfileLimits(configured,limits);
#endif
    if(!code)throw nexrt::DataError("E_ENTRY","task application descriptor is absent");
    return nexrt::executeTaskApplication(*code,limits,location);
  });
}
int64_t nex_task_application_execute_limits(const nexrt::TaskCodeDescriptor *code,int64_t argc,const char *const *argv,int64_t steps,int64_t timeoutMs,int64_t workers){
  return nex_task_application_execute_limits_at(code,argc,argv,steps,timeoutMs,workers,nullptr);
}
}
