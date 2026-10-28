#pragma once
#include "nex/language.h"
namespace nex {
struct ServerWorkload {
  std::string selection,path,source,sha256,helper,helperSource,helperSha256;
  llvm::json::Object plan;
};
// Readonly data validation: no process, environment-secret read or graph Store.
ServerWorkload inspectServerWorkload(const std::string &root,const std::string &selection);
void validateServerWorkloadAuthority(const ServerWorkload &workload,const std::vector<std::string> &arguments,
  const std::map<std::string,std::string> &environment={});
void verifyServerWorkloadInputs(const ServerWorkload &workload);
class ServerWorkloadRun {
  ServerWorkload workload;
  std::string directory,input,result,runner,python;
public:
  explicit ServerWorkloadRun(const ServerWorkload &workload);
  ~ServerWorkloadRun();
  ServerWorkloadRun(const ServerWorkloadRun&)=delete;
  ServerWorkloadRun &operator=(const ServerWorkloadRun&)=delete;
  std::vector<std::string> launcher()const;
  llvm::json::Value evidence()const;
};
}
