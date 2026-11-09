#pragma once
#include "nex/language.h"

namespace nex {
struct MetalSourceFunction {
  std::string name,symbol,hash;
  Span source;
  unsigned firstLine=0,lastLine=0;
};
struct MetalSource {
  std::string source,entry,inputLayout,resultType;
  std::vector<std::string> parameterTypes;
  std::vector<MetalSourceFunction> functions;
};
// Source emission only. Dispatch and device authority belong to a trusted host.
MetalSource emitMetal(const Program &,const std::string &entry="main",
                      const std::string &inputLayout="rows");
}
