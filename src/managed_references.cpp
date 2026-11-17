#include "nex/managed_references.h"
#include "nex/task_frontend.h"
#include "nex_cells.h"
#include <functional>
namespace nex {
bool supportsManagedReferences(const Program &program){return supportsManagedReferences(program.sourceLanguage);}
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
bool usesManagedReferences(const Program &program,const std::set<std::string> &entries){
  if(!supportsManagedReferences(program))return false;
  std::set<std::string> seen;
  std::function<bool(const Function&)> visit=[&](const Function &function){
    if(!seen.insert(function.name).second)return false;
    if(function.effects.contains("state")||containsManagedReference(program,function.result))return true;
    for(const auto &parameter:function.params)if(containsManagedReference(program,parameter.type))return true;
    for(const auto &capture:function.captures)if(containsManagedReference(program,capture.type))return true;
    bool local=false;std::function<void(E)> expression;std::function<void(const std::vector<S>&)> block;
    expression=[&](E value){if(value){local|=containsManagedReference(program,value->type);for(auto argument:value->args)expression(argument);for(auto arm:value->arms)block(arm->body);}};
    block=[&](const auto &statements){for(auto statement:statements){local|=containsManagedReference(program,statement->type);expression(statement->expr);childBlocks(statement,block);}};
    block(function.body);if(local)return true;
    for(const auto &dependency:function.dependencies)if(visit(program.function(dependency)))return true;
    return false;
  };
  for(const auto &entry:entries)if(visit(program.function(entry)))return true;
  return false;
}
bool usesOwnerThreadTasks(const Program &program,const std::set<std::string> &entries){
  if(program.sourceLanguage!=SourceLanguage::References030)return false;
  bool tasks=false;for(const auto &entry:entries)tasks|=usesTaskEffects(program,entry);
  if(!tasks)return false;
  if(usesManagedReferences(program,entries))return true;
  std::set<std::string> seen;std::vector<std::string> pending(entries.begin(),entries.end());
  while(!pending.empty()){
    auto name=std::move(pending.back());pending.pop_back();if(!seen.insert(name).second)continue;
    const auto &function=program.function(name);
    if(function.realm=="server"&&function.effects.contains("db"))return true;
    pending.insert(pending.end(),function.dependencies.begin(),function.dependencies.end());
  }
  return false;
}
void validateManagedReferenceExecution(const Program &program,const std::set<std::string> &entries){
  if(program.sourceLanguage!=SourceLanguage::References030||!usesManagedReferences(program,entries))return;
  std::set<std::string> seen;
  std::function<void(const Function&)> visit=[&](const Function &function){
    if(!seen.insert(function.name).second)return;
    if(usesParallelMap(function))throw Error("E_CELL_CONCURRENCY","language0.30 reference tasks require cooperative owner-thread execution; parallel reference transfer remains pending",function.span);
    for(const auto &dependency:function.dependencies)visit(program.function(dependency));
  };
  for(const auto &entry:entries)visit(program.function(entry));
}
void bindManagedReferencePrototypeTypes(Program &program){
  if(program.sourceLanguage!=SourceLanguage::ManagedReferencesPrototype)throw Error("E_LANGUAGE_VERSION","private reference type binding requires its explicit frontend");
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
  return llvm::json::Object{{"schema","nex.managed-references/1"},{"status","source030_cli_development"},
    {"introduced_toolchain","0.249.0"},{"public_source_enabled",true},
    {"source_type_enabled",true},{"state_effect_enabled",true},{"source_language_changed",false},
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
    {"payloads",llvm::json::Array{"i64","bool","finite f64","str","bytes","list","record","result","enum","closure","same-heap cell","genuine file owner","genuine external owner"}},
    {"owned_capability_payloads",true},{"parallel_transfer",false},{"task_transfer",true},
    {"owned_payloads",llvm::json::Object{{"introduced_toolchain","0.260.0"},
      {"guide","docs/managed-reference-owned-payloads.md"},{"test","tests/managed_cell_resources.cpp"},
      {"source_test","tests/managed_reference_resources.py"},
      {"ownership","registry retains genuine resource wrappers; immutable snapshots retain their original aliases"},
      {"authority","existing independent file/foreign/request domains and explicit close; retention never renews authority"},
      {"collection","resource wrappers are leaf data nodes; reclaim unreachable visible cell/closure cycles; last actual resource owner settles physical cleanup"},
      {"cleanup","operation pins heap state; callback reentry is rejected; close during collection invalidates then defers registry teardown"},
      {"limits","resource quotas remain independent; garbage collection is not prompt finalization or a hard pause bound"},
      {"opaque_cycles","native objects are not traced; host-held source values count as external roots"},
      {"source_finalizers",false},{"task_payloads",false},{"browser_resource_payloads",false}}},
    {"limit_accounting","registered cells, all adopted data nodes, and all Value payload slots; includes retired payloads until collection; not a byte-memory bound"},
    {"defaults",llvm::json::Object{{"maximum_cells",int64_t(limits.maximumCells)},
      {"maximum_nodes",int64_t(limits.maximumNodes)},{"maximum_edges",int64_t(limits.maximumEdges)}}},
    {"reference_interpreter_source_enabled",true},{"native_source_enabled",true},{"typescript_source_enabled",true},
    {"public_flag_scope","explicit030 projects; retained028/029 preserve their source versions"},
    {"source030_development",llvm::json::Object{{"introduced_toolchain","0.262.0"},{"language","0.30"},
      {"reference_tasks",llvm::json::Object{{"introduced_toolchain","0.268.0"},
        {"selection","evaluateManagedTaskReferencePrototype"},{"guide","docs/reference-tasks.md"},
        {"test","tests/reference_tasks.cpp"},{"boundary_test","tests/reference_tasks_boundaries.py"},
        {"frontend_state_callbacks",true},{"caller_state_required",true},
        {"reference_interpreter",true},{"machine","independent checked AST continuations"},
        {"context","one owned thread-affine heap across captures, waits, channels and typed errors"},
        {"execution_workers",int64_t(1)},{"root_result","unit or ordinary immutable wire value"},
        {"cleanup","close before root resource retirement; also close on fatal/control/observer failure"},
        {"resource_authority","existing task-region transfer and revocation; retention does not renew authority"},
        {"public_source_enabled",false},{"ordinary_CLI",false},{"native",false},{"typescript",false},
        {"TaskIR",false},{"parallel_transfer",false},{"stable_public_ABI",false}}},
      {"native_tasks",llvm::json::Object{{"introduced_toolchain","0.269.0"},
        {"selection","emitManagedReferenceTasksDevelopmentNative"},{"guide","docs/reference-tasks.md"},
        {"test","tests/native_reference_tasks.py"},{"runtime_test","tests/owner_task_runtime.cpp"},
        {"reference_oracle","evaluateManagedTaskReferencePrototype"},
        {"native",true},{"TaskIR_lowering",true},{"TaskIR_reference_execution",false},
        {"task_ABI","0x4e45585400003001"},{"published_task_ABI_unchanged",int64_t(7)},
        {"execution","cooperative source continuations on the enclosing request owner thread"},
        {"source_workers",int64_t(1)},{"IO_workers","existing raw completion/lease protocol; no cells"},
        {"heap","borrow enclosing request context across resumes; keep caller handles and state alive"},
        {"cleanup","owned frames retire before publication; collect retired source cycles outside scheduler locks"},
        {"resource_authority","existing task-region ownership and explicit transfer; cells do not renew authority"},
        {"entry","standalone no-argument unit/i64 application"},
        {"public_source_enabled",false},{"ordinary_CLI",false},{"typescript",false},
        {"parallel_transfer",false},{"persistent_UI_context",false},{"stable_public_ABI",false},
        {"SDK_delivery_accepted",false},{"full_platform_acceptance",false}}},
      {"typescript_tasks",llvm::json::Object{{"introduced_toolchain","0.270.0"},
        {"selection","emitManagedReferenceTasksDevelopmentTypeScript"},
        {"guide","docs/reference-tasks.md"},
        {"test","tests/typescript_reference_tasks.py"},
        {"reference_oracle","evaluateManagedTaskReferencePrototype"},
        {"typescript",true},
        {"source_map","nex.private-typescript-reference-tasks/1"},
        {"checked_revision",true},
        {"execution","cooperative generator continuations on the JavaScript owner thread"},
        {"source_workers",int64_t(1)},
        {"heap","one owned heap per invocation; explicit per-job scope and completion roots"},
        {"scheduler_roots","pending callbacks, future results, channel buffers and source errors"},
        {"cleanup","retire lanes, scheduler roots and heap on return, fatal, cancellation and host observer failure"},
        {"entry","standalone no-argument unit or immutable wire value"},
        {"host_IO",false},
        {"public_source_enabled",false},
        {"ordinary_CLI",false},
        {"parallel_transfer",false},
        {"persistent_UI_context",false},
        {"stable_public_ABI",false},
        {"SDK_delivery_accepted",false},
        {"full_platform_acceptance",false}}},
      {"persistent_UI",llvm::json::Object{{"introduced_toolchain","0.272.0"},
        {"public_source_enabled",true},{"ordinary_CLI",true},{"source_language","0.30"},
        {"guide","docs/persistent-ui.md"},{"test","tests/persistent_ui.py"},
        {"example","examples/persistent-ui/main.nex"},
        {"selection","nex web/build --target web; reachable cells or task effects in030 UI entries"},
        {"typescript_map","nex.typescript-application/1"},
        {"heap","one application-owned heap; source state stays opaque across serialized invocations"},
        {"source_workers",int64_t(1)},{"maximum_pending_events",int64_t(256)},
        {"effects",llvm::json::Array{"state","task","throw"}},
        {"initial_order",llvm::json::Array{"initial","title","view"}},
        {"event_order",llvm::json::Array{"update","commands","worker_commands","title","view"}},
        {"structured_tasks","joined before view publication; wire HTTP/Worker responses become later events"},
        {"host_boundary","copied checked immutable wire events/views/commands; no live State export"},
        {"cleanup","close pending events, source frames and application heap on close, abort, source/fatal/host failure"},
        {"controls",llvm::json::Array{"steps","timeoutMs","workers","signal","complete"}},
        {"task_capability_state",false},{"parallel_transfer",false},{"worker_reference_transfer",false},
        {"source_host_IO",false},{"native_persistent_application",false},
        {"retained_synchronous_UI",true},{"source_version_changed",false},
        {"SDK_delivery_accepted",false},{"full_platform_acceptance",false}}},
      {"native_providers",llvm::json::Object{{"introduced_toolchain","0.275.0"},
        {"public_source_enabled",true},{"ordinary_CLI",true},{"source_language","0.30"},
        {"guide","docs/reference-task-providers.md"},{"test","tests/reference_task_providers.py"},
        {"execution","one application-owned heap and owner-thread executor across checked code-only images"},
        {"selection","propagate ABI8 across every connected binary component when reachable030 source uses references"},
        {"record_schema","nex.native-task-provider/17"},{"record_schema_file","llm/native-reference-task-provider.schema.json"},
        {"debug_record_schema","nex.native-task-provider/18"},{"debug_plan_schema","nex.project-task-linkage/18"},
        {"logical_debugging",true},{"profiling",true},{"debug_guide","docs/reference-provider-debugging.md"},
        {"profile_record_schema","nex.native-task-provider/19"},{"profile_plan_schema","nex.project-task-linkage/19"},
        {"profile_guide","docs/reference-task-profiling.md"},
        {"static_plan_schema","nex.project-static-task-linkage/6"},{"shared_plan_schema","nex.project-task-linkage/17"},
        {"plan_schema_file","llm/project-reference-task-linkage.schema.json"},
        {"execution_task_ABI",int64_t(8)},{"requirements_mask",int64_t(16159)},
        {"static",true},{"fixed_shared",true},{"mixed",true},{"source_workers",int64_t(1)},
        {"profiles",llvm::json::Array{"debug","release","profile"}},
        {"source_required",true},{"checked_capture_replay",true},{"retained_ABI7",true},
        {"callable_exports",false},{"imported_function_values",false},{"external_authority_exports",false},
        {"parallel_transfer",false},{"HTTP_project_providers",false},{"runtime_unload",false},
        {"logical_debug_profile",true},{"stable_public_ABI",false},
        {"SDK_delivery_accepted",false},{"full_platform_acceptance",false}}},
      {"native_host_sessions",llvm::json::Object{{"introduced_toolchain","0.276.0"},
        {"guide","docs/native-task-sessions.md"},{"test","tests/native_task_sessions.py"},
        {"API","nexrt::NativeTaskSession"},{"header","runtime/nex_task_session.h"},
        {"matching_runtime_CXX",true},{"checked_source_exports",true},
        {"execution_task_ABI",int64_t(8)},{"source_workers",int64_t(1)},
        {"heap","one application-owned heap across serialized joined invocations"},
        {"controls","fresh step budget, deadline and cancellation callback per invocation; idle time is excluded"},
        {"typed_source_error","retain returned payload and keep session usable"},
        {"fatal_exit","close the application context before host retry"},
        {"resources","explicit persistent host grants; promote returned result/error owners only"},
        {"cancel_thread_safe",true},{"public_source_enabled",false},{"new_source_syntax",false},
        {"stable_public_ABI",false},{"native_UI_controller",false},{"parallel_transfer",false},
        {"runtime_unload",false},{"SDK_delivery_accepted",false},{"full_platform_acceptance",false}}},
      {"native_task_profiling",llvm::json::Object{{"introduced_toolchain","0.279.0"},
        {"guide","docs/reference-task-profiling.md"},{"test","tests/task_provider_profile.py"},
        {"source_language","0.30"},{"execution_task_ABI",int64_t(8)},
        {"ordinary_CLI",true},{"standalone",true},{"provider_images",true},
        {"selection","nex profile FILE; nex project --kind profile with a profile configuration"},
        {"source_workers",int64_t(1)},{"one_application_heap",true},
        {"single_image_report_schema","nex.profile/2"},{"provider_report_schema","nex.profile/3"},
        {"profile_record_schema","nex.native-task-provider/19"},{"profile_plan_schema","nex.project-task-linkage/19"},
        {"source_calls",true},{"source_CPU_and_active_elapsed",true},{"logical_lifetime",true},
        {"memory","shallow Handle/Data allocations; excludes heap registry/index backing, dynamic payload buffers and total RAM"},
        {"native_HTTP",true},{"native_HTTP_scope","standalone owner-thread server with a pinned HTTP workload"},
        {"native_HTTP_test","tests/server_workload.py"},{"simultaneous_logical_debug",false},{"parallel_transfer",false},
        {"SDK_delivery_accepted",false},{"full_platform_acceptance",false}}},
      {"native_task_debugging",llvm::json::Object{{"introduced_toolchain","0.277.0"},
        {"source_language","0.30"},{"ordinary_CLI",true},{"standalone",true},
        {"guide","docs/reference-task-debugging.md"},{"test","tests/task_debugging.py"},
        {"selection","nex debug --kind lldb|nex-dap; debug-profile source-only task entry"},
        {"execution_task_ABI",int64_t(8)},{"catalog_ABI",int64_t(1)},
        {"logical_steps",true},{"scalar_pure_watches",true},{"cell_inspection",true},
        {"inspection_command","nex-task-inspect BINDING [TASK_ID [FRAME_INDEX]]"},
        {"inspection_schema","nex.task-value-inspection/1"},
        {"inspection_schema_file","llm/task-value-inspection.schema.json"},
        {"identity","stopped-process diagnostic identity; aliases/cycles remain explicit"},
        {"DAP_cell_expansion",true},{"read_only",true},{"inferior_evaluation",false},
        {"cell_watch_reconstruction",false},{"provider_images",true},{"provider_introduced_toolchain","0.278.0"},
        {"provider_catalog_ABI",int64_t(2)},{"provider_guide","docs/reference-provider-debugging.md"},{"native_HTTP",false},
        {"profiling",false},{"parallel_transfer",false},{"SDK_delivery_accepted",false},
        {"full_platform_acceptance",false}}},
      {"ordinary_tasks",llvm::json::Object{{"introduced_toolchain","0.271.0"},
        {"ordinary_CLI",true},
        {"public_source_enabled",true},
        {"guide","docs/reference-tasks.md"},
        {"test","tests/reference_tasks_cli.py"},
        {"source_language","0.30"},
        {"source_workers",int64_t(1)},
        {"execution","cooperative source on the invocation/request owner thread"},
        {"heap","one owned context across task frames, futures, channels and source errors"},
        {"reference_interpreter",true},
        {"native_standalone",true},
        {"native_HTTP",true},
        {"native_HTTP_platforms",llvm::json::Array{"macOS","Linux"}},
        {"native_task_ABI","0x4e45585400000008"},
        {"native_application_schema","nex.native-task-application/6"},
        {"retained_task_ABI7_unchanged",true},
        {"private_development_ABI_unchanged","0x4e45585400003001"},
        {"native_profiles",llvm::json::Array{"debug","release","profile"}},
        {"native_HTTP_profiles",llvm::json::Array{"debug","release","profile"}},
        {"native_HTTP_logical_debugging",false},{"native_HTTP_profiling",true},
        {"typescript",true},
        {"typescript_map","nex.typescript-map/4"},
        {"typescript_host_values","checked copied immutable wire arguments/results; independent heap per invocation"},
        {"typescript_host_IO",false},
        {"typed_diagnostics","copied at owned entry boundaries; no live reference packet escapes"},
        {"cell_payload_task_capabilities",false},
        {"task_provider_images",true},
        {"logical_debug_profile",true},{"logical_debug_profile_scope","independent native builds; HTTP profiling with pinned workload; HTTP logical debugging pending"},
        {"parallel_transfer",false},
        {"persistent_UI_context",false},
        {"SDK_delivery_accepted",false},
        {"full_platform_acceptance",false}}},
      {"status","ordinary_cli_graph_development"},{"selection","nex init; language0.30 in nex.json; explicit versioned C++ APIs"},
      {"guide","docs/references030.md"},{"grammar","docs/references030.ebnf"},{"test","tests/references030.py"},
      {"frontend",true},{"inherits029",true},{"canonical_format","nex.program/18"},{"source_bundle","nex.sources/1"},
      {"archival",true},{"explicit_history_preserving_migration",true},{"origin029_rechecked",true},
      {"reference_interpreter",true},{"native_application",true},{"typescript_value_entries",true},
      {"typescript_map","nex.typescript-map/3"},{"reference_execution","one sequential heap per execution; independent copied host values/errors"},
      {"no_reference_tasks","ordinary029 parser, scheduler and generator behavior retained"},
      {"task_reference_contexts",true},{"task_parallel_reference_contexts",false},{"reference_library_HTTP_entries",true},
      {"native_reference_HTTP",llvm::json::Object{{"introduced_toolchain","0.264.0"},
        {"guide","docs/reference-http.md"},{"test","tests/reference_http.py"},
        {"sequential_request",true},{"concurrent_independent_requests",true},
        {"owner","one thread-affine RequestScope per HTTP request"},
        {"source_errors","copy diagnostic; retire live payload within request"},
        {"response","ordinary immutable std::http::Response"},
        {"task_transfer",true},{"persistent_UI_context",false}}},
      {"native_reference_libraries",llvm::json::Object{{"introduced_toolchain","0.263.0"},
        {"guide","docs/reference-library-abi.md"},{"test","tests/reference_library.py"},
        {"code_only",true},{"one_runtime",true},{"one_enclosing_context",true},
        {"related_calls","live cell handles, immutable snapshots, returned closure captures and typed error packets"},
        {"compiled_source_catch",true},{"thread_affine",true},
        {"fatal_traps","unwind and close context before further calls"},
        {"images","keep code images loaded until callables, captures and image-local cleanup retire"},
        {"runtime_unload",false},{"stable_public_ABI",false}}},
      {"ordinary_CLI",true},{"new_project_default",true},{"SDK_delivery_accepted",false},{"full_platform_acceptance",false}}},
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
      {"source_modules",llvm::json::Object{{"introduced_toolchain","0.257.0"},
        {"selection","loadManagedReferencesPrototypeBundle"},{"schema","nex.private-reference-sources/1"},
        {"binding","shared module loader: imports, visibility, qualified nominal identities, trait witnesses and declaration-local type binders"},
        {"runtime_context","one heap across source units and calls in one sequential application"},
        {"native_linkage","one generated application image; separate DLL/reference host ABI remains pending"},
        {"typescript_map","reachable_source_units hashes and copied failure file/line; no source text or public revision"},
        {"guide","docs/managed-reference-modules.md"},{"test","tests/managed_reference_modules.cpp"},
        {"cases","tests/managed_reference_module_cases.py"},{"public_source_enabled",false}}},
      {"native",true},{"typescript",true},{"ordinary_CLI",false},{"archival",false},{"migration",false},
      {"native_introduced_toolchain","0.251.0"},{"native_selection","emitManagedReferencesPrototypeMLIR"},
      {"native_guide","docs/managed-reference-native-prototype.md"},
      {"native_entry","sequential application: unit or i64 process status; same-runtime generated-code fixture"},
      {"native_context","one application- or request-owned heap; source handles retire before heap close on every exit"},
      {"native_request",llvm::json::Object{{"introduced_toolchain","0.258.0"},
        {"selection","emitManagedReferencesPrototypeRequestMLIR"},
        {"symbol","i64 nex_private_reference_request(Handle **source_error_out)"},
        {"entry","no arguments; unit maps to zero, i64 status retains full width; nonnull caller-owned source-error output slot"},
        {"context","matching-runtime RequestScope owns one lazy heap across calls; requests never inherit the application heap"},
        {"limits","host may configure cell/node/edge limits once before first cell use"},
        {"polling","entry and before/after native cell operations; GC traversal is not preemptive or separately metered"},
        {"cleanup","request-owner thread after source handles; cancellation is observed cooperatively"},
        {"callbacks","factory/destructor reentry rejected across context transitions; an ended creation cannot publish its heap"},
        {"guide","docs/managed-reference-requests.md"},{"test","tests/managed_reference_requests.cpp"},
        {"public_source_enabled",false},{"http_adapter_enabled",false},{"reference_values_return_to_host",false}}},
      {"typescript_introduced_toolchain","0.253.0"},{"typescript_selection","emitManagedReferencesPrototypeTypeScript"},
      {"typescript_guide","docs/managed-reference-typescript-prototype.md"},
      {"typescript_entry","sequential execution context: no arguments; unit or immutable wire result in a private JSON-text evaluation envelope"},
      {"typescript_context","explicit expression/lexical/builder/completion roots; one heap across source calls; closed on every exit"},
      {"typescript_value_exports",llvm::json::Object{{"introduced_toolchain","0.261.0"},
        {"selection","emitManagedReferencesValueTypeScript"},{"guide","docs/managed-reference-value-exports.md"},
        {"input","checked immutable ordinary browser values; exact primitive kinds and nominal layouts; bounded copies"},
        {"output","ordinary immutable browser values; unit returns undefined; no execution envelope"},
        {"context","one sequential heap per invocation; copied result outlives close; nested host calls restore enclosing context"},
        {"errors","independent NexError code/message/site; no live source packet escapes"},
        {"output_order","source print observed synchronously, including before a failure"},
        {"transfer","no references, closures, tasks or owned resources at host signatures"},
        {"persistent_browser_state",false},{"UI_adapter",false},{"worker_transfer",false},
        {"test","tests/managed_reference_value_entries.py"},{"public_source_enabled",false}}},
      {"typescript_heap_kernel",llvm::json::Object{{"introduced_toolchain","0.252.0"},
        {"implementation","web/nex-managed-heap.ts"},{"guide","docs/managed-reference-typescript-heap.md"},
        {"test","tests/managed_heap_typescript.py"},{"source_lowering",true},
        {"rooting","explicit binding, operand, builder and transfer roots; no dependency on host GC timing"},
        {"representation","explicit identity for every immutable data node, including strings; checked boxed value facade"}}},
      {"input","single-unit parser or transient private source-module bundle; no endpoints"},
      {"type","cell<T>; identity aliases with immutable payload snapshots"},{"effect","state required for create, read, write and explicit collection"},
      {"operations",llvm::json::Array{"cell_new(value)","cell_new<T>(value)","cell_read(cell)","cell_write(cell,value)","cell_collect()"}},
      {"function_effects",llvm::json::Array{"io","state","throw","fs","ffi","inferred effect parameters"}},
      {"resource_coexistence",llvm::json::Object{{"introduced_toolchain","0.259.0"},
        {"effects",llvm::json::Array{"fs","ffi"}},{"realms","existing server-only resource rules"},
        {"reference_host","uses an enclosing explicit FileScope/ForeignScope; standalone file environment remains available"},
        {"native_host","application or matching-runtime request; source handles and owned resources unwind before heap close"},
        {"cell_payloads","genuine file/external owners and captures retain existing authority; task capabilities remain rejected"},
        {"browser","reachable server/resource functions rejected; unreachable server units excluded"},
        {"guide","docs/managed-reference-resources.md"},{"test","tests/managed_reference_resources.py"},
        {"public_source_enabled",false}}},
      {"entry_result","unit or immutable wire value; cells/closures cannot escape the host context"},
      {"uncaught_source_errors","E_SOURCE_EXCEPTION diagnostic; payload remains within the context"},
      {"threading","sequential; no task or parallel execution"}}},
    {"pending",llvm::json::Array{"matching complete compiler/platform/SDK qualification",
      "native HTTP logical debugging/profiling","persistent native host-session debug/profile launches and native UI controllers",
      "live cell graph reconstruction for pure watches","source finalizers and opaque native callback-cycle contracts",
      "cross-thread sharing, monitors and atomics","weak references and finalization semantics",
      "Java/Python class, nullable and dynamic protocols"}}};
}
}
