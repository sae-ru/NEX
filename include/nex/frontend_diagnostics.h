#pragma once
#include "nex/language.h"

namespace nex {
// Capture only the inputs actually held by this frontend invocation. No reads,
// store writes, semantic revisions or persistent operation IDs are synthesized.
void attachFrontendDiagnostic(Error &error,
    const std::map<std::string,std::string> &sources,const std::string &entry,
    const std::string &kind,const std::string &phase,bool complete);
// A stopped expression is checked using its captured program language, which
// can differ from the ordinary CLI/default source language.
void attachFrontendDiagnostic(Error &error,
    const std::map<std::string,std::string> &sources,const std::string &entry,
    const std::string &kind,const std::string &phase,bool complete,
    const std::string &sourceLanguage);
llvm::json::Value diagnosticJSON(const Error &error,
    const std::string &toolchain={},const std::string &build={});
}
