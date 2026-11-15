#include "nex/managed_references.h"
#include "nex_cells.h"
namespace nex {
llvm::json::Object managedReferencesCapability(){
  const nexrt::CellHeapLimits limits;
  return llvm::json::Object{{"schema","nex.managed-references/1"},{"status","private_runtime_kernel"},
    {"introduced_toolchain","0.249.0"},{"public_source_enabled",false},
    {"source_type_enabled",false},{"state_effect_enabled",false},{"source_language_changed",false},
    {"guide","docs/managed-references-design.md"},{"header","runtime/nex_cells.h"},
    {"implementation","runtime/nex_cells.cpp"},{"test","tests/cells.cpp"},
    {"heap_lifetime","one execution context; close invalidates its cells"},
    {"mutation","thread-affine; foreign heap and thread operations rejected"},
    {"identity","same live cell object; structural payload equality does not identify cells"},
    {"snapshots","read retains an immutable value snapshot; write replaces only the cell payload"},
    {"collection","trace external strong roots after subtracting registry/graph ownership; reclaim unreachable cycles"},
    {"teardown","detach mutable edges and release registry in reverse immutable-adoption order; no collector graph workspace allocated at close"},
    {"payloads",llvm::json::Array{"i64","bool","finite f64","str","bytes","list","record","result","enum","closure","same-heap cell"}},
    {"owned_capability_payloads",false},{"parallel_transfer",false},{"task_transfer",false},
    {"limit_accounting","registered cells, all adopted data nodes, and all Value payload slots; includes retired payloads until collection; not a byte-memory bound"},
    {"defaults",llvm::json::Object{{"maximum_cells",int64_t(limits.maximumCells)},
      {"maximum_nodes",int64_t(limits.maximumNodes)},{"maximum_edges",int64_t(limits.maximumEdges)}}},
    {"reference_interpreter_source_enabled",false},{"native_source_enabled",false},{"typescript_source_enabled",false},
    {"pending",llvm::json::Array{"checked reference types and state effect","versioned grammar and explicit history-preserving migration",
      "reference/native/TypeScript lowering","native entry/module/ABI ownership","owned capability integration",
      "cross-thread sharing, monitors and atomics","source debugger/profile integration","weak references and finalization semantics",
      "matching complete compiler/platform/SDK qualification"}}};
}
}
