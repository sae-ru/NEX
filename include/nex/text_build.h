#pragma once
#include "nex/language.h"
namespace nex {
// Expand the checked str(...) constructor into an ordinary closure/loop. The
// unpublished accumulator is a private list<str> flushed by one runtime join.
E textBuildLambda(const std::vector<Type> &arguments,const std::string &realm,
                  const std::set<std::string> &effects,Span span,int64_t ordinal);
llvm::json::Value textBuildCapability();
}
