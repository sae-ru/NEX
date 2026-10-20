#pragma once
#include "nex/language.h"

namespace nex {
// Physical project checking with explicit in-memory source overlays. This path
// never initializes a Store, materializes source or executes a source function.
llvm::json::Value editorAnalysis(const std::string &entry,const std::string &root,
    const llvm::json::Value &overlay);
}
