#include "nex/diagnostic_catalogue.h"
#include <algorithm>
#include <iterator>
#include <string_view>

namespace nex {
namespace {
struct Entry {const char *code,*category,*meaning,*action,*guide;};
// This reviewed catalogue is deliberately explicit. Host/user-defined trap
// codes and diagnostics absent from this list are not invented at lookup time.
constexpr Entry entries[]={
  {"E_ANALYSIS_LIMIT","limit","Editor/source analysis exceeded its declared bound.","Request a smaller overlay or symbol context; inspect the actual limit rather than dropping validation.","frontend"},
  {"E_API_LIMIT","api","An endpoint wire schema exceeds a checked size or record bound.","Reduce the exposed schema or split the API; keep wire eligibility checks enabled.","api"},
  {"E_API_METHOD","api","The endpoint method is unsupported.","Use an advertised HTTP method and retain the endpoint's exact method/path contract.","api"},
  {"E_API_NAME","api","An endpoint operation name conflicts with another definition.","Give each endpoint a distinct operation name and check all reachable modules.","api"},
  {"E_API_PATH","api","An endpoint route is outside the supported path grammar.","Use the documented /api/ route format; inspect the original path diagnostic.","api"},
  {"E_API_ROUTE","api","Two endpoints declare the same method/path.","Remove or rename the conflicting route and update its callers explicitly.","api"},
  {"E_API_SIGNATURE","api","An endpoint handler has an incompatible realm, parameters or result.","Use the advertised server handler signature with API context and an eligible result payload.","api"},
  {"E_API_STATUS","api","The declared success status cannot carry the required JSON response.","Choose a supported 2xx status that permits a body; do not replace an error with success.","api"},
  {"E_ARITY","type","A call supplies the wrong number of value arguments.","Check the resolved function or constructor signature and update every caller after an interface change.","language"},
  {"E_ASSERT","runtime","An assertion or source contract failed.","Inspect the failing predicate and its inputs. This is fatal checked control, not a catchable source error.","source-contract"},
  {"E_BASE64","runtime","Text is not a valid supported base64 encoding.","Use the strict codec contract and explicitly handle its result; do not silently discard invalid bytes.","bytes"},
  {"E_BOUNDS","runtime","An index or slice is outside the value's bounds.","Check start/count and len(value). String indices and slices count Unicode scalars, not UTF-8 bytes.","language"},
  {"E_CANCELLED","control","The owning operation or task was cancelled.","Stop work and retain runtime-owned cleanup. Cancellation is not an ordinary source exception and skips user finally.","task-limits"},
  {"E_CONSTRUCTOR","type","The selected value constructor does not match the declared type.","Use ordered struct fields or the named enum case; enum constructors need parentheses even without payloads.","language"},
  {"E_CONTRACT_LIMIT","limit","A source contract exceeds its declared size/count bound.","Reduce the clause or use small pure helpers; retain the same required predicate and checking scope.","source-contract"},
  {"E_CONTRACT_SYNTAX","syntax","A source contract is malformed or incomplete.","Use requires/ensures and complete invariant/decreases clauses only when the selected compiler advertises them.","source-contract"},
  {"E_DEBUG_LIMIT","limit","A debugger expression or captured value exceeds its budget.","Request a smaller bounded range or pure expression; do not execute source merely to bypass a watch limit.","expression"},
  {"E_DEBUG_RETURN","debug","A watch would need to return from an executing source function.","Inspect the result directly or use a permitted pure helper; postfix ? is not a debugger return operation.","expression"},
  {"E_DEBUG_UNAVAILABLE","debug","The requested value or operation is unavailable at this stop.","Check the current frame/stop identity and availability metadata before requesting the value again.","debug"},
  {"E_DEBUG_VALUE","debug","A debugger value does not satisfy its checked representation.","Use the selected frame's advertised type and bounded value protocol; retain the original diagnostic.","expression"},
  {"E_DIV_ZERO","runtime","Checked integer division or remainder used a zero divisor.","Validate the divisor before evaluation; source try/catch does not recover this fatal arithmetic trap.","language"},
  {"E_DNS_BUSY","provider","The selected DNS provider cannot admit this request now.","Handle the provider's recoverable outcome and actual capacity policy; do not infer additional DNS authority.","dns"},
  {"E_DNS_TIMEOUT","provider","The selected DNS request reached its timeout.","Inspect the explicit resolver policy and total timeout; distinguish a provider result from fatal parent cancellation.","dns"},
  {"E_DUPLICATE","name","A binding, parameter, field or declaration is repeated or reserved.","Inspect the named scope and choose a distinct legal name; do not shadow a required interface accidentally.","language"},
  {"E_EFFECT","effect","A declaration or call violates the checked effect contract.","Declare the actual required effects or keep the operation pure. Scope/spawn/wait can deliver source errors: add throw or use a lexical try. Effects do not grant OS authority.","language"},
  {"E_ENTRY","type","The requested execution entry is absent or ineligible.","Select a concrete entry with the command's required parameters/result; do not call a generic template as a native entry.","build"},
  {"E_ENUM","type","An enum declaration has no legal set of cases.","Declare at least one distinct case with eligible ordered payload types.","match"},
  {"E_EXCEPTION_MIGRATION","version","A retained exception model requires an explicit language migration.","Preserve the archived graph and IDs; use the selected migration workflow with a reviewed candidate.","exception"},
  {"E_EXCEPTION_STAGE","effect","The selected private exception experiment does not support this composition.","Use the selected public descriptor for ordinary programs; private experimental flags do not grant public support.","exception"},
  {"E_FFI_BINDING","ffi","An external binding's library/export identity or manifest pin is invalid.","Use the actual checked bundle's identifiers and lowercase SHA256 pin, plus an explicit operator grant.","ffi"},
  {"E_FFI_DECLARATION","ffi","An external declaration has an unsupported source signature or form.","Use a concrete server extern function with the ffi effect and the documented foreign body.","ffi"},
  {"E_FIELD","type","A value has no accessible field with the requested name.","Inspect its declared nominal type and field spelling. Imported names use alias::name, not field syntax.","language"},
  {"E_FILE","tool","A required file could not be read or written as requested.","Inspect the exact path and OS diagnostic; preserve existing data and required file/root permissions.","files"},
  {"E_FLOAT_LITERAL","syntax","A floating literal is malformed.","Use decimal digits around the fraction/exponent where required; NEX accepts finite binary64 values only.","language"},
  {"E_FUNCTION","type","A callable value or function operation is invalid for this context.","Check the exact callable signature, capture rules, realm and effects against the selected function guide.","function"},
  {"E_FUNCTION_LIMIT","limit","A callable type or closure exceeds its declared bound.","Reduce the signature/capture shape and inspect the reported limit rather than weakening type checks.","function"},
  {"E_GENERIC_ARITY","generic","The number of type arguments is incorrect.","Match the declared generic parameters. For example, err<T> and decode_json<T> each take one payload type.","language"},
  {"E_GENERIC_BOUND","generic","A generic argument or operation does not satisfy a declared bound.","Add the genuinely required bound or use an eligible argument; unused template bodies are still checked parametrically.","trait"},
  {"E_GENERIC_ENTRY","generic","A source template is not a concrete execution entry.","Instantiate it through a concrete wrapper or select the advertised specialized entry form.","language"},
  {"E_GENERIC_INFER","generic","The required generic arguments cannot be inferred uniquely.","State eligible type arguments explicitly. An associated projection does not by itself infer its Self type.","trait"},
  {"E_GENERIC_KIND","generic","A type argument has the wrong constructor kind or is incompletely applied.","Distinguish a unary constructor such as list from a value type such as list<i64>; match the declared kind.","trait"},
  {"E_GENERIC_LIMIT","limit","A generic construction exceeds its declared arity, depth or specialization budget.","Reduce the type/specialization graph while retaining the same contract; inspect the reported bound.","trait"},
  {"E_GENERIC_NAME","name","A generic or nominal name conflicts with a reserved builtin.","Rename the source declaration and its references; do not redefine result/list or other builtin constructors.","language"},
  {"E_GENERIC_SCOPE","generic","A type parameter is used outside its permitted scope.","Keep the parameter inside its declaration or pass an explicit concrete type through the public signature.","trait"},
  {"E_GPU_LIMIT","gpu","Reachable device code exceeds a declared GPU capacity or bound.","Inspect the selected backend's capacities and reachable graph; larger buffers do not extend language support automatically.","gpu"},
  {"E_GPU_REALM","gpu","A reachable function violates the GPU realm/effect contract.","Select shared pure reachable code supported by that emitter; source emission itself grants no device authority.","gpu"},
  {"E_GPU_RECURSION","gpu","The device emitter does not support the reachable recursion.","Use a supported bounded iteration or choose a CPU path; do not remove verification of the reachable graph.","gpu"},
  {"E_GPU_TYPE","gpu","A reachable type is outside the selected GPU backend's supported subset.","Query gpu_codegen for that backend and use its actual value ABI/capacities; CPU support does not imply device support.","gpu"},
  {"E_GPU_UNSUPPORTED","gpu","A reachable operation has no supported device lowering.","Inspect the exact rejected operation and advertised subset, then choose an explicit supported implementation.","gpu"},
  {"E_HTTP_BUSY","provider","The selected HTTP provider cannot admit this request now.","Handle its recoverable result and explicit capacity policy; do not bypass the operator's request limits.","http-client"},
  {"E_HTTP_TIMEOUT","provider","The selected HTTP request reached its total timeout.","Inspect network policy and elapsed body/header work; keep fatal parent deadlines distinct from provider results.","http-client"},
  {"E_INFER","type","The expression lacks enough type information.","Add the actual expected type or explicit eligible generic arguments; do not infer C++/Python conversions.","language"},
  {"E_INTERNAL","tool","A compiler/runtime invariant failed rather than an ordinary source rule.","Retain the exact compiler identity, input, diagnostic and failing IR; reduce a reproducer without disabling verification.","frontend"},
  {"E_LANGUAGE_VERSION","version","The selected compiler, source declaration or retained graph has an incompatible language version.","Query describe and use explicit history-preserving migration. Editing nex.json alone does not migrate a graph.","compatibility"},
  {"E_LEX","syntax","Source contains an invalid token or character outside a literal.","Use ASCII identifiers, quoted UTF-8 text and supported operators; inspect the indicated byte column.","grammar"},
  {"E_LIMIT","limit","Execution reached a declared resource/capacity limit.","Inspect the exact operation and budget, reduce live work or select a reviewed limit; do not relabel the failure as success.","task-limits"},
  {"E_MATCH","runtime","No supported runtime match outcome is available.","Keep checked exhaustive patterns and source/revision consistency; inspect the original match diagnostic.","match"},
  {"E_MATCH_LIMIT","limit","A pattern exceeds its declared depth/node bound.","Reduce or decompose the pattern while retaining exhaustive ordered matching.","match"},
  {"E_MATCH_TYPE","type","A pattern or match arm disagrees with the subject/result type or arm form.","Use one subject type and consistent arm result types; do not mix statement block arms with expression arms.","match"},
  {"E_MEMORY","runtime","An allocation or reservation could not be satisfied.","Inspect live managed values and explicit budgets; preserve cleanup and distinguish this fatal outcome from result values.","resources"},
  {"E_MUTABILITY","type","Assignment targets an immutable binding.","Use var for a local that must be reassigned; let, parameters and captures remain immutable snapshots.","language"},
  {"E_NAME","name","The requested identifier or function cannot be resolved.","Check spelling, lexical scope and imports; imported definitions use alias::name and may need pub.","language"},
  {"E_NETWORK_BUSY","provider","The selected TCP provider cannot admit this request now.","Handle its result under the declared socket/capacity policy rather than creating an ungranted connection.","tcp"},
  {"E_NETWORK_TIMEOUT","provider","The selected TCP operation reached its timeout.","Inspect the named operation and total timeout; preserve cancellation/deadline precedence and resource retirement.","tcp"},
  {"E_OPTION","tool","A command-line option or argument is invalid for this command.","Use the selected command's documented positional arguments and flags; do not silently ignore an unsupported option.","discovery"},
  {"E_OVERFLOW","runtime","Checked signed arithmetic exceeded the i64 range.","Validate operands or choose a supported explicit numeric representation; do not replace checked arithmetic with wrapping.","language"},
  {"E_PARALLEL_TYPE","type","parallel_map has an incompatible value/callback signature.","Use a one-argument eligible value-returning callback and the required realm/effects; inspect source_concurrency.","concurrency"},
  {"E_PARSE","syntax","The token sequence does not match the selected NEX grammar.","Inspect the reported token and its predecessor. Locals use let/var name:Type=value; reassignment uses name=value. +=, ++ and let mut are not NEX syntax.","quick"},
  {"E_PARSE_LIMIT","limit","Source syntax exceeds its declared recursion/chain bound.","Split the expression or declaration into smaller checked helpers; do not disable parser limits.","grammar"},
  {"E_RANGE","type","A literal, conversion or value is outside its required finite range.","Check i64/finite-f64 and octet domains. Inspect the exact operation instead of silently clipping or wrapping.","language"},
  {"E_REALM","effect","A declaration or call crosses an unavailable execution realm.","Keep shared code portable, server authority on the server and client code free of server capabilities.","language"},
  {"E_RESOURCE","tool","A matching compiler/SDK resource could not be found.","Keep bin/nex with its matching share/nex resources or select the intended NEX_RESOURCE_DIR; do not borrow an older SDK silently.","discovery"},
  {"E_RESOURCE_CONSTRUCTOR","type","An opaque resource has no public source constructor.","Use a granted external factory and retain its genuine owner/lifetime instead of fabricating a value.","source-resources"},
  {"E_RESOURCE_DECLARATION","type","An opaque resource declaration is invalid for the selected source model.","Use its advertised server declaration and eligible parameters; source structs cannot replace genuine opaque owners.","source-resources"},
  {"E_RESOURCE_TYPE","type","The operation requires a different or genuine opaque resource owner.","Match the exact nominal resource type and active ownership scope; do not cast or invent a handle.","source-resources"},
  {"E_RESULT","runtime","unwrap evaluated an error result.","Handle the result with match/is_ok or propagate it with ? from a result-returning function. Source catch does not catch this fatal unwrap trap.","result"},
  {"E_RESULT_RETURN","type","Postfix ? has no compatible result-returning function boundary.","Return result<T> from the current function or explicitly handle the error value; ? returns from its current function.","result"},
  {"E_RETHROW","effect","Bare throw has no lexical source catch to rethrow from.","Rethrow only inside the current function's catch, or throw an explicitly typed new source error.","exception"},
  {"E_RETURN","type","A non-unit function has a path without the required return value.","Return the declared type on every reachable normal path; a statement if/match is not an implicit value return.","language"},
  {"E_RUNTIME","runtime","Execution failed in the selected runtime operation.","Retain the original code/message and runtime identity; distinguish fatal control, source errors and ordinary result values.","diagnostic"},
  {"E_SOURCE_EXCEPTION","runtime","An explicit source error escaped the selected entry.","Inspect its typed payload or source code/message and add a matching source catch only when recovery is intended.","exception"},
  {"E_SOURCE_TYPE","type","A source error payload has an incompatible or unsupported type.","Use the selected typed-error contract and preserve its ownership/realm restrictions; matching uses the complete concrete type.","exception"},
  {"E_STRING","syntax","A string literal or escape is invalid or unterminated.","Use quoted strict UTF-8 text and valid JSON-style escapes; surrogate escapes must form Unicode scalars.","language"},
  {"E_TARGET_LIBRARY","tool","A selected native library does not satisfy the target's checked link contract.","Use matching target libraries/archives and preserve the reported dependency/ABI diagnostics.","native-entry-abi"},
  {"E_TASK_DEADLOCK","control","The structured task scope cannot make further progress.","Inspect waits, channels and closure ordering; ensure a sender/receiver/close can settle without escaping its owner scope.","task-lifetime"},
  {"E_TASK_STATE","control","A task or channel operation uses an invalid lifecycle state.","Keep operations inside the genuine owner scope and inspect completion/cancellation/close state before reuse.","task-lifetime"},
  {"E_TASK_TYPE","type","A task callback, future, channel or scope has an incompatible type/effect contract.","Use the advertised exact callback signature, effects and owner scope; discover structured_tasks_runtime for supported IO compositions.","task-lifetime"},
  {"E_TASK_UNIMPLEMENTED","control","The selected task engine does not implement this reachable operation.","Choose a supported engine/composition or keep the integration pending; a different backend's support is not authority.","tasks-runtime"},
  {"E_TEST","type","A test declaration or test function use is invalid.","Use parameterless unit test functions with the advertised effects; test functions are not ordinary callable values.","language"},
  {"E_TIMEOUT","control","Execution reached its owning deadline.","Inspect the total elapsed operation and retain runtime-owned cleanup. Fatal deadlines are not recoverable source errors.","task-limits"},
  {"E_TRAIT_ASSOCIATED","generic","An associated type binding/projection is missing or inconsistent.","Bind each required associated type and use the exact trait/Self projection.","trait"},
  {"E_TRAIT_CONFORMANCE","generic","An implementation does not satisfy the trait contract.","Match every method, associated type, parameter/result type, bound, realm and effect.","trait"},
  {"E_TRAIT_CYCLE","generic","Trait resolution contains an unsupported cycle.","Break the dependency cycle explicitly without weakening the required trait contract.","trait"},
  {"E_TRAIT_HEAD","generic","A trait implementation head is not valid or eligible.","Use the documented trait-for-type head and constructor kind; inspect the exact rejected declaration.","trait"},
  {"E_TRAIT_LIMIT","limit","Trait resolution exceeds its declared bound.","Reduce the implementation/projection graph and retain a concrete reproducer of the rejected resolution.","trait"},
  {"E_TRAIT_METHOD","generic","A trait method declaration or binding is incompatible.","Bind the required method name to a function with the exact advertised signature, realm and effects.","trait"},
  {"E_TRAIT_ORPHAN","generic","The implementation violates trait/type ownership rules.","Declare the implementation in an eligible owner module; do not add ambient overlapping implementations.","trait"},
  {"E_TRAIT_OVERLAP","generic","Multiple implementations overlap for the requested type.","Make the eligible implementation unique; do not depend on incidental declaration order.","trait"},
  {"E_TYPE","type","A declaration, expression or call disagrees with its required type.","Inspect the actual signature and concrete types. NEX has no implicit numeric/boolean conversion; use an eligible explicit conversion.","language"},
  {"E_TYPED_EXCEPTION_AUTHORITY","effect","A typed error transfer would violate resource authority or lifetime.","Keep genuine resource owners inside permitted scopes and use the advertised typed-provider transport.","typed-error-provider"},
  {"E_UNREACHABLE","type","A statement follows an unconditional control exit.","Remove or restructure the unreachable statement; preserve return/throw/finally ordering.","language"},
  {"E_UTF8","runtime","Text is not a sequence of valid UTF-8 Unicode scalars.","Preserve arbitrary input as bytes and handle strict decoding explicitly; do not replace malformed text silently.","bytes"},
  {"E_VISIBILITY","name","A public signature or import exposes an inaccessible definition.","Export the required nominal types/traits as well as functions, or keep the interface private.","language"},
};
struct Example {const char *code,*invalid,*corrected;};
constexpr Example examples[]={
  {"E_PARSE",R"nex(module example; fn main()->unit { var n:i64=1; n+=2; })nex",
    R"nex(module example; fn main()->unit { var n:i64=1; n=n+2; assert(n==3); })nex"},
  {"E_MUTABILITY",R"nex(module example; fn main()->unit { let n:i64=1; n=2; })nex",
    R"nex(module example; fn main()->unit { var n:i64=1; n=2; assert(n==2); })nex"},
  {"E_TYPE",R"nex(module example; fn value()->i64 { return true; } fn main()->unit {})nex",
    R"nex(module example; fn value()->i64 { return 1; } fn main()->unit { assert(value()==1); })nex"},
  {"E_NAME",R"nex(module example; fn main()->unit { assert(missing()==1); })nex",
    R"nex(module example; fn value()->i64 { return 1; } fn main()->unit { assert(value()==1); })nex"},
  {"E_ARITY",R"nex(module example; fn value(n:i64)->i64 { return n; } fn main()->unit { assert(value()==1); })nex",
    R"nex(module example; fn value(n:i64)->i64 { return n; } fn main()->unit { assert(value(1)==1); })nex"},
  {"E_EFFECT",R"nex(module example; fn main()->unit { print("value"); })nex",
    R"nex(module example; fn main()->unit !{io} { print("value"); })nex"},
  {"E_EFFECT",R"nex(module example; fn main()->unit !{task} { let n:i64=with_tasks(1,fn(scope:task_scope)->i64 !{task} { return 1; }); })nex",
    R"nex(module example; fn main()->unit !{task,throw} { let n:i64=with_tasks(1,fn(scope:task_scope)->i64 !{task} { return 1; }); assert(n==1); })nex"},
  {"E_RETURN",R"nex(module example; fn value(n:i64)->i64 { if n>0 { return n; } } fn main()->unit {})nex",
    R"nex(module example; fn value(n:i64)->i64 { if n>0 { return n; } return 0; } fn main()->unit { assert(value(0)==0); })nex"},
  {"E_RESULT_RETURN",R"nex(module example; fn value()->i64 { return ok(1)?; } fn main()->unit {})nex",
    R"nex(module example; fn value()->result<i64> { let n:i64=ok(1)?; return ok(n); } fn main()->unit { assert(unwrap(value())==1); })nex"},
};

std::vector<const Entry*> ordered(){
  std::vector<const Entry*> result;for(const auto &entry:entries)result.push_back(&entry);
  std::sort(result.begin(),result.end(),[](const auto *a,const auto *b){return std::string_view(a->code)<b->code;});
  return result;
}
const std::string &catalogueHash(){
  static const std::string result=[](){
    std::string text="nex.diagnostic-catalogue/1";
    auto append=[&](const char *value){text.push_back('\0');text+=value;};
    for(const auto *entry:ordered())for(const char *value:{entry->code,entry->category,entry->meaning,entry->action,entry->guide})append(value);
    for(const auto &example:examples)for(const char *value:{example.code,example.invalid,example.corrected})append(value);
    return hash(text);
  }();return result;
}
llvm::json::Object envelope(const char *schema,const std::string &toolchain,const std::string &compilerBuild){
  return llvm::json::Object{{"schema",schema},{"language",languageVersion},{"toolchain",toolchain},
    {"compiler_build",compilerBuild},{"descriptor_hash",hash(json(describe(),false))},
    {"catalogue_hash",catalogueHash()}};
}
llvm::json::Value bounded(llvm::json::Object result){
  llvm::json::Value value(std::move(result));
  if(json(value).size()+1>diagnosticExplanationByteLimit)throw Error("E_INTERNAL","compiled diagnostic explanation exceeds its byte bound");
  return value;
}
}

llvm::json::Object diagnosticCatalogueCapability(){
  return llvm::json::Object{{"status","compiled_reviewed_catalogue"},{"command","nex explain CODE [--json]"},
    {"index_command","nex explain --kind index [--json]"},{"schema","nex.diagnostic-explanation/1"},
    {"index_schema","nex.diagnostic-catalogue-index/1"},{"catalogue_hash",catalogueHash()},
    {"catalogue_hash_algorithm","BLAKE3/256"},
    {"covered_codes",int64_t(std::size(entries))},{"checked_example_pairs",int64_t(std::size(examples))},
    {"complete_code_registry",false},{"unknown_codes_invented",false},
    {"code_bytes_max",int64_t(diagnosticCodeByteLimit)},{"response_bytes_max",int64_t(diagnosticExplanationByteLimit)},
    {"graph_store_opened",false},{"source_files_read",false},{"python_required",false},
    {"source_executed",false},{"automatic_fix",false},{"guide","docs/diagnostics.md"}};
}
llvm::json::Object llmEntryCapability(){
  return llvm::json::Object{{"status","bounded_language_entry"},{"guide_command","nex guide --kind quick --json"},
    {"guide","llm/QUICK_REFERENCE.md"},{"language",languageVersion},{"guide_utf8_bytes_max",6144},
    {"example_project","examples/llm-quick/nex.json"},{"examples_require_validation",true},
    {"token_savings_demonstrated",false},{"language_migration_required",false}};
}
llvm::json::Value diagnosticCatalogueIndex(const std::string &toolchain,const std::string &compilerBuild){
  auto result=envelope("nex.diagnostic-catalogue-index/1",toolchain,compilerBuild);
  llvm::json::Array codes;for(const auto *entry:ordered())codes.push_back(entry->code);
  result["codes"]=std::move(codes);result["complete_code_registry"]=false;
  result["command"]="nex explain CODE --json";return bounded(std::move(result));
}
llvm::json::Value explainDiagnostic(const std::string &code,const std::string &toolchain,const std::string &compilerBuild){
  if(code.size()<3||code.size()>diagnosticCodeByteLimit||!code.starts_with("E_")||
      !std::all_of(code.begin()+2,code.end(),[](char c){return(c>='A'&&c<='Z')||(c>='0'&&c<='9')||c=='_';}))
    throw Error("E_OPTION","explain code must be E_ followed by uppercase ASCII letters/digits/underscores, at most128 bytes");
  const Entry *selected=nullptr;for(const auto &entry:entries)if(code==entry.code){selected=&entry;break;}
  if(!selected)throw Error("E_OPTION","no compiled explanation for "+code+"; use nex explain --kind index for covered builtin codes");
  auto result=envelope("nex.diagnostic-explanation/1",toolchain,compilerBuild);
  result["code"]=code;result["category"]=selected->category;result["meaning"]=selected->meaning;
  result["action"]=selected->action;result["guide_command"]=std::string("nex guide --kind ")+selected->guide+" --json";
  result["context_specific"]=false;result["automatic_fix"]=false;
  llvm::json::Array pairs;for(const auto &example:examples)if(code==example.code)pairs.push_back(llvm::json::Object{
    {"invalid",example.invalid},{"corrected",example.corrected},{"rejection_code",example.code},
    {"kind","illustrative_program_pair"},{"applies_to_user_source",false}});
  result["examples"]=std::move(pairs);return bounded(std::move(result));
}
std::string diagnosticExplanationText(const llvm::json::Value &value){
  const auto *object=value.getAsObject();if(!object)throw Error("E_INTERNAL","invalid compiled explanation");
  auto boundedText=[](std::string result){
    if(result.size()>diagnosticExplanationByteLimit)throw Error("E_INTERNAL","compiled diagnostic text exceeds its byte bound");
    return result;
  };
  if(auto codes=object->getArray("codes")){
    std::string result="Covered builtin diagnostic codes (reviewed catalogue, not a complete registry):\n";
    for(const auto &code:*codes)result+=code.getAsString()->str()+"\n";return boundedText(std::move(result));
  }
  std::string result=object->getString("code")->str()+" — "+object->getString("meaning")->str()+"\n";
  result+="Action: "+object->getString("action")->str()+"\n";
  result+="Guide: "+object->getString("guide_command")->str()+"\n";
  for(const auto &item:*object->getArray("examples")){
    const auto *example=item.getAsObject();result+="Invalid example:\n"+example->getString("invalid")->str()+"\n";
    result+="Corrected example:\n"+example->getString("corrected")->str()+"\n";
  }
  return boundedText(std::move(result));
}
}
