#pragma once
#include "nex_error.h"
#include <cstdint>
#include <optional>
#include <string_view>

namespace nexrt {
inline constexpr uint64_t maximumTaskExecutionSteps=UINT64_C(9007199254740991);
inline constexpr uint64_t maximumTaskExecutionTimeoutMs=3600000;
inline constexpr unsigned maximumTaskExecutionWorkers=16;
struct TaskExecutionLimits {
  uint64_t steps=1000000,timeoutMs=5000;
  unsigned workers=16;
  bool operator==(const TaskExecutionLimits &)const=default;
};
inline bool validTaskExecutionLimits(const TaskExecutionLimits &limits)noexcept{
  return limits.steps&&limits.steps<=maximumTaskExecutionSteps&&
    limits.timeoutMs&&limits.timeoutMs<=maximumTaskExecutionTimeoutMs&&
    limits.workers&&limits.workers<=maximumTaskExecutionWorkers;
}
inline std::optional<uint64_t> parseTaskLimitDecimal(std::string_view text,uint64_t maximum,uint64_t minimum=1)noexcept{
  if(text.empty()||minimum>maximum)return std::nullopt;
  uint64_t value=0;
  for(char c:text){
    if(c<'0'||c>'9')return std::nullopt;
    auto digit=uint64_t(c-'0');
    if(digit>maximum||value>(maximum-digit)/10)return std::nullopt;
    value=value*10+digit;
  }
  if(value<minimum)return std::nullopt;
  return value;
}
// The image supplies immutable ceilings. Literal process arguments can lower
// them; neither the compiler nor the standalone runtime reads ambient limits.
// Unknown application arguments retain their ordinary meaning. Reserve the
// entire --nex-task- prefix so misspellings cannot silently run with defaults.
inline TaskExecutionLimits parseTaskExecutionArguments(const TaskExecutionLimits &ceilings,int argc,const char *const *argv){
  if(!validTaskExecutionLimits(ceilings))throw DataError("E_OPTION","invalid compiled task execution limits");
  if(argc<0||(argc&&!argv))throw DataError("E_OPTION","invalid task application argument vector");
  auto result=ceilings;bool steps=false,timeout=false,workers=false;
  for(int i=0;i<argc;++i){
    if(!argv[i])throw DataError("E_OPTION","null task application argument");
    if(!i)continue;
    std::string_view flag(argv[i]);
    if(!flag.starts_with("--nex-task-"))continue;
    bool *seen=nullptr;uint64_t maximum=0;
    if(flag=="--nex-task-steps"){seen=&steps;maximum=ceilings.steps;}
    else if(flag=="--nex-task-timeout-ms"){seen=&timeout;maximum=ceilings.timeoutMs;}
    else if(flag=="--nex-task-workers"){seen=&workers;maximum=ceilings.workers;}
    else throw DataError("E_OPTION","unknown reserved task application option: "+std::string(flag));
    if(*seen)throw DataError("E_OPTION","duplicate task application option: "+std::string(flag));
    *seen=true;
    if(i+1>=argc||!argv[i+1])throw DataError("E_OPTION","missing decimal value for "+std::string(flag));
    auto value=parseTaskLimitDecimal(argv[++i],maximum);
    if(!value)throw DataError("E_OPTION",std::string(flag)+" requires decimal 1.."+std::to_string(maximum)+"; application arguments may only lower compiled task limits");
    if(seen==&steps)result.steps=*value;
    else if(seen==&timeout)result.timeoutMs=*value;
    else result.workers=static_cast<unsigned>(*value);
  }
  return result;
}
}
