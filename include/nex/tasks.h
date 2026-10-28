#pragma once
#include "nex/project.h"
namespace nex {
struct TaskOptions {
  std::string root,compiler,revision,directory,expectedHash;
  std::map<std::string,std::string> candidates;
  std::map<std::string,std::string> toolchains;
  std::string foreign;
};
llvm::json::Value taskTemplate(const Program &program,const std::string &entry);
llvm::json::Value projectTaskTemplate(const std::string &root,const std::string &manifest,
  const std::string &component,const std::string &configuration);
llvm::json::Value checkTask(const llvm::json::Value &task,const TaskOptions &options);
llvm::json::Value runTask(const llvm::json::Value &task,const TaskOptions &options);
llvm::json::Value replayTask(const std::string &receipt,const TaskOptions &options);
}
