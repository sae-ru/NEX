#pragma once
#include "nex/language.h"
namespace nex {
struct CudaSourceFunction { std::string name,symbol,hash;Span source;unsigned firstLine=0,lastLine=0; };
struct CudaSource { std::string source,entry,inputLayout,resultType;std::vector<std::string> parameterTypes;std::vector<CudaSourceFunction> functions;bool floatingPoint=false;llvm::json::Value valueABI=nullptr; };
// Source emission only. GPU dispatch requires explicit trusted device authority.
CudaSource emitCuda(const Program &,const std::string &entry,const std::string &inputLayout,unsigned listCapacity=32);
}
