#pragma once
#include "nex/language.h"
namespace nex {
llvm::json::Value parseDebugFrame(const std::string &text);
llvm::json::Value inspectExpression(const std::string &manifest,const llvm::json::Value &frame,
  const std::string &expression,bool plan=false,uint64_t steps=100000,bool demand=false);
}
