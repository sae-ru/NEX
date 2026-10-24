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
}
int64_t executeTaskApplication(const TaskCodeDescriptor &code,SourceLocation location){
  return executeTaskApplication(code,TaskExecutionLimits{},location);
}
int64_t executeTaskApplication(const TaskCodeDescriptor &code,const TaskExecutionLimits &limits,SourceLocation location){
  return hostOperation(location,[&]() -> int64_t {
    if(!validTaskExecutionLimits(limits))throw DataError("E_OPTION","invalid task execution limits");
    // NativeTaskFrame performs the full ABI/slot validation before scheduling.
    // The public process entry has the same no-argument i64/unit contract as an
    // ordinary executable, regardless of whether its entry suspends.
    if(code.parameterCount||code.captureCount||(code.resultKind!=0&&code.resultKind!=4))
      throw DataError("E_ENTRY","task application entry must take no arguments and return i64 or unit");
    if(code.abi!=taskCodeABI||(code.requirements&~taskCodeRequirementsMask))
      throw DataError("E_TASK_STATE","invalid task application descriptor ABI/requirements");
#ifdef NEX_TASK_PROFILE_ENABLED
    taskProfileEffectiveLimits(limits);
#endif
    RequestScope request(limits.steps,limits.timeoutMs);
    auto context=std::make_shared<TaskFrameHostContext>();
#ifndef _WIN32
    std::unique_ptr<FileScope> files;
    if(code.requirements&taskCodeImageFileRead){
      if(!inFileScope())files=std::make_unique<FileScope>(true);
      context->fileReads=captureFileReadGrant(true);
    }
#endif
    if(code.requirements&taskCodeImageForeign){
#ifdef NEX_FOREIGN_ENABLED
      context->foreign=captureForeignScope(true);
      context->foreignCleanup=std::make_shared<ResourceExecutor>(ResourceExecutorLimits{4096,64,8*1048576});
#else
      throw DataError("E_TASK_STATE","task foreign image has no linked foreign adapter");
#endif
    }
    TaskGroup group(limits.workers,4096,{},bool(code.requirements&(taskCodeImageFileRead|taskCodeImageForeign)));
    if(code.requirements&taskCodeImageForeign)group.enableResourceRegions({},true);
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
}
extern "C" {
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
