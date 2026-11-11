#pragma once
#include "nex/language.h"
namespace nex {
// Expand the checked bytes(...) constructor into an ordinary closure/loop. The
// unpublished accumulator is a private list<i64>; one final conversion validates
// octets and publishes immutable bytes.
E bytesBuildLambda(const std::vector<Type> &arguments,const std::string &realm,
                   const std::set<std::string> &effects,Span span,int64_t ordinal);
llvm::json::Value bytesBuildCapability();
}
