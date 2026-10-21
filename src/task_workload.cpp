#include "nex/task_workload.h"
#include "llvm/ADT/APInt.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/Support/RandomNumberGenerator.h"
#include "llvm/Support/SHA256.h"
#include <array>
#include <filesystem>

namespace nex {
TaskWorkloadState createTaskWorkloadState(const ServerWorkload &workload,
  const std::string &ownedDirectory,unsigned workers){
  if(workers<1||workers>64)throw Error("E_TASK_WORKLOAD","server workers must be1..64");
  auto root=std::filesystem::canonical(ownedDirectory);std::array<uint8_t,32> random;
  if(auto error=llvm::getRandomBytes(random.data(),random.size()))throw Error("E_TASK_WORKLOAD","secure test credential generation failed");
  auto token="nex_"+llvm::toHex(random,true);
  auto sha=llvm::toHex(llvm::SHA256::hash(llvm::arrayRefFromStringRef(token)),true);
  auto auth=root/"auth.json",database=root/"state.sqlite";
  if(std::filesystem::exists(auth)||std::filesystem::exists(database))throw Error("E_TASK_WORKLOAD","server workload requires fresh owned state");
  writeFile(auth.string(),json(llvm::json::Object{{"schema","nex.auth/1"},{"tokens",llvm::json::Array{
    llvm::json::Object{{"user","nex-task-workload"},{"sha256",sha}}}}})+"\n");
  std::filesystem::permissions(auth,std::filesystem::perms::owner_read|std::filesystem::perms::owner_write,std::filesystem::perm_options::replace);
  TaskWorkloadState result;result.arguments={"--auth",auth.string(),"--database",database.string(),"--workers",std::to_string(workers)};
  if(auto name=workload.plan.getString("authorization_env"))result.environment[name->str()]=std::move(token);
  result.description=llvm::json::Object{{"schema","nex.task-workload-state/1"},{"user","nex-task-workload"},
    {"credential_scope","fresh synthetic user per check"},{"database_scope","fresh owned database per check"},
    {"credentials_captured",false},{"database_captured",false},{"server_workers",workers}};
  return result;
}
namespace {
uint64_t limit(const llvm::json::Value &value){
  auto text=value.getAsString();uint64_t n=0;
  if(!text||text->empty()||text->size()>20||(text->size()>1&&text->front()=='0'))throw Error("E_TASK_WORKLOAD","invalid unsigned workload budget");
  for(char c:*text){if(c<'0'||c>'9'||n>(UINT64_MAX-unsigned(c-'0'))/10)throw Error("E_TASK_WORKLOAD","invalid unsigned workload budget");n=n*10+unsigned(c-'0');}return n;
}
}
llvm::json::Array taskWorkloadBudgetFailures(const llvm::json::Object &profile,
  const llvm::json::Object &budget){
  llvm::json::Array failures;auto metrics=profile.getObject("workload");
  auto planned=metrics?metrics->getInteger("planned_requests"):std::nullopt,completed=metrics?metrics->getInteger("completed_requests"):std::nullopt;
  if(!metrics||!metrics->getBoolean("ok").value_or(false)||!metrics->getBoolean("all_expectations_met").value_or(false)||
      !planned||*planned<=0||!completed||*completed!=*planned){
    failures.push_back("workload:incomplete");return failures;
  }
  auto phases=metrics->getArray("phases");if(!phases||phases->empty()){failures.push_back("workload:missing_phases");return failures;}
  for(const auto &[name,field]:std::map<std::string,std::string>{{"max_p95_latency_ns","p95"},{"max_p99_latency_ns","p99"}}){
    if(auto maximum=budget.get(name))for(size_t i=0;i<phases->size();++i){
      auto phase=(*phases)[i].getAsObject();auto latencies=phase?phase->getObject("latency_ns"):nullptr;
      auto observed=latencies?latencies->getInteger(field):std::nullopt;
      if(!observed||*observed<0||uint64_t(*observed)>limit(*maximum))failures.push_back(name+":phase"+std::to_string(i));
    }
  }
  if(auto minimum=budget.get("min_requests_per_second"))for(size_t i=0;i<phases->size();++i){
    auto phase=(*phases)[i].getAsObject();auto count=phase?phase->getInteger("requests"):std::nullopt,duration=phase?phase->getInteger("duration_ns"):std::nullopt;
    if(!count||*count<=0||!duration||*duration<=0||
      llvm::APInt(128,uint64_t(*count)*1000000000ULL).ult(llvm::APInt(128,limit(*minimum))*llvm::APInt(128,uint64_t(*duration))))
      failures.push_back("min_requests_per_second:phase"+std::to_string(i));
  }
  return failures;
}
}
