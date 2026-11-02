#pragma once
#include "nex/language.h"
#include "nex_task_limits.h"
namespace nex {
enum class NativeTaskLinkageMode { None, Static, SharedFixed };
enum class NativeTaskArtifactKind { CodeArchive, PicStage, SharedImage, Application };
struct NativeTaskImageIdentity {
  std::string key,digest,sha256,uuid,runtimeKey,runtimeDigest;
};
// Versioned compiler-private static task interface. Source remains required.
// Definitions describe physical machine ownership, separately from exports.
struct NativeTaskExport {
  std::string contract, signature, accessor;
  int64_t requirements=0;
};
struct NativeTaskProfileSite {
  std::string name,functionHash,functionSourceHash,sourceUnitHash,debugPath,contract;
  int64_t line=0;
};
struct NativeTaskProfileRegistry {
  std::string component,accessor,ownerImage;
  std::vector<NativeTaskProfileSite> sites;
};
struct NativeTaskProfileCatalog {
  NativeTaskLinkageMode mode=NativeTaskLinkageMode::None;
  NativeTaskArtifactKind artifact=NativeTaskArtifactKind::CodeArchive;
  std::string ownerImage;
  std::vector<NativeTaskProfileRegistry> registries;
};
struct NativeTaskProfileRegistryInfo {
  std::string component,accessor,catalogHash;
  uint64_t siteCount=0,textBytes=0;
};
struct NativeTaskProfileInfo {
  std::string catalogFile,catalogHash;
  std::vector<NativeTaskProfileRegistryInfo> registries;
};
std::string nativeTaskProfileRegistryAccessor(const std::string &component);
llvm::json::Object nativeTaskProfileCatalogJSON(const NativeTaskProfileCatalog &);
NativeTaskProfileCatalog parseNativeTaskProfileCatalog(const llvm::json::Value &);
NativeTaskProfileInfo nativeTaskProfileInfo(const NativeTaskProfileCatalog &,const std::string &file="task-profile-catalog.json");
struct NativeTaskDebugCode {
  std::string name,functionHash,functionSourceHash,sourceUnitHash,debugPath,contract;
  llvm::json::Object metadata;
};
struct NativeTaskDebugRegistry {
  std::string component,accessor,ownerImage;
  std::vector<NativeTaskDebugCode> codes;
};
struct NativeTaskDebugCatalog {
  NativeTaskLinkageMode mode=NativeTaskLinkageMode::None;
  NativeTaskArtifactKind artifact=NativeTaskArtifactKind::CodeArchive;
  std::string ownerImage;
  std::vector<NativeTaskDebugRegistry> registries;
};
struct NativeTaskDebugDefinition {
  std::string name,functionHash,functionSourceHash,sourceUnitHash,debugPath,contract;
  int64_t line=0;
  bool retained=false;
};
struct NativeTaskDebugSourceComponent {
  std::string component,ownerImage,entry,language,revision,sourceHash,bundleFile,bundleHash;
  std::vector<std::string> exports;
  std::vector<NativeTaskDebugDefinition> definitions;
};
struct NativeTaskDebugSourceUnion {
  NativeTaskLinkageMode mode=NativeTaskLinkageMode::None;
  NativeTaskArtifactKind artifact=NativeTaskArtifactKind::CodeArchive;
  std::string ownerImage;
  std::vector<NativeTaskDebugSourceComponent> components;
};
struct NativeTaskDebugRegistryInfo {
  std::string component,accessor,catalogHash;
  uint64_t codeCount=0;
};
struct NativeTaskDebugInfo {
  std::string catalogFile,catalogHash,sourceUnionFile,sourceUnionHash;
  std::vector<NativeTaskDebugRegistryInfo> registries;
};
std::string nativeTaskDebugRegistryAccessor(const std::string &component);
llvm::json::Object nativeTaskDebugCatalogJSON(const NativeTaskDebugCatalog &);
NativeTaskDebugCatalog parseNativeTaskDebugCatalog(const llvm::json::Value &);
llvm::json::Object nativeTaskDebugSourceUnionJSON(const NativeTaskDebugSourceUnion &);
NativeTaskDebugSourceUnion parseNativeTaskDebugSourceUnion(const llvm::json::Value &);
llvm::json::Object nativeTaskDebugInfoJSON(const NativeTaskDebugInfo &);
NativeTaskDebugInfo nativeTaskDebugInfo(const NativeTaskDebugCatalog &,const NativeTaskDebugSourceUnion &,
  const std::string &catalogFile="task-debug-catalog.json",const std::string &sourceUnionFile="task-debug-sources.json");
struct NativeTaskProviderInfo {
  bool enabled=false, codeOnly=false, taskFileReads=false, taskFileWrites=false,taskFileStreams=false;
  std::string component, cohort, language;
  std::set<std::string> definitions;
  std::map<std::string,NativeTaskExport> exports;
  NativeTaskLinkageMode mode=NativeTaskLinkageMode::Static;
  NativeTaskArtifactKind artifact=NativeTaskArtifactKind::CodeArchive;
  // PIC stages have no final image owner. Final records bind one actual image.
  std::string ownerImage{};
  std::map<std::string,std::string> definitionOwners{};
  std::map<std::string,bool> componentFileReads{},componentFileWrites{},componentFileStreams{};
  std::optional<NativeTaskImageIdentity> image{};
  std::optional<NativeTaskProfileInfo> profiling{};
  std::optional<NativeTaskDebugInfo> debugging{};
};
struct NativeTaskApplicationStage {
  bool enabled=false;
  std::string entry{},descriptorAccessor{};
  nexrt::TaskExecutionLimits configured;
  bool fileReads=false,fileWrites=false;
  int64_t executionABI=INT64_C(0x4e45585400000003);
  bool fileStreams=false;
};
llvm::json::Value nativeTaskApplicationStageJSON(const NativeTaskApplicationStage &);
NativeTaskApplicationStage parseNativeTaskApplicationStage(const llvm::json::Value &);
llvm::json::Object nativeTaskProviderJSON(const NativeTaskProviderInfo &);
NativeTaskProviderInfo parseNativeTaskProvider(const llvm::json::Value &);
struct NativeTaskFileRequirements {bool reads=false,writes=false,streams=false;};
// Checked reachable instructions/retained values; these flags grant no authority.
NativeTaskFileRequirements nativeTaskFileRequirements(const Program &,const std::set<std::string> &selected);
bool nativeTaskFileWrites(const Program &,const std::set<std::string> &selected);
NativeTaskExport nativeTaskExportInterface(const Program &,const std::string &function,
                                         const std::string &contract);
// Compiler-private NEX ABI inputs, produced by a checked project build. Source
// remains available to the checker; machine definitions come from this archive.
struct NativeLibraryInput {
  std::string path, digest, abi;
  std::map<std::string,std::string> contracts;
  bool parallelCalls=false;
  std::string taskProviderPath{},taskProviderDigest{};
};
struct BuildOptions {
  std::string profile = "debug", target, entry = "main";
  bool testEntry = false, libraryEntry = false;
  std::string toolchain;
  // Set only by native application packaging, never by ambient environment.
  std::string foreignCatalogue;
  bool projectLibraryABI = false, codeOnlyLibrary = false;
  // Compiler-private staging for a separately linked image. Keep executable
  // entry validation/main emission, but retain only PIC NEX objects; a final
  // linker owns runtime, bridge and application/profile identity exactly once.
  bool positionIndependent = false, deferredLink = false;
  // A final image linker owns its C++ entry thunk. Entry validation remains
  // executable-specific while reusable NEX function objects omit LLVM main.
  bool functionsOnly = false;
  std::vector<std::string> libraryExports;
  std::vector<NativeLibraryInput> libraries;
  nexrt::TaskExecutionLimits taskLimits;
  bool taskLimitsSpecified=false;
  // Explicit logical task debugger instrumentation; ordinary debug-profile
  // builds retain their existing execution and metadata without these hooks.
  bool taskDebug=false;
  bool staticTaskABI=false;
  std::string taskComponent{};
  std::set<std::string> taskImportedFunctions{};
  NativeTaskLinkageMode taskLinkageMode=NativeTaskLinkageMode::None;
};
NativeTaskLinkageMode effectiveNativeTaskLinkage(const BuildOptions &);
struct BuildResult {
  std::string executable, mlir, llvm, key;
  bool cached = false;
  std::string notices;
  std::string compilation;
  unsigned compiledModules = 0, reusedModules = 0;
  std::string target, compilerTarget;
  bool hostCompatible = true;
  unsigned compiledFunctions = 0, reusedFunctions = 0;
  bool foreignCalls = false;
  std::string libraryABI;
  // Exact physical entry signatures from verified LLVM, for --library builds.
  // Serialized JSON avoids making the native build result a move-only object.
  std::string nativeEntryABI;
  std::map<std::string,std::string> functionContracts;
  bool parallelCalls=false;
  NativeTaskProviderInfo taskProvider{};
  std::string taskProviderFile{},taskProviderDigest{};
  NativeTaskApplicationStage taskApplication{};
  NativeTaskProfileCatalog profileCatalog{};
  NativeTaskDebugCatalog debugCatalog{};
  NativeTaskDebugSourceUnion debugSources{};
  // Original pretty-printed source-bundle bytes, keyed by component.
  std::map<std::string,std::string> debugSourceBundles{};
};
std::string emitMLIR(const Program &program, const std::string &entry = "main", bool testEntry = false,bool libraryEntry=false);
// Dedicated compiler-private experiment; public build/archival stay gated.
std::string emitSourceExceptionsPrototypeMLIR(const Program &,const std::string &entry="main",bool optimized=false);
// The caller must validate the bounded scalar Wasm closure before emitting it.
std::string emitWasmMLIR(const Program &program,const std::string &entry,bool optimized);
std::string lowerMLIRToLLVM(const std::string &source,const std::string &path,
                           const std::string &triple,const std::string &layout);
void validateNativeBuildEntry(const Program &program,const BuildOptions &options);
// Additional files bound by a versioned retained-build completion record.
// Legacy records without these fields retain the original six-file contract.
std::vector<std::string> nativeCompletionInputs(const llvm::json::Object &metadata);
BuildResult build(const Program &program, const std::string &directory, const BuildOptions &options);
int execute(const std::vector<std::string> &arguments);
// Trusted Clang/GNU-compatible build tools accept @response files. Large
// commands use an owned UTF-8 argument file; application argv stays literal.
int executeNativeBuildTool(const std::vector<std::string> &arguments);
// The caller owns cleanup (or retains failed native intermediates).
std::string createTemporaryDirectory(const std::string &prefix,const std::string &base="");
struct ProcessResult { int code; std::string output, errors; };
ProcessResult capture(const std::vector<std::string> &arguments,unsigned timeoutSeconds=30);
std::string pythonProgram();
ProcessResult captureNativeBuildTool(const std::vector<std::string> &arguments,unsigned timeoutSeconds=30);
}
