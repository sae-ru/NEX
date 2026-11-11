#pragma once
#include "nex/language.h"
namespace nex {
// Expand the checked constructor shape into an ordinary closure/loop. Only its
// unpublished accumulator uses the three compiler-private list operations.
E listBuildLambda(const std::vector<Type> &arguments,Type result,
                  const std::string &realm,const std::set<std::string> &effects,
                  Span span,int64_t ordinal);
llvm::json::Value listBuildCapability();
}
