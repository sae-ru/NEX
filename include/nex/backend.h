#pragma once
#include "nex/language.h"
#include "nex_task_limits.h"
namespace nex {
// Versioned compiler-private static task interface. Source remains required.
// Definitions describe physical machine ownership, separately from exports.
struct NativeTaskExport {
  std::string contract, signature, accessor;
  int64_t requirements=0;
};
struct NativeTaskProviderInfo {
  bool enabled=false, codeOnly=false, taskFileReads=false;
  std::string component, cohort, language;
  std::set<std::string> definitions;
  std::map<std::string,NativeTaskExport> exports;
};
llvm::json::Object nativeTaskProviderJSON(const NativeTaskProviderInfo &);
NativeTaskProviderInfo parseNativeTaskProvider(const llvm::json::Value &);
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
};
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
  std::map<std::string,std::string> functionContracts;
  bool parallelCalls=false;
  NativeTaskProviderInfo taskProvider{};
  std::string taskProviderFile{},taskProviderDigest{};
};
std::string emitMLIR(const Program &program, const std::string &entry = "main", bool testEntry = false,bool libraryEntry=false);
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
}
