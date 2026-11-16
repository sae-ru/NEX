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
void bindManagedReferencePrototypeTypes(Program &program){
  if(!supportsManagedReferences(program))throw Error("E_LANGUAGE_VERSION","private reference type binding requires its explicit frontend");
  // The public module loader scopes these binders while resolving modules. The
  // private parser has no loader: sharing a raw F/T between declarations lets a
  // later kind or bound overwrite an earlier one, and leaves trait Self unbound.
  std::map<std::string,std::string> parameters;
  std::set<std::string> traitMethods;
  std::set<std::string> projections;
  for(const auto &trait:program.traits)for(const auto &[name,bounds]:trait.associated)projections.insert(trait.name+"::"+name);
  auto scope=[&](auto &declaration,const std::string &name){
    parameters.clear();
    for(auto &parameter:declaration.typeParameters){auto local=parameter;parameter=program.module+"::"+name+"::"+local;parameters.emplace(local,parameter);}
  };
  std::function<void(Type&)> type=[&](Type &value){
    if(value.kind==Type::Parameter){
      auto found=parameters.find(value.name);
      if(found==parameters.end())throw Error("E_GENERIC_SCOPE","type parameter is outside its declaration");
      value.name=found->second;
    }
    if(value.kind==Type::Record&&projections.contains(value.name))value.kind=Type::Projection;
    if(value.element){value.element=std::make_shared<Type>(*value.element);type(*value.element);}
    for(auto &argument:value.arguments)type(argument);
  };
  std::function<void(E)> expression;
  std::function<void(const std::vector<S>&)> block;
  expression=[&](E value){if(value){
    type(value->annotation);
    for(auto &argument:value->typeArguments)type(argument);
    for(auto &argument:value->methodArguments)type(argument);
    if(!value->methodArguments.empty()){
      if(!traitMethods.contains(value->text))throw Error("E_GENERIC_ARITY","second type argument list requires a trait method",value->span);
      value->typeArguments.insert(value->typeArguments.end(),value->methodArguments.begin(),value->methodArguments.end());value->methodArguments.clear();
    }
    if(value->lambda){auto &lambda=*value->lambda;type(lambda.result);for(auto &parameter:lambda.params)type(parameter.type);block(lambda.body);}
    for(auto &argument:value->args)expression(argument);
    for(auto &arm:value->arms)block(arm->body);
  }};
  block=[&](const std::vector<S> &body){for(auto &statement:body){
    type(statement->type);expression(statement->expr);
    // A block match shares its arms with its expression; bind them only once.
    if(statement->kind!=Stmt::Match)childBlocks(statement,block);
  }};
  auto signature=[&](Function &function){
    type(function.result);for(auto &parameter:function.params)type(parameter.type);
    for(auto &value:function.typeDefaults)type(value);
  };
  for(auto &trait:program.traits)for(auto &method:trait.methods){
    method.name=trait.name+"::"+method.name;
    traitMethods.insert(method.name);
    scope(method,method.name);parameters["Self"]=trait.name+"::Self";signature(method);
  }
  for(auto &implementation:program.implementations){
    scope(implementation,implementation.name);type(implementation.self);
    for(auto &[name,value]:implementation.associated)type(value);
    for(auto &[name,method]:implementation.methods)for(auto &argument:method.typeArguments)type(argument);
  }
  for(auto &function:program.functions){scope(function,function.name);signature(function);block(function.body);}
  for(auto &structure:program.structures){
    scope(structure,structure.name);for(auto field:structure.members())type(field->type);
    for(auto &value:structure.typeDefaults)type(value);
  }
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
    {"external_snapshot_teardown",llvm::json::Object{{"introduced_toolchain","0.254.0"},
      {"guide","docs/value-retirement.md"},{"test","tests/value_retirement.py"},
      {"sequential_ordinary_graphs","atomic last-owner retirement; shared live values remain unchanged"},
      {"cleanup_workspace_allocation",false},{"host_subclass_destructors","run before their own child vector is retired"},
      {"runtime_value_graph_edges_stack_bounded",true},
      {"owner_introduced_toolchain","0.255.0"},{"owner_header","runtime/nex_value_owner.h"},
      {"owner_guide","docs/value-owners.md"},{"owner_test","tests/value_owner.cpp"},
      {"owner_context","explicit stack-owned retirement context; no thread-local or image-local queue"},
      {"synchronous_root_retirement",true},{"weak_acquisition","cannot acquire queued or destroying data"},
      {"std_shared_ptr_binary_interchange",false}}},
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
      {"generic_composition",llvm::json::Object{{"introduced_toolchain","0.256.0"},
        {"type_binders","declaration-local identities; same-spelled parameters keep independent kinds and bounds"},
        {"language029",llvm::json::Array{"partial type lambdas","whole-type constructor inference","higher-order kind signatures"}},
        {"traits",llvm::json::Array{"associated projections","static dispatch","method references","generic constructor methods"}},
        {"source_effects","state and typed throws compose with inferred callback effects"},
        {"public_source_enabled",false}}},
      {"native",true},{"typescript",true},{"ordinary_CLI",false},{"archival",false},{"migration",false},
      {"native_introduced_toolchain","0.251.0"},{"native_selection","emitManagedReferencesPrototypeMLIR"},
      {"native_guide","docs/managed-reference-native-prototype.md"},
      {"native_entry","sequential application: unit or i64 process status; same-runtime generated-code fixture"},
      {"native_context","one opaque application-owned heap; source handles retire before heap close on every exit"},
      {"typescript_introduced_toolchain","0.253.0"},{"typescript_selection","emitManagedReferencesPrototypeTypeScript"},
      {"typescript_guide","docs/managed-reference-typescript-prototype.md"},
      {"typescript_entry","sequential execution context: no arguments; unit or immutable wire result in a private JSON-text evaluation envelope"},
      {"typescript_context","explicit expression/lexical/builder/completion roots; one heap across source calls; closed on every exit"},
      {"typescript_heap_kernel",llvm::json::Object{{"introduced_toolchain","0.252.0"},
        {"implementation","web/nex-managed-heap.ts"},{"guide","docs/managed-reference-typescript-heap.md"},
        {"test","tests/managed_heap_typescript.py"},{"source_lowering",true},
        {"rooting","explicit binding, operand, builder and transfer roots; no dependency on host GC timing"},
        {"representation","explicit identity for every immutable data node, including strings; checked boxed value facade"}}},
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
