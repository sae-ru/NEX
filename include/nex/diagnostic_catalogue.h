#pragma once
#include "nex/language.h"

namespace nex {
inline constexpr size_t diagnosticExplanationByteLimit=8192;
inline constexpr size_t diagnosticCodeByteLimit=128;
// Compiled read-only guidance, never a project lookup or automatic source edit.
llvm::json::Object diagnosticCatalogueCapability();
llvm::json::Object llmEntryCapability();
llvm::json::Value explainDiagnostic(const std::string &code,const std::string &toolchain,
                                   const std::string &compilerBuild);
llvm::json::Value diagnosticCatalogueIndex(const std::string &toolchain,
                                         const std::string &compilerBuild);
std::string diagnosticExplanationText(const llvm::json::Value &value);
}
