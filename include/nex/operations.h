#pragma once
#include "nex/language.h"
namespace nex {
struct Operation {
  std::string path,parent,role,kind,anchor,content,site,binding,callee;
  unsigned ordinal=0;
  Span span;SourceRange sourceRange;std::string fragment;
  llvm::json::Value definition=nullptr;
  const void *ast=nullptr;
};
std::vector<Operation> operationTree(const Program &program,const Function &function);
llvm::json::Array operationSites(const Program &program,const Function &function);
llvm::json::Array operationSites(const Function &function,const std::vector<Operation> &operations);
// Conservative sibling matching; an empty result entry requests a fresh identity.
std::map<std::string,std::string> matchOperations(const std::vector<Operation> &current,
  const std::vector<Operation> &previous,const std::map<std::string,std::string> &ids);
}
