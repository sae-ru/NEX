#pragma once
#include "nex/language.h"
#include "nex_task_limits.h"

namespace nex {
inline nexrt::TaskExecutionLimits parseTaskLimitsJSON(const llvm::json::Value &value,
                                                     const std::string &code="E_OPTION") {
  auto object=value.getAsObject();
  if(!object||object->empty()||object->size()>3)throw Error(code,"task_limits requires a nonempty object with steps, timeout_ms or workers");
  nexrt::TaskExecutionLimits result;
  for(const auto &[key,item]:*object){
    auto number=item.getAsUINT64();
    uint64_t maximum=key=="steps"?nexrt::maximumTaskExecutionSteps:
      key=="timeout_ms"?nexrt::maximumTaskExecutionTimeoutMs:
      key=="workers"?nexrt::maximumTaskExecutionWorkers:0;
    if(!maximum||!number||*number<1||uint64_t(*number)>maximum)
      throw Error(code,"invalid task_limits field or integer: "+key.str());
    if(key=="steps")result.steps=uint64_t(*number);
    else if(key=="timeout_ms")result.timeoutMs=uint64_t(*number);
    else result.workers=unsigned(*number);
  }
  return result;
}
inline llvm::json::Object taskLimitsJSON(const nexrt::TaskExecutionLimits &limits) {
  return llvm::json::Object{{"steps",int64_t(limits.steps)},{"timeout_ms",int64_t(limits.timeoutMs)},
          {"workers",int64_t(limits.workers)}};
}
inline void appendTaskLimitArguments(std::vector<std::string> &arguments,
                                    const nexrt::TaskExecutionLimits &limits) {
  arguments.insert(arguments.end(),{"--task-steps",std::to_string(limits.steps),
    "--task-timeout-ms",std::to_string(limits.timeoutMs),"--task-workers",std::to_string(limits.workers)});
}
inline nexrt::TaskExecutionLimits taskEffectiveLimits(const nexrt::TaskExecutionLimits &limits,
                                                     const std::vector<std::string> &arguments) {
  std::vector<const char*> argv;for(const auto &argument:arguments)argv.push_back(argument.c_str());
  try{return nexrt::parseTaskExecutionArguments(limits,int(argv.size()),argv.data());}
  catch(const nexrt::DataError &error){throw Error(error.code,error.what());}
}
inline llvm::json::Object taskExecutionJSON(const nexrt::TaskExecutionLimits &configured,
                                          const nexrt::TaskExecutionLimits &effective,
                                          const std::string &backend,unsigned supervisorSeconds=0) {
  llvm::json::Object result{{"configured",taskLimitsJSON(configured)},
    {"effective",taskLimitsJSON(effective)},{"backend",backend},
    {"executor_workers",int64_t(backend=="native"?effective.workers:1)},
    {"step_model",backend=="native"?"native resume and runtime polls":
      backend=="reference"?"checked AST actions and atoms":"generator and checkpoint work"},
    {"cooperative_deadline",true},{"identical_step_thresholds",false}};
  if(supervisorSeconds)result["supervisor_timeout_seconds"]=int64_t(supervisorSeconds);
  return result;
}
}
