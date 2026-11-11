#pragma once
#include "nex/language.h"

namespace nex {
// Byte offsets classified by the actual current-language parser, never by a
// second grammar. In particular a type-closing >= contributes a > and an =.
struct SourceFormatHints {
  std::set<size_t> genericOpens, genericCloses, prefixes, effectBraces;
};
SourceFormatHints sourceFormatHints(const std::string &source,const std::string &file);
std::string formatSource(const std::string &source,const std::string &file);
void replaceFormattedSource(const std::string &file,const std::string &original,
                            const std::string &formatted);
llvm::json::Value sourceFormattingCapability();
}
