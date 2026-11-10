#pragma once
#include "nex/language.h"
namespace nex::cuda_experiment {
struct CudaSourceFunction { std::string name,symbol,hash;Span source;unsigned firstLine=0,lastLine=0; };
struct CudaSource { std::string source,entry,inputLayout,resultType;std::vector<std::string> parameterTypes;std::vector<CudaSourceFunction> functions;bool floatingPoint=false; };
// Source-only independent experiment; not part of the installed compiler CLI.
CudaSource emitCuda(const Program &,const std::string &entry,const std::string &inputLayout);
}
