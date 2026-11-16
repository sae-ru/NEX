#pragma once
#include "nex/language.h"
#include "nex_cells.h"
namespace nex {
struct WebModule;
llvm::json::Object managedReferencesCapability();
const std::set<std::string> &managedReferenceBuiltins();
// Unarchived C++ development entry points. Ordinary CLI versions do not select
// this identity, and ordinary backends/evaluation reject it.
Program parseManagedReferencesPrototype(std::string source,std::string path);
// Give declaration-local type binders distinct identities before checking the
// unarchived single unit. This does not select ordinary module/graph loading.
void bindManagedReferencePrototypeTypes(Program &);
struct ManagedReferenceEvaluation {
  Evaluation evaluation;
  nexrt::CellHeapStats beforeCollection,afterCollection;
};
ManagedReferenceEvaluation evaluateManagedReferencesPrototype(const Program &program,
    const std::string &entry="main",uint64_t stepLimit=1000000,nexrt::CellHeapLimits limits={});
std::string emitManagedReferencesPrototypeMLIR(const Program &program,
    const std::string &entry="main",bool optimized=false,nexrt::CellHeapLimits limits={});
WebModule emitManagedReferencesPrototypeTypeScript(const Program &program,
    const std::string &entry="main",nexrt::CellHeapLimits limits={});
}
