#include "nex/managed_references.h"
#include "nex_cells.h"
#include <functional>
namespace nex {
bool supportsManagedReferences(const Program &program){return program.sourceLanguage==SourceLanguage::ManagedReferencesPrototype;}
bool containsManagedReference(const Program &program,const Type &type){
  std::set<std::string> seen;
  std::function<bool(const Type&)> visit=[&](const Type &value){
    if(value.kind==Type::Cell||(value.kind==Type::Constructor&&value.name=="$cell"))return true;
    if(value.element&&visit(*value.element))return true;
    for(const auto &argument:value.arguments)if(visit(argument))return true;
    if(value.kind==Type::Record&&program.hasStructure(value.name)&&seen.insert(value.name).second){
      const auto &record=program.structure(value.name);
      for(const auto &argument:record.typeArguments)if(visit(argument))return true;
      for(auto field:record.members())if(visit(field->type))return true;
    }
    return false;
  };return visit(type);
}
const std::set<std::string> &managedReferenceBuiltins(){
  static const std::set<std::string> names={"cell","cell_new","cell_read","cell_write","cell_collect"};return names;
}
llvm::json::Object managedReferencesCapability(){
  const nexrt::CellHeapLimits limits;
  return llvm::json::Object{{"schema","nex.managed-references/1"},{"status","private_checked_reference_candidate"},
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
    {"public_flag_scope","ordinary published source languages; private candidate has its own selection"},
    {"private_candidate",llvm::json::Object{{"introduced_toolchain","0.250.0"},{"language","0.30-refs-prototype"},
      {"selection","parseManagedReferencesPrototype; check; evaluateManagedReferencesPrototype"},
      {"guide","docs/managed-references-prototype.md"},{"grammar","docs/managed-references-prototype.ebnf"},
      {"test","tests/managed_references.cpp"},{"frontend",true},{"reference_interpreter",true},
      {"native",false},{"typescript",false},{"ordinary_CLI",false},{"archival",false},{"migration",false},
      {"input","one unarchived source unit; no imports or endpoints"},
      {"type","cell<T>; identity aliases with immutable payload snapshots"},{"effect","state required for create, read, write and explicit collection"},
      {"operations",llvm::json::Array{"cell_new(value)","cell_new<T>(value)","cell_read(cell)","cell_write(cell,value)","cell_collect()"}},
      {"function_effects",llvm::json::Array{"io","state","throw","inferred effect parameters"}},
      {"entry_result","unit or immutable wire value; cells/closures cannot escape the host context"},
      {"uncaught_source_errors","E_SOURCE_EXCEPTION diagnostic; payload remains within the context"},
      {"threading","sequential; no task or parallel execution"}}},
    {"pending",llvm::json::Array{"public reference types and state effect","versioned public grammar and explicit history-preserving migration",
      "native/TypeScript lowering and source backend agreement","native entry/module/ABI ownership","owned capability integration",
      "cross-thread sharing, monitors and atomics","source debugger/profile integration","weak references and finalization semantics",
      "matching complete compiler/platform/SDK qualification"}}};
}
}
