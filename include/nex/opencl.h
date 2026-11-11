#pragma once
#include "nex/language.h"

namespace nex {
struct OpenCLSourceFunction {
  std::string name,symbol,hash;
  Span source;
  unsigned firstLine=0,lastLine=0;
};
struct OpenCLSource {
  std::string source,entry,inputLayout,resultType;
  std::vector<std::string> parameterTypes;
  std::vector<OpenCLSourceFunction> functions;
};
// OpenCL C source emission only. Compilation, dispatch and device authority belong to a trusted host.
OpenCLSource emitOpenCL(const Program &,const std::string &entry="main",
                      const std::string &inputLayout="rows");
}
