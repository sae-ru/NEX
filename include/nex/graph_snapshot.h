#pragma once
#include "llvm/Support/JSON.h"
#include <string>
namespace nex {
llvm::json::Value createGraphSnapshot(const std::string &root,const std::string &directory,unsigned timeoutSeconds=60);
llvm::json::Value recoverGraphSnapshot(const std::string &snapshot,const std::string &directory,unsigned timeoutSeconds=60);
}
