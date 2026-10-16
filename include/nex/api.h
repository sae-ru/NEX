#pragma once
#include "nex/language.h"
namespace nex {
llvm::json::Value describeAPI(const Program &program);
llvm::json::Value generateAPI(const Program &program,const std::string &directory);
}
