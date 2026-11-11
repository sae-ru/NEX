#pragma once
#include "nex/language.h"

namespace nex {
struct CliOption {
  std::string name,metavar,description;
  std::vector<std::string> aliases,restrictedCommands;
  bool unique=false;
  std::string restrictionMessage;
};
struct CliCommand {
  std::string name,arguments,description,guide;
  std::vector<std::string> options;
  std::map<std::string,std::vector<std::string>> choices;
  bool quietStatus=false,applicationArguments=false,hidden=false;
};
const std::vector<CliOption> &cliOptions();
const std::vector<CliCommand> &cliCommands();
const CliOption *cliOption(const std::string &name);
const CliCommand *cliCommand(const std::string &name);
const std::map<std::string,std::string> &cliGuides();
llvm::json::Value cliHelp(const std::string &command,const std::string &version,const std::string &build);
std::string cliHelpText(const llvm::json::Value &help);
llvm::json::Value cliComplete(const std::vector<std::string> &words);
std::string cliCompletionScript(const std::string &shell);
llvm::json::Value cliCapability();
}
