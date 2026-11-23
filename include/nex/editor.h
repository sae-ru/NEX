#pragma once
#include "nex/language.h"

namespace nex {
// A bounded, single-line JSON description of a checked function for an editor.
std::string briefFunctionContext(const Program &program,const std::string &symbol,bool physical);
// Optional source excerpt for the original failing test. Returns null if oversized.
llvm::json::Value testRepairContext(const Program &program, const Function &test,
    const std::vector<std::string> &contextArguments);
// Physical project checking with explicit in-memory source overlays. This path
// never initializes a Store, materializes source or executes a source function.
llvm::json::Value editorAnalysis(const std::string &entry,const std::string &root,
    const llvm::json::Value &overlay,bool references=false,bool details=false);
}
