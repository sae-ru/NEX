#include "nex_task_application.h"
#include <limits>

namespace nexrt {
namespace {
TaskBody applicationTask(TaskGroup &group,Value,Value closure){
  if(closure.tag!=Value::Object||!closure.object||closure.object->kind!=Data::Closure||!closure.object->taskCode)
    throw DataError("E_TASK_STATE","application task descriptor is absent");
  auto &code=*static_cast<const TaskCodeDescriptor*>(closure.object->taskCode);
  return executeTaskFrame(group,NativeTaskFrame(code,{},closure));
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
    RequestScope request(limits.steps,limits.timeoutMs);
    TaskGroup group(limits.workers);
    auto environment=std::make_shared<Data>(Data::Closure);
    environment->taskCode=&code;
    auto root=group.spawn(applicationTask,{},Value(std::move(environment)));
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
    auto limits=nexrt::parseTaskExecutionArguments({uint64_t(steps),uint64_t(timeoutMs),unsigned(workers)},int(argc),argv);
    if(!code)throw nexrt::DataError("E_ENTRY","task application descriptor is absent");
    return nexrt::executeTaskApplication(*code,limits,location);
  });
}
int64_t nex_task_application_execute_limits(const nexrt::TaskCodeDescriptor *code,int64_t argc,const char *const *argv,int64_t steps,int64_t timeoutMs,int64_t workers){
  return nex_task_application_execute_limits_at(code,argc,argv,steps,timeoutMs,workers,nullptr);
}
}
