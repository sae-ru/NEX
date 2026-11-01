#include "nex_task_protocol.h"
#include "nex/native_images.h"
#include "nex/native_file.h"
#include "nex/task_frontend.h"
#include "nex/native_toolchain.h"
#include "nex/operations.h"
#include "nex/task_provider_debug.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/Support/raw_ostream.h"
#include "llvm/Object/BuildID.h"
#include "llvm/Object/MachO.h"
#include "llvm/Object/ObjectFile.h"
#include "llvm/Support/Error.h"
#include "llvm/Support/SHA256.h"
#include "llvm/TargetParser/Triple.h"
#include <algorithm>
#include <cerrno>
#include <cstdlib>
#include <filesystem>
#include <set>
#include <cstddef>
#include <cstring>
#ifdef _WIN32
#include "nex_platform.h"
#endif

namespace nex {
namespace {
namespace fs=std::filesystem;
using Object=llvm::json::Object;using Array=llvm::json::Array;using JSON=llvm::json::Value;
[[noreturn]] void fail(const std::string &s){throw Error("E_PROJECT_IMAGE",s);}
Object read(const fs::path &p){
  auto parsed=llvm::json::parse(readFile(p.string()));if(!parsed)fail("invalid captured image JSON: "+p.string());
  auto o=parsed->getAsObject();if(!o)fail("expected captured image object: "+p.string());return Object(*o);
}
std::string text(const Object &o,const char *k){auto v=o.getString(k);if(!v)fail(std::string("missing captured image field: ")+k);return v->str();}
std::string digest(const fs::path &p){return hash(readFile(p.string()));}
std::string sha(const fs::path &p){auto data=readFile(p.string());return llvm::toHex(llvm::SHA256::hash(llvm::arrayRefFromStringRef(data)),true);}
std::string uuid(const fs::path &p){
  return nativeImageUUID(p.string());
}
struct Temporary {fs::path path=createTemporaryDirectory("nex-native-image");~Temporary(){std::error_code ignored;fs::remove_all(path,ignored);}};
void run(std::vector<std::string> args){if(executeNativeBuildTool(args)!=0)fail("native image tool failed; retained inputs describe the selected link");}
void copyCaptured(const fs::path &from,const fs::path &to){
  if(!fs::is_regular_file(from))fail("captured image source is not a regular file: "+from.string());
  fs::create_directories(to.parent_path());
  auto bytes=readFile(from.string());auto permissions=fs::status(from).permissions();
  // ELF loaders keep relocated private pages for the lifetime of a mapping.
  // Truncating a mapped DSO, even to restore identical bytes, invalidates them.
  if(!fs::is_symlink(to)&&fs::is_regular_file(to)&&fs::status(to).permissions()==permissions&&readFile(to.string())==bytes)return;
  // mkstemp interprets only the final Xs; literal '%' in a project path is
  // data, whereas LLVM unique-file models replace '%' throughout the path.
  auto path=to.string()+".nex-copy-XXXXXX";int descriptor=::mkstemp(path.data());
  if(descriptor<0)fail("cannot stage captured image: "+std::error_code(errno,std::generic_category()).message());
  struct Staged {fs::path path;~Staged(){std::error_code ignored;fs::remove(path,ignored);}} staged{path};
  llvm::raw_fd_ostream output(descriptor,true);output.write(bytes.data(),bytes.size());output.close();
  if(output.has_error()){auto failure=output.error();output.clear_error();fail("cannot write staged image: "+failure.message());}
  fs::permissions(staged.path,permissions);
  // The sibling stage is on the destination filesystem. Rename keeps existing
  // processes on their old inode while future loads see the complete new file.
  if(auto error=replaceNativeFile(staged.path,to))
    fail("cannot atomically replace captured image while preserving existing readers: "+error.message());
}
struct Captured {
  const NativeImageInput *input;
  Object build,debug,compilation;
  std::string objects;
  NativeTaskProviderInfo taskProvider;
  NativeTaskProfileCatalog profileCatalog;
  NativeTaskDebugCatalog debugCatalog;
  NativeTaskDebugSourceUnion debugSources;
  std::map<std::string,std::string> debugBundles;
};
Captured capture(const NativeImageInput &input){
  auto folder=fs::path(input.stage.executable).parent_path();auto meta=read(folder/"build.json");
  if(text(meta,"key")!=input.stage.key||!meta.getBoolean("position_independent").value_or(false))fail("image input requires its checked PIC build: "+input.name);
  auto kind=text(meta,"kind");if(kind!="object_archive"&&kind!="static_library")fail("image input is not an object archive: "+input.name);
  if(kind=="static_library"&&!read(folder/"library-abi.json").getBoolean("code_only").value_or(false))fail("shared images require code-only static dependencies: "+input.name);
  auto objects=readFile(input.stage.executable);std::string completed=input.stage.key+hash(objects);
  for(const auto &path:{folder/"program.mlir",folder/"program.ll",folder/"compilation.json",folder/"build.json",folder/"source-bundle.json"})completed+=digest(path);
  for(const auto &name:nativeCompletionInputs(meta))completed+=digest(folder/name);
  if(readFile((folder/"complete").string())!=hash(completed)+"\n")fail("captured PIC stage changed before image linking: "+input.name);
  NativeTaskProviderInfo provider;NativeTaskProfileCatalog catalog;NativeTaskDebugCatalog debugCatalog;NativeTaskDebugSourceUnion debugSources;std::map<std::string,std::string> debugBundles;
  if(effectiveNativeTaskLinkage(input.options)==NativeTaskLinkageMode::SharedFixed){
    auto record=folder/"task-provider.json";auto bytes=readFile(record.string());
    if(input.stage.taskProviderFile!=record.string()||hash(bytes)!=input.stage.taskProviderDigest)fail("captured task provider pin changed: "+input.name);
    auto parsed=llvm::json::parse(bytes);if(!parsed)fail("invalid captured task provider JSON");provider=parseNativeTaskProvider(*parsed);
    if(provider.mode!=NativeTaskLinkageMode::SharedFixed||provider.artifact!=NativeTaskArtifactKind::PicStage||provider.component!=input.name||provider.image||!provider.ownerImage.empty()||
       json(nativeTaskProviderJSON(provider),false)!=json(nativeTaskProviderJSON(input.stage.taskProvider),false))fail("captured task PIC provider differs from checked stage");
    if(provider.language=="0.23"||provider.language=="0.24"||(provider.language=="0.25"||provider.language=="0.26"||isTypedSourceErrorVersion(provider.language))){
      auto requirements=meta.getObject("runtime_requirements");auto writes=meta.getBoolean("task_file_writes");
      if(!requirements||!writes||*writes!=provider.taskFileWrites||requirements->getBoolean("task_file_writes")!=*writes)fail("captured023 stage write requirements differ");
      auto selected=meta.get("task_application");if(!selected)fail("captured023 stage omitted task application selection");auto stage=parseNativeTaskApplicationStage(*selected);
      if(stage.enabled&&(stage.executionABI!=(isTypedSourceErrorVersion(provider.language)?nexrt::taskCodeTypedSourceExceptionABI:(provider.language=="0.25"||provider.language=="0.26"||isTypedSourceErrorVersion(provider.language))?nexrt::taskCodeSourceExceptionABI:provider.language=="0.24"?nexrt::taskCodeStreamABI:nexrt::taskCodeWriteABI)||stage.fileWrites!=provider.taskFileWrites))fail("captured root application ABI/write requirements differ");
      if(provider.language=="0.24"||(provider.language=="0.25"||provider.language=="0.26"||isTypedSourceErrorVersion(provider.language))){
        auto streams=meta.getBoolean("task_file_streams");
        if(!streams||*streams!=provider.taskFileStreams||requirements->getBoolean("task_file_streams")!=*streams||
           (stage.enabled&&stage.fileStreams!=provider.taskFileStreams))fail("captured024 stream requirements differ");
      }
    }
    if(input.options.profile=="profile"){
      if(!provider.profiling)fail("profile task stage omitted its catalog");
      auto parsed=llvm::json::parse(readFile((folder/provider.profiling->catalogFile).string()));if(!parsed)fail("invalid captured task profile catalog");catalog=parseNativeTaskProfileCatalog(*parsed);
      if(nativeTaskProfileInfo(catalog).catalogHash!=provider.profiling->catalogHash||json(nativeTaskProfileCatalogJSON(catalog),false)!=json(nativeTaskProfileCatalogJSON(input.stage.profileCatalog),false))fail("captured task profile catalog differs from checked stage");
    }else if(provider.profiling)fail("unprofiled stage cannot consume a profile task provider");
    if(bool(provider.debugging)!=input.options.taskDebug)fail("debug and ordinary task providers cannot be mixed");
    if(provider.debugging){const auto &info=*provider.debugging;auto catalogValue=llvm::json::parse(readFile((folder/info.catalogFile).string()));auto sourceValue=llvm::json::parse(readFile((folder/info.sourceUnionFile).string()));if(!catalogValue||!sourceValue)fail("invalid captured debug catalog/source union");
      debugCatalog=parseNativeTaskDebugCatalog(*catalogValue);debugSources=parseNativeTaskDebugSourceUnion(*sourceValue);
      if(json(nativeTaskDebugInfoJSON(nativeTaskDebugInfo(debugCatalog,debugSources)),false)!=json(nativeTaskDebugInfoJSON(info),false)||json(nativeTaskDebugCatalogJSON(debugCatalog),false)!=json(nativeTaskDebugCatalogJSON(input.stage.debugCatalog),false)||json(nativeTaskDebugSourceUnionJSON(debugSources),false)!=json(nativeTaskDebugSourceUnionJSON(input.stage.debugSources),false))fail("captured debug metadata differs from checked stage");
      for(const auto &source:debugSources.components){auto bytes=readFile((folder/source.bundleFile).string());if(hash(bytes)!=source.bundleHash||!debugBundles.emplace(source.component,std::move(bytes)).second)fail("captured debug source bundle differs");}
      if(debugBundles!=input.stage.debugSourceBundles)fail("captured debug source bundle set differs");(void)loadNativeTaskDebugSources(folder.string(),debugCatalog,debugSources);
    }
    auto root=meta.get("task_application");
    if(!root||*root!=nativeTaskApplicationStageJSON(input.stage.taskApplication))fail("captured task application entry differs");
    if((input.kind=="executable")!=input.stage.taskApplication.enabled)fail("task image application entry selection differs");
  }
  return {&input,std::move(meta),read(folder/"debug.json"),read(folder/"compilation.json"),std::move(objects),std::move(provider),std::move(catalog),std::move(debugCatalog),std::move(debugSources),std::move(debugBundles)};
}
Object imageRecord(const fs::path &path,const std::string &key,const std::string &abi,const std::string &kind){
  return Object{{"path",path.string()},{"key",key},{"abi",abi},{"kind",kind},{"hash",digest(path)},{"sha256",sha(path)},{"uuid",uuid(path)}};
}
std::vector<std::string> strings(const Object &o,const char *key){
  auto array=o.getArray(key);if(!array)fail(std::string("missing captured image array: ")+key);
  std::vector<std::string> result;for(const auto &value:*array){auto s=value.getAsString();if(!s)fail("invalid captured image string array");result.push_back(s->str());}return result;
}
// DSOs work both at their original retained path (dependencies in images/) and
// as copied first-party dependencies (adjacent images). Linker arguments remain
// separate so commas, quotes, Unicode and literal percent signs stay data.
void rpaths(std::vector<std::string> &args,bool darwin,const NativeToolchain &tools,bool storage,bool foreign,bool server){
  if(llvm::Triple(tools.target).isOSWindows())return;
  for(const auto &path:darwin?std::vector<std::string>{"@loader_path","@loader_path/images"}:std::vector<std::string>{"$ORIGIN","$ORIGIN/images"})args.insert(args.end(),{"-Xlinker","-rpath","-Xlinker",path});
  std::set<std::string> paths;
  if(storage)paths.insert(fs::path(tools.sqliteLibrary).parent_path().string());
  if(foreign||server)paths.insert(fs::path(tools.opensslCrypto).parent_path().string());
  if(server)paths.insert(fs::path(tools.opensslSSL).parent_path().string());
  for(const auto &path:paths){if(!darwin&&path.find(':')!=std::string::npos)fail("ELF image library path contains ':'");args.insert(args.end(),{"-Xlinker","-rpath","-Xlinker",path});}
}
void archive(std::vector<std::string> &args,const fs::path &path,bool darwin){
  if(darwin)args.insert(args.end(),{"-Xlinker","-force_load","-Xlinker",path.string()});
  else args.insert(args.end(),{"-Xlinker","--whole-archive",path.string(),"-Xlinker","--no-whole-archive"});
}
void packageSymbols(const fs::path &image,const NativeToolchain &tools,bool darwin){
  if(darwin)run({tools.debugPackager,image.string(),"-o",image.string()+".dSYM"});
}
Array symbolFiles(const fs::path &image){
  Array result;auto folder=fs::path(image.string()+".dSYM");
  if(fs::is_directory(folder)){
    std::vector<fs::path> paths;for(const auto &entry:fs::recursive_directory_iterator(folder))if(entry.is_regular_file())paths.push_back(entry.path());
    std::sort(paths.begin(),paths.end());for(const auto &path:paths)result.push_back(Object{{"path",path.string()},{"hash",digest(path)}});
  }
  return result;
}
std::vector<std::string> flags(const NativeToolchain &tools,const fs::path &projection,const std::string &profile,bool foreign,bool sharedProfile){
  std::vector<std::string> f={"-std=c++20","-I",projection.string(),"-g",profile=="debug"?"-O0":"-O2","-fPIC"};
  if(foreign)f.insert(f.end(),{"-I",tools.opensslInclude,"-pthread","-DNEX_FOREIGN_ENABLED"});
  if(profile=="profile"){
    f.insert(f.end(),{"-fno-omit-frame-pointer","-pthread"});
    for(const auto *name:{"NEX_PROFILE_ENABLED","TRACY_ENABLE","TRACY_ON_DEMAND","TRACY_DELAYED_INIT","TRACY_MANUAL_LIFETIME","TRACY_ONLY_LOCALHOST","TRACY_NO_BROADCAST","TRACY_NO_CODE_TRANSFER","TRACY_NO_CALLSTACK","TRACY_NO_SYSTEM_TRACING","TRACY_NO_SAMPLING","TRACY_NO_CRASH_HANDLER","TRACY_NO_FRAME_IMAGE"})f.push_back(std::string("-D")+name);
    if(sharedProfile)f.push_back("-DNEX_SHARED_PROFILE_RUNTIME");
  }
  return f;
}
void compile(const NativeToolchain &tools,const fs::path &source,const fs::path &destination,const std::vector<std::string> &flags){
  Temporary temp;auto object=temp.path/"native.o";auto command=tools.driver;command.insert(command.end(),flags.begin(),flags.end());command.insert(command.end(),{"-c",source.string(),"-o",object.string()});run(std::move(command));copyCaptured(object,destination);
}
void link(const NativeToolchain &tools,const fs::path &projection,const fs::path &destination,std::vector<std::string> inputs,bool darwin,bool shared,bool storage,bool foreign,bool server){
  Temporary temp;auto output=temp.path/destination.filename();auto args=tools.driver;
  const bool windows=llvm::Triple(tools.target).isOSWindows();
  if(!tools.linker.empty())args.push_back("--ld-path="+tools.linker);
  if(windows){
    args.insert(args.end(),{"-static","-Wl,--build-id","-Wl,--no-insert-timestamp","-Wl,--export-all-symbols"});
    if(shared){
      // The OpenSSL assembly alias is private to its static archive. Exporting
      // it from the common NEX DLL conflicts with a server's own crypto link.
      args.insert(args.end(),{"-shared","-Wl,--exclude-symbols,CRYPTO_memcmp","-Xlinker","--out-implib","-Xlinker",output.string()+".a"});
    }
    else {
      args.push_back("-Wl,--stack,8388608");
      auto bin=fs::path(tools.compiler).parent_path();
      auto suffix=fs::path(tools.compiler).extension()==".exe"?".exe":"";
      auto rc=temp.path/"application.rc",res=temp.path/"application.res",coff=temp.path/"application.o";
      writeFile(rc.string(),"1 24 "+json((projection/"nex_windows.manifest").generic_string(),false)+"\n");
      run({(bin/(std::string("llvm-rc")+suffix)).string(),"/no-preprocess","/X","/C","65001","/FO",res.string(),rc.string()});
      run({(bin/(std::string("llvm-cvtres")+suffix)).string(),llvm::Triple(tools.target).getArch()==llvm::Triple::aarch64?"/MACHINE:ARM64":"/MACHINE:X64","/TIMESTAMP:0","/OUT:"+coff.string(),res.string()});
      inputs.push_back(coff.string());
    }
  }else if(shared){
    if(darwin)args.push_back("-dynamiclib");else args.insert(args.end(),{"-shared","-Xlinker","-z","-Xlinker","defs"});
    args.insert(args.end(),{"-Xlinker",darwin?"-install_name":"-soname","-Xlinker",(darwin?"@rpath/":"")+destination.filename().string()});
  }else args.insert(args.end(),{"-Xlinker",darwin?"-export_dynamic":"--export-dynamic"});
  if(!darwin&&!windows)args.insert(args.end(),{"-Xlinker","--build-id=sha1"});
  args.insert(args.end(),inputs.begin(),inputs.end());
  if(windows)args.insert(args.end(),{"-lntdll","-lbcrypt","-ladvapi32","-lcrypt32","-lws2_32","-lsecur32","-ldbghelp","-ldwmapi"});
  rpaths(args,darwin,tools,storage,foreign,server);args.insert(args.end(),{"-o",output.string(),"-g"});run(std::move(args));copyCaptured(output,destination);
  if(windows&&shared)copyCaptured(output.string()+".a",destination.string()+".a");
  packageSymbols(destination,tools,darwin);
}
void provided(const Captured &stage,std::map<std::string,std::string> &contracts){
  if(stage.taskProvider.enabled){
    for(const auto &name:stage.taskProvider.definitions){auto contract=stage.input->stage.functionContracts.at(name);if(!contracts.emplace(name,contract).second)fail("duplicate emitted task definition: "+name);}return;
  }
  for(const auto &unit:*stage.compilation.getArray("units")){
    auto name=text(*unit.getAsObject(),"identity");auto contract=stage.input->stage.functionContracts.at(name);
    auto [old,inserted]=contracts.emplace(name,contract);if(!inserted&&old->second!=contract)fail("conflicting emitted function contract: "+name);
  }
}
}


NativeImageResults buildNativeImages(const std::string &directory,const std::vector<NativeImageInput> &inputs){
  if(inputs.empty())fail("shared image linking needs checked stages");
  auto root=fs::absolute(directory);auto tools=configureNative(inputs.front().options);llvm::Triple triple(tools.target);
  bool darwin=triple.isMacOSX(),windows=triple.isOSWindows();if(!darwin&&!triple.isOSLinux()&&!windows)fail("shared native images require macOS, Linux or Windows");
  std::map<std::string,Captured> stages;std::map<std::string,std::string> sources;std::set<std::string> components,notices;
  const bool sharedTasks=effectiveNativeTaskLinkage(inputs.front().options)==NativeTaskLinkageMode::SharedFixed;
  const bool taskProfiling=sharedTasks&&inputs.front().options.profile=="profile";
  const bool taskDebugging=sharedTasks&&inputs.front().options.taskDebug;
  bool tasks=false,taskReads=false,taskWrites=false,taskStreams=false;
  bool storage=false,foreign=false,profiling=false,wire=false,files=false,parallel=false,taskDebug=false;auto abi=inputs.front().stage.libraryABI;auto profile=inputs.front().options.profile;
  std::string foreignDefault;
  auto toolchainFingerprint=inspectNativeToolchain(inputs.front().options).hash;
  auto verifyToolchain=[&](){if(inspectNativeToolchain(inputs.front().options).hash!=toolchainFingerprint)fail("native image toolchain changed while linking");};
  for(const auto &input:inputs){
    if((effectiveNativeTaskLinkage(input.options)==NativeTaskLinkageMode::SharedFixed)!=sharedTasks)fail("cannot merge different task linkage modes in one runtime image");
    if(input.options.taskDebug!=inputs.front().options.taskDebug)fail("cannot merge debug and ordinary native stages in one runtime image");
    if(input.stage.libraryABI!=abi||input.options.profile!=profile||configureNative(input.options).identity!=tools.identity)fail("shared image stages have different target/runtime/toolchain ABIs");
    auto stage=capture(input);if(text(stage.build,"toolchain_fingerprint")!=toolchainFingerprint)fail("captured stage toolchain differs from image linker");
    auto selectedDefault=text(stage.build,"foreign_catalogue");
    if(selectedDefault!=input.options.foreignCatalogue)fail("captured foreign default differs from its image stage");
    if(!selectedDefault.empty()){
      if(selectedDefault!="../foreign/host.json"||input.kind=="shared_library"||input.kind=="static_library")fail("invalid application foreign default");
      foreignDefault=selectedDefault;
    }
    auto requirements=stage.build.getObject("runtime_requirements");if(!requirements)fail("missing shared runtime requirements");
    auto stageTaskDebug=requirements->getBoolean("task_debug").value_or(false);
    if(stageTaskDebug!=input.options.taskDebug||stage.build.getBoolean("task_debug").value_or(false)!=stageTaskDebug)fail("captured task debug selection differs from its image stage");
    if(stageTaskDebug&&!taskDebugging&&(input.kind!="executable"||!input.dynamicDependencies.empty()||!input.staticDependencies.empty()))fail("task debug binary providers require a checked debug provider cohort");
    taskDebug|=stageTaskDebug;
    storage|=requirements->getBoolean("storage").value_or(false);foreign|=requirements->getBoolean("foreign").value_or(false);profiling|=requirements->getBoolean("profiling").value_or(false);
    wire|=requirements->getBoolean("wire").value_or(false);files|=requirements->getBoolean("files").value_or(false);
    parallel|=requirements->getBoolean("parallel").value_or(false);
    if(sharedTasks){tasks|=requirements->getBoolean("tasks").value_or(false);taskReads|=requirements->getBoolean("task_file_reads").value_or(false);taskWrites|=requirements->getBoolean("task_file_writes").value_or(false);taskStreams|=requirements->getBoolean("task_file_streams").value_or(false);}
    auto inventory=stage.build.getObject("runtime_inputs");if(!inventory)fail("missing captured runtime inventory");
    auto projection=fs::path(text(stage.build,"runtime_source_projection"));
    for(const auto &[name,value]:*inventory){
      auto data=readFile((projection/name.str()).string());if(value.getAsString()!=hash(data))fail("captured runtime file changed: "+name.str());
      auto [old,inserted]=sources.emplace(name.str(),data);if(!inserted&&old->second!=data)fail("conflicting captured runtime file: "+name.str());
    }
    for(const auto &component:strings(stage.build,"runtime_components"))if(component!="http_main.cpp")components.insert(component);
    if(!input.stage.notices.empty())notices.insert(readFile(input.stage.notices));stages.emplace(input.name,std::move(stage));
  }
  Object runtimeInputs;for(const auto &[name,data]:sources)runtimeInputs[name]=hash(data);
  Array componentNames;for(const auto &name:components)componentNames.push_back(name);
  const bool ownedExecutor=components.contains("nex_resource_executor.cpp");
  Object requirements{{"wire",wire},{"storage",storage},{"files",files},{"foreign",foreign},{"profiling",profiling},{"parallel",parallel},{"task_debug",taskDebug}};
  Object runtimeSeed{{"schema","nex.native-runtime-input/1"},{"compiler_build",NEX_BUILD_ID},{"abi",abi},{"toolchain",tools.identity},{"toolchain_fingerprint",toolchainFingerprint},{"profile",profile},
    {"cache",root.string()},{"cwd",fs::current_path().string()},{"inputs",std::move(runtimeInputs)},{"components",std::move(componentNames)},
    {"shared_profile_identity",profiling},{"task_debug",taskDebug},{"foreign",foreign},{"storage",storage},{"parallel",parallel},{"owned_executor_pthread",ownedExecutor},{"foreign_catalogue",foreignDefault}};
  if(windows){Object resources;auto bin=fs::path(tools.compiler).parent_path();auto suffix=fs::path(tools.compiler).extension()==".exe"?".exe":"";
    for(const auto *name:{"llvm-rc","llvm-cvtres"}){auto tool=bin/(std::string(name)+suffix);resources[tool.string()]=digest(tool);}runtimeSeed["windows_resource_tools"]=std::move(resources);}
  if(sharedTasks){requirements["tasks"]=tasks;requirements["task_file_reads"]=taskReads;requirements["task_file_writes"]=taskWrites;runtimeSeed["task_linkage_mode"]="shared-fixed";runtimeSeed["tasks"]=tasks;runtimeSeed["task_file_reads"]=taskReads;runtimeSeed["task_file_writes"]=taskWrites;}
  if(sharedTasks&&supportsTaskFileStreams(*inputs.front().program)){requirements["task_file_streams"]=taskStreams;runtimeSeed["task_file_streams"]=taskStreams;}
  if(sharedTasks&&supportsSourceExceptionTasks(*inputs.front().program)){const auto abi=isTypedSourceErrorLanguage(inputs.front().program->sourceLanguage)?nexrt::taskCodeTypedSourceExceptionABI:nexrt::taskCodeSourceExceptionABI;requirements["task_execution_abi"]=abi;runtimeSeed["task_execution_abi"]=abi;}
  auto runtimeText=json(JSON(Object(runtimeSeed)),false),runtimeKey=hash(runtimeText);auto runtimeFolder=root/("runtime-"+runtimeKey);
  auto extension=windows?".dll":darwin?".dylib":".so";auto runtime=runtimeFolder/("libnex_runtime_"+runtimeKey+extension);auto projection=runtimeFolder/"runtime-inputs";
  for(const auto &[name,data]:sources)writeFile((projection/name).string(),data);
  std::string noticeText;for(const auto &notice:notices)noticeText+=notice+'\n';
  auto runtimeIntact=[&](){try{
    auto record=read(runtimeFolder/"image.json");if(text(record,"key")!=runtimeKey||text(record,"hash")!=digest(runtime)||text(record,"sha256")!=sha(runtime)||text(record,"uuid")!=uuid(runtime)||readFile((runtimeFolder/"inputs.json").string())!=runtimeText)return false;
    auto symbols=record.getArray("symbols");if(!symbols)return false;for(const auto &s:*symbols)if(text(*s.getAsObject(),"hash")!=digest(text(*s.getAsObject(),"path")))return false;
    return readFile((runtimeFolder/"complete").string())==hash(runtimeKey+digest(runtime)+digest(runtimeFolder/"image.json")+hash(runtimeText)+(windows?digest(runtime.string()+".a"):""))+"\n";
  }catch(const std::exception &){return false;}};
  if(!runtimeIntact()){
    std::vector<std::string> objects;auto runtimeFlags=flags(tools,projection,profile,foreign,true);
    if(windows)runtimeFlags.push_back("-DNEX_SHARED_WINDOWS_RUNTIME");
    // Owned cleanup brings the external executor even without source tasks.
    // GNU C++ runtimes on older glibc still require explicit pthread linkage.
    if(parallel||tasks||ownedExecutor)runtimeFlags.push_back("-pthread");
    if(parallel||tasks)runtimeFlags.push_back("-DNEX_STRUCTURED_WORKERS");
    if(tasks)runtimeFlags.push_back("-DNEX_ASYNC_TASKS");
    if(taskProfiling)runtimeFlags.push_back("-DNEX_TASK_PROFILE_ENABLED");
    if(taskDebug)runtimeFlags.insert(runtimeFlags.end(),{"-DNEX_TASK_DEBUG_ENABLED","-DNEX_ASYNC_TASKS","-DNEX_STRUCTURED_WORKERS","-pthread"});
    if(!foreignDefault.empty())runtimeFlags.push_back("-DNEX_FOREIGN_DEFAULT="+json(foreignDefault,false));
    for(const auto &component:components){auto object=runtimeFolder/("runtime-"+std::to_string(objects.size())+".o");compile(tools,projection/component,object,runtimeFlags);objects.push_back(object.string());}
    if(storage)objects.push_back(tools.sqliteLibrary);
    if(foreign){objects.insert(objects.end(),{tools.opensslCrypto,"-pthread"});if(!darwin&&!windows)objects.push_back("-ldl");}
    if(profiling){objects.push_back("-pthread");if(!darwin&&!windows)objects.push_back("-ldl");}
    if(parallel||tasks||ownedExecutor)objects.push_back("-pthread");
    link(tools,projection,runtime,std::move(objects),darwin,true,storage,foreign,false);
    verifyToolchain();auto record=imageRecord(runtime,runtimeKey,abi,"runtime");record["symbols"]=symbolFiles(runtime);record["inputs"]=Object(runtimeSeed);record["requirements"]=Object(requirements);
    writeFile((runtimeFolder/"inputs.json").string(),runtimeText);writeFile((runtimeFolder/"image.json").string(),json(JSON(Object(record))));
    writeFile((runtimeFolder/"complete").string(),hash(runtimeKey+digest(runtime)+digest(runtimeFolder/"image.json")+hash(runtimeText)+(windows?digest(runtime.string()+".a"):""))+"\n");
  }
  NativeImageResults result;result.runtime=read(runtimeFolder/"image.json");
  for(const auto &input:inputs){
    if(input.kind=="static_library")continue;
    const auto &stage=stages.at(input.name);bool shared=input.kind=="shared_library",server=input.kind=="server";
    Array statics,dynamics;
    for(const auto &name:input.staticDependencies){const auto &s=stages.at(name);auto row=Object{{"component",name},{"hash",hash(s.objects)},{"abi",s.input->stage.libraryABI}};if(sharedTasks)row["task_provider_hash"]=s.input->stage.taskProviderDigest;statics.push_back(std::move(row));}
    for(const auto &name:input.dynamicDependencies){auto found=result.images.find(name);if(found==result.images.end())fail("dynamic image order is not dependency-first: "+name);auto row=Object{{"component",name},{"hash",digest(found->second.executable)},{"key",found->second.key}};if(sharedTasks)row["task_provider_hash"]=found->second.taskProviderDigest;dynamics.push_back(std::move(row));}
    NativeTaskProfileCatalog localCatalog,rootCatalog;
    if(taskProfiling){
      localCatalog.mode=NativeTaskLinkageMode::SharedFixed;localCatalog.artifact=shared?NativeTaskArtifactKind::SharedImage:NativeTaskArtifactKind::Application;localCatalog.ownerImage=input.name;
      auto merge=[&](const NativeTaskProfileCatalog &catalog,const std::string &owner){for(auto registry:catalog.registries){registry.ownerImage=owner;localCatalog.registries.push_back(std::move(registry));}};
      merge(stage.profileCatalog,input.name);for(const auto &name:input.staticDependencies)merge(stages.at(name).profileCatalog,input.name);
      std::sort(localCatalog.registries.begin(),localCatalog.registries.end(),[](const auto &a,const auto &b){return a.component<b.component;});
      (void)nativeTaskProfileInfo(localCatalog);rootCatalog=localCatalog;
      if(!shared)for(const auto &name:input.dynamicDependencies)for(const auto &registry:result.images.at(name).profileCatalog.registries)rootCatalog.registries.push_back(registry);
      std::sort(rootCatalog.registries.begin(),rootCatalog.registries.end(),[](const auto &a,const auto &b){return a.component<b.component;});(void)nativeTaskProfileInfo(rootCatalog);
    }
    NativeTaskDebugCatalog localDebug,rootDebug;NativeTaskDebugSourceUnion localSources,rootSources;std::map<std::string,std::string> localBundles,rootBundles;
    if(taskDebugging){
      localDebug.mode=NativeTaskLinkageMode::SharedFixed;localDebug.artifact=shared?NativeTaskArtifactKind::SharedImage:NativeTaskArtifactKind::Application;localDebug.ownerImage=input.name;
      localSources.mode=localDebug.mode;localSources.artifact=localDebug.artifact;localSources.ownerImage=input.name;
      auto merge=[&](const Captured &from){for(auto registry:from.debugCatalog.registries){registry.ownerImage=input.name;localDebug.registries.push_back(std::move(registry));}for(auto source:from.debugSources.components){source.ownerImage=input.name;localSources.components.push_back(std::move(source));}for(const auto &[name,bytes]:from.debugBundles)if(!localBundles.emplace(name,bytes).second)fail("duplicate embedded debug component");};
      merge(stage);for(const auto &name:input.staticDependencies)merge(stages.at(name));
      auto sort=[](auto &catalog,auto &sources){std::sort(catalog.registries.begin(),catalog.registries.end(),[](const auto &a,const auto &b){return a.component<b.component;});std::sort(sources.components.begin(),sources.components.end(),[](const auto &a,const auto &b){return a.component<b.component;});(void)nativeTaskDebugInfo(catalog,sources);};sort(localDebug,localSources);
      rootDebug=localDebug;rootSources=localSources;rootBundles=localBundles;
      if(!shared)for(const auto &name:input.dynamicDependencies){const auto &dependency=result.images.at(name);for(const auto &registry:dependency.debugCatalog.registries)rootDebug.registries.push_back(registry);for(const auto &source:dependency.debugSources.components)rootSources.components.push_back(source);for(const auto &[component,bytes]:dependency.debugSourceBundles){auto [old,inserted]=rootBundles.emplace(component,bytes);if(!inserted&&old->second!=bytes)fail("conflicting loaded debug source component");}}
      sort(rootDebug,rootSources);
    }
    Object seed{{"schema","nex.native-image-input/1"},{"compiler_build",NEX_BUILD_ID},{"component",input.name},{"kind",input.kind},{"stage",input.stage.key},{"objects",hash(stage.objects)},
      {"runtime_key",runtimeKey},{"runtime_hash",digest(runtime)},{"abi",abi},{"static_libraries",std::move(statics)},{"dynamic_libraries",std::move(dynamics)}};
    if(sharedTasks){seed["schema"]="nex.native-image-input/2";seed["mode"]="shared-fixed";seed["task_provider_hash"]=input.stage.taskProviderDigest;seed["task_application"]=nativeTaskApplicationStageJSON(input.stage.taskApplication);}
    if(taskProfiling){seed["schema"]="nex.native-image-input/3";seed["task_profile_catalog"]=nativeTaskProfileInfo(rootCatalog).catalogHash;}
    if(taskDebugging){seed["schema"]="nex.native-image-input/4";seed["task_debug_catalog"]=nativeTaskDebugInfo(rootDebug,rootSources).catalogHash;seed["task_debug_source_union"]=nativeTaskDebugInfo(rootDebug,rootSources).sourceUnionHash;}
    auto seedText=json(JSON(Object(seed)),false),key=hash(seedText);auto folder=root/key;
    auto executable=folder/(shared?"libnex_"+input.name+"_"+key+extension:windows?"app.exe":"app");
    const auto imagesFolder=windows?folder:folder/"images";
    const auto imagePath=[&](const std::string &name){return windows?name:"images/"+name;};
    BuildResult built=input.stage;built.executable=executable.string();built.key=key;built.mlir=(folder/"program.mlir").string();built.llvm=(folder/"program.ll").string();built.compilation=(folder/"compilation.json").string();built.notices=(folder/"THIRD_PARTY_NOTICES.txt").string();built.cached=false;
    built.parallelCalls=parallel;
    if(sharedTasks){
      auto &provider=built.taskProvider;provider=NativeTaskProviderInfo{};provider.enabled=true;provider.mode=NativeTaskLinkageMode::SharedFixed;
      provider.artifact=shared?NativeTaskArtifactKind::SharedImage:NativeTaskArtifactKind::Application;provider.codeOnly=shared;provider.component=input.name;provider.ownerImage=input.name;provider.cohort=abi;provider.language=programLanguage(*input.program);
      auto merge=[&](const Captured &source){const auto &info=source.taskProvider;
        for(const auto &name:info.definitions){if(!provider.definitions.insert(name).second)fail("duplicate task definition in final image: "+name);provider.definitionOwners[name]=info.definitionOwners.at(name);}
        for(const auto &[name,value]:info.componentFileReads){auto [old,inserted]=provider.componentFileReads.emplace(name,value);if(!inserted&&old->second!=value)fail("task component read flag changed");provider.taskFileReads|=value;}
        for(const auto &[name,value]:info.componentFileWrites){auto [old,inserted]=provider.componentFileWrites.emplace(name,value);if(!inserted&&old->second!=value)fail("task component write flag changed");provider.taskFileWrites|=value;}
        for(const auto &[name,value]:info.componentFileStreams){auto [old,inserted]=provider.componentFileStreams.emplace(name,value);if(!inserted&&old->second!=value)fail("task component stream flag changed");provider.taskFileStreams|=value;}
        for(const auto &[name,value]:info.exports)if(!provider.exports.emplace(name,value).second)fail("duplicate task accessor in final image: "+name);
      };merge(stage);for(const auto &name:input.staticDependencies)merge(stages.at(name));
      if(taskProfiling){built.profileCatalog=localCatalog;provider.profiling=nativeTaskProfileInfo(localCatalog);}
      if(taskDebugging){built.debugCatalog=localDebug;built.debugSources=localSources;built.debugSourceBundles=localBundles;provider.debugging=nativeTaskDebugInfo(localDebug,localSources);}
      built.taskProviderFile=(folder/"task-provider.json").string();built.taskProviderDigest.clear();
    }
    built.functionContracts.clear();provided(stage,built.functionContracts);for(const auto &name:input.staticDependencies)provided(stages.at(name),built.functionContracts);
    fs::create_directories(imagesFolder);copyCaptured(input.stage.executable,folder/"objects.a");
    Array completion;completion.push_back(Object{{"kind","abi"},{"path","library-abi.json"}});if(sharedTasks)completion.push_back(Object{{"kind","task_provider"},{"path","task-provider.json"}});if(taskProfiling)completion.push_back(Object{{"kind","profile_catalog"},{"path","task-profile-catalog.json"}});
    if(taskDebugging){completion.push_back(Object{{"kind","debug_catalog"},{"path","task-debug-catalog.json"}});completion.push_back(Object{{"kind","debug_sources"},{"path","task-debug-sources.json"}});(void)writeNativeTaskDebugSources(folder.string(),rootDebug,rootSources,rootBundles);for(auto &value:nativeTaskDebugSourceInputs(rootDebug,rootSources,rootBundles))completion.push_back(std::move(value));}
    completion.push_back(Object{{"kind","link_inputs"},{"path","image-inputs.json"}});completion.push_back(Object{{"kind","objects"},{"path","objects.a"}});
    Array staticInventory;std::vector<std::string> linkInputs;archive(linkInputs,folder/"objects.a",darwin);
    for(size_t i=0;i<input.staticDependencies.size();++i){
      const auto &dependency=stages.at(input.staticDependencies[i]);auto relative="libraries/"+std::to_string(i)+".a";
      writeFile((folder/relative).string(),dependency.objects);archive(linkInputs,folder/relative,darwin);completion.push_back(Object{{"kind","static_library"},{"path",relative}});
      Object contracts;for(const auto &[name,digest]:dependency.input->stage.functionContracts)contracts[name]=digest;
      auto row=Object{{"component",input.staticDependencies[i]},{"path",(folder/relative).string()},{"hash",hash(dependency.objects)},{"abi",abi},{"contracts",std::move(contracts)}};
      if(sharedTasks){auto sidecar="libraries/"+std::to_string(i)+".task-provider.json";auto bytes=readFile(dependency.input->stage.taskProviderFile);if(hash(bytes)!=dependency.input->stage.taskProviderDigest)fail("static task stage sidecar changed");writeFile((folder/sidecar).string(),bytes);completion.push_back(Object{{"kind","static_task_provider"},{"path",sidecar}});row["task_provider_path"]=(folder/sidecar).string();row["task_provider_hash"]=hash(bytes);row["task_provider"]=nativeTaskProviderJSON(dependency.taskProvider);
        if(taskProfiling){auto name="libraries/"+std::to_string(i)+".task-profile-catalog.json";auto source=fs::path(dependency.input->stage.taskProviderFile).parent_path()/"task-profile-catalog.json";auto raw=readFile(source.string());auto parsed=llvm::json::parse(raw);if(!parsed||nativeTaskProfileInfo(parseNativeTaskProfileCatalog(*parsed)).catalogHash!=dependency.taskProvider.profiling->catalogHash)fail("static profile catalog changed");writeFile((folder/name).string(),raw);completion.push_back(Object{{"kind","static_profile_catalog"},{"path",name}});row["task_profile_catalog_path"]=(folder/name).string();row["task_profile_catalog_hash"]=hash(raw);}
        if(taskDebugging){auto source=fs::path(dependency.input->stage.taskProviderFile).parent_path();for(const auto &[suffix,kind,key]:std::vector<std::tuple<std::string,std::string,std::string>>{{"task-debug-catalog.json","static_debug_catalog","task_debug_catalog"},{"task-debug-sources.json","static_debug_sources","task_debug_sources"}}){auto name="libraries/"+std::to_string(i)+"."+suffix;auto raw=readFile((source/suffix).string());writeFile((folder/name).string(),raw);completion.push_back(Object{{"kind",kind},{"path",name}});row[key+"_path"]=(folder/name).string();row[key+"_hash"]=hash(raw);}}
      }
      staticInventory.push_back(std::move(row));
    }
    std::map<std::string,Object> images;images.emplace(runtime.filename().string(),read(runtimeFolder/"image.json"));
    for(const auto &name:input.dynamicDependencies){const auto &dependency=result.images.at(name);images.emplace(fs::path(dependency.executable).filename().string(),imageRecord(dependency.executable,dependency.key,abi,"library"));
      auto meta=read(fs::path(dependency.executable).parent_path()/"image-inputs.json");for(const auto &value:*meta.getArray("images")){const auto &record=*value.getAsObject();images.emplace(fs::path(text(record,"path")).filename().string(),Object(record));}}
    std::map<std::string,std::string> providerRecords,profileRecords,debugCatalogRecords,debugSourceRecords;
    if(sharedTasks)for(const auto &name:input.dynamicDependencies){const auto &dependency=result.images.at(name);
      auto bytes=readFile(dependency.taskProviderFile);if(hash(bytes)!=dependency.taskProviderDigest)fail("dynamic task provider changed");
      auto add=[&](const std::string &image,const std::string &record){auto [old,inserted]=providerRecords.emplace(image,record);if(!inserted&&old->second!=record)fail("conflicting owned task image provider");};
      add(fs::path(dependency.executable).filename().string(),bytes);
      auto addProfile=[&](const std::string &image,const std::string &raw){auto [old,inserted]=profileRecords.emplace(image,raw);if(!inserted&&old->second!=raw)fail("conflicting owned profile catalog");};
      if(taskProfiling)addProfile(fs::path(dependency.executable).filename().string(),readFile((fs::path(dependency.executable).parent_path()/"task-profile-catalog.json").string()));
      auto addDebug=[&](const std::string &image,const std::string &catalog,const std::string &sources){auto [c,ci]=debugCatalogRecords.emplace(image,catalog);auto [s,si]=debugSourceRecords.emplace(image,sources);if((!ci&&c->second!=catalog)||(!si&&s->second!=sources))fail("conflicting owned debug metadata");};
      if(taskDebugging){auto parent=fs::path(dependency.executable).parent_path();addDebug(fs::path(dependency.executable).filename().string(),readFile((parent/"task-debug-catalog.json").string()),readFile((parent/"task-debug-sources.json").string()));}
      auto metadata=read(fs::path(dependency.executable).parent_path()/"image-inputs.json");auto records=metadata.getArray("task_providers");if(!records)fail("missing transitive task provider inventory");
      for(const auto &value:*records){const auto &record=*value.getAsObject();auto path=fs::path(dependency.executable).parent_path()/text(record,"path");auto data=readFile(path.string());if(hash(data)!=text(record,"hash"))fail("owned task provider pin changed");add(fs::path(text(record,"image")).filename().string(),data);}
      if(taskProfiling){auto catalogs=metadata.getArray("task_profile_catalogs");if(!catalogs)fail("missing transitive profile catalog inventory");for(const auto &value:*catalogs){const auto &record=*value.getAsObject();auto raw=readFile((fs::path(dependency.executable).parent_path()/text(record,"path")).string());if(hash(raw)!=text(record,"hash"))fail("owned profile catalog pin changed");addProfile(fs::path(text(record,"image")).filename().string(),raw);}}
      if(taskDebugging){auto catalogs=metadata.getArray("task_debug_catalogs"),sources=metadata.getArray("task_debug_sources");if(!catalogs||!sources||catalogs->size()!=sources->size())fail("missing transitive debug metadata inventory");std::map<std::string,std::string> capturedSources;
        for(const auto &value:*sources){const auto &row=*value.getAsObject();auto raw=readFile((fs::path(dependency.executable).parent_path()/text(row,"path")).string());if(hash(raw)!=text(row,"hash")||!capturedSources.emplace(text(row,"image"),raw).second)fail("owned debug source union pin differs");}
        for(const auto &value:*catalogs){const auto &row=*value.getAsObject();auto raw=readFile((fs::path(dependency.executable).parent_path()/text(row,"path")).string());if(hash(raw)!=text(row,"hash")||!capturedSources.contains(text(row,"image")))fail("owned debug catalog pin differs");addDebug(fs::path(text(row,"image")).filename().string(),raw,capturedSources.at(text(row,"image")));}
      }
    }
    Array imageInventory,providerInventory,profileInventory,debugCatalogInventory,debugSourceInventory;
    for(auto &[name,record]:images){
      auto original=fs::path(text(record,"path")),captured=imagesFolder/name;copyCaptured(original,captured);if(digest(captured)!=text(record,"hash"))fail("owned image changed during capture");
      if(windows)copyCaptured(original.string()+".a",captured.string()+".a");
      record["path"]=captured.string();record["symbols"]=symbolFiles(original);
      Array capturedSymbols;
      for(const auto &value:*record.getArray("symbols")){const auto &s=*value.getAsObject();auto from=fs::path(text(s,"path"));auto suffix=from.lexically_relative(fs::path(original.string()+".dSYM"));auto to=fs::path(captured.string()+".dSYM")/suffix;copyCaptured(from,to);capturedSymbols.push_back(Object{{"path",to.string()},{"hash",digest(to)}});}
      record["symbols"]=std::move(capturedSymbols);imageInventory.push_back(Object(record));completion.push_back(Object{{"kind","owned_image"},{"path",imagePath(name)}});
    }
    if(windows){
      std::set<std::string> imports;
      for(const auto &[name,record]:images)imports.insert(imagePath(name)+".a");
      if(shared)imports.insert(executable.filename().string()+".a");
      for(const auto &path:imports)completion.push_back(Object{{"kind","import_library"},{"path",path}});
    }
    if(sharedTasks)for(const auto &[name,record]:images)if((text(record,"kind")=="library")!=providerRecords.contains(name))fail("owned task provider inventory differs from library images");
    if(sharedTasks)for(const auto &[name,bytes]:providerRecords){if(!images.contains(name)||text(images.at(name),"kind")!="library")fail("task provider does not name an owned library image");
      auto parsed=llvm::json::parse(bytes);if(!parsed)fail("invalid owned task provider");auto info=parseNativeTaskProvider(*parsed);const auto &owned=images.at(name);
      if(info.artifact!=NativeTaskArtifactKind::SharedImage||!info.image||info.image->key!=text(owned,"key")||info.image->digest!=text(owned,"hash")||info.image->sha256!=text(owned,"sha256")||info.image->uuid!=text(owned,"uuid")||info.image->runtimeKey!=runtimeKey||info.image->runtimeDigest!=digest(runtime))fail("owned task provider image identity differs");
      auto path=imagePath(name)+".task-provider.json";writeFile((folder/path).string(),bytes);providerInventory.push_back(Object{{"image",imagePath(name)},{"path",path},{"hash",hash(bytes)},{"component",info.component}});completion.push_back(Object{{"kind","owned_task_provider"},{"path",path}});
      if(taskProfiling){if(!info.profiling||!profileRecords.contains(name))fail("owned image omitted profile catalog");const auto &raw=profileRecords.at(name);auto parsedCatalog=llvm::json::parse(raw);if(!parsedCatalog)fail("invalid owned profile catalog");auto catalog=parseNativeTaskProfileCatalog(*parsedCatalog);
        if(nativeTaskProfileInfo(catalog).catalogHash!=info.profiling->catalogHash||catalog.ownerImage!=info.component)fail("owned profile catalog identity differs");
        auto relative=imagePath(name)+".task-profile-catalog.json";writeFile((folder/relative).string(),raw);profileInventory.push_back(Object{{"image",imagePath(name)},{"path",relative},{"hash",hash(raw)},{"catalog_hash",info.profiling->catalogHash},{"component",info.component}});completion.push_back(Object{{"kind","owned_profile_catalog"},{"path",relative}});
      }
      if(taskDebugging){if(!info.debugging||!debugCatalogRecords.contains(name)||!debugSourceRecords.contains(name))fail("owned image omitted debug metadata");auto c=llvm::json::parse(debugCatalogRecords.at(name)),s=llvm::json::parse(debugSourceRecords.at(name));if(!c||!s)fail("invalid owned debug metadata");auto catalog=parseNativeTaskDebugCatalog(*c);auto sources=parseNativeTaskDebugSourceUnion(*s);if(catalog.ownerImage!=info.component||json(nativeTaskDebugInfoJSON(nativeTaskDebugInfo(catalog,sources)),false)!=json(nativeTaskDebugInfoJSON(*info.debugging),false))fail("owned debug metadata identity differs");
        auto catalogPath=imagePath(name)+".task-debug-catalog.json",sourcePath=imagePath(name)+".task-debug-sources.json";writeFile((folder/catalogPath).string(),debugCatalogRecords.at(name));writeFile((folder/sourcePath).string(),debugSourceRecords.at(name));
        debugCatalogInventory.push_back(Object{{"image",imagePath(name)},{"path",catalogPath},{"hash",hash(debugCatalogRecords.at(name))},{"catalog_hash",info.debugging->catalogHash},{"component",info.component}});debugSourceInventory.push_back(Object{{"image",imagePath(name)},{"path",sourcePath},{"hash",hash(debugSourceRecords.at(name))},{"source_union_hash",info.debugging->sourceUnionHash},{"component",info.component}});completion.push_back(Object{{"kind","owned_debug_catalog"},{"path",catalogPath}});completion.push_back(Object{{"kind","owned_debug_sources"},{"path",sourcePath}});
      }
    }
    for(const auto &record:imageInventory)for(const auto &symbol:*record.getAsObject()->getArray("symbols"))completion.push_back(Object{{"kind","owned_symbols"},{"path",fs::path(text(*symbol.getAsObject(),"path")).lexically_relative(folder).generic_string()}});
    if(taskDebugging){completion.push_back(Object{{"kind","debug_manifest"},{"path","debug.json"}});completion.push_back(Object{{"kind","debug_formatter"},{"path","debugger/lldb_nex.py"}});completion.push_back(Object{{"kind","debug_adapter"},{"path","debugger/nex_dap.py"}});}
    if(taskDebugging&&!shared&&darwin)for(const auto &path:{"debug-symbols.complete","app.dSYM/Contents/Info.plist","app.dSYM/Contents/Resources/DWARF/app"})completion.push_back(Object{{"kind","root_symbols"},{"path",path}});
    for(const auto &name:input.dynamicDependencies)linkInputs.push_back((imagesFolder/fs::path(result.images.at(name).executable).filename()).string()+(windows?".a":""));
    linkInputs.push_back((imagesFolder/runtime.filename()).string()+(windows?".a":""));
    if(taskProfiling&&profileRecords.size()!=providerRecords.size())fail("profile catalog closure differs from code images");
    if(taskDebugging&&(debugCatalogRecords.size()!=providerRecords.size()||debugSourceRecords.size()!=providerRecords.size()))fail("debug metadata closure differs from code images");
    auto stageFolder=fs::path(input.stage.executable).parent_path();copyCaptured(stageFolder/"program.mlir",folder/"program.mlir");copyCaptured(stageFolder/"program.ll",folder/"program.ll");copyCaptured(stageFolder/"source-bundle.json",folder/"source-bundle.json");
    auto debug=Object(stage.debug);debug["program"]=executable.string();debug["build_key"]=key;debug["owned_images"]=Array(imageInventory);
    for(const auto *file:{"lldb_nex.py","nex_dap.py"})copyCaptured(stageFolder/"debugger"/file,folder/"debugger"/file);
    debug["formatter"]=(folder/"debugger/lldb_nex.py").string();debug["dap_adapter"]=(folder/"debugger/nex_dap.py").string();
    auto debugTextFor=[&]{auto record=Object(debug);if(auto task=record.getObject("task_debug")){
      (*task)["image_sha256"]="";(*task)["image_uuid"]="";
      if(fs::is_regular_file(executable))try{(*task)["image_sha256"]=sha(executable);(*task)["image_uuid"]=uuid(executable);}catch(const Error &){}
    }
      if(taskDebugging&&!shared&&fs::is_regular_file(executable)){Array owners;Object runtimeOwner;
        owners.push_back(Object{{"component",input.name},{"path",executable.string()},{"key",key},{"hash",digest(executable)},{"sha256",sha(executable)},{"uuid",uuid(executable)},{"kind","application"}});
        for(const auto &value:imageInventory){const auto &row=*value.getAsObject();if(row.getString("kind")=="runtime")runtimeOwner=Object{{"component",nullptr},{"path",text(row,"path")},{"key",text(row,"key")},{"hash",text(row,"hash")},{"sha256",text(row,"sha256")},{"uuid",text(row,"uuid")},{"kind","runtime"}};}
        for(const auto &value:providerInventory){const auto &row=*value.getAsObject();auto name=fs::path(text(row,"image")).filename().string();const auto &owner=images.at(name);owners.push_back(Object{{"component",text(row,"component")},{"path",text(owner,"path")},{"key",text(owner,"key")},{"hash",text(owner,"hash")},{"sha256",text(owner,"sha256")},{"uuid",text(owner,"uuid")},{"kind","shared-image"}});}
        record=finalizeNativeTaskDebugManifest(std::move(record),rootDebug,rootSources,rootBundles,std::move(owners),std::move(runtimeOwner));
      }
      return json(JSON(std::move(record)))+"\n";};
    auto debugText=debugTextFor();
    auto compilation=Object(stage.compilation);compilation["build_key"]=key;compilation["image_inputs"]=Object(seed);compilation["owned_images"]=Array(imageInventory);
    compilation["stage_binary_inputs"]=JSON(*stage.compilation.get("static_libraries"));compilation["static_libraries"]=Array(staticInventory);
    compilation["shared_runtime_key"]=runtimeKey;
    Object contracts;for(const auto &[name,digest]:built.functionContracts)contracts[name]=digest;
    Object abiRecord{{"schema","nex.native-library-abi/1"},{"abi",abi},{"compiler_build",NEX_BUILD_ID},{"target",built.target},{"code_only",shared},{"function_contracts",std::move(contracts)},{"static_libraries",Array(staticInventory)}};
    Object linkRecord{{"schema",sharedTasks?"nex.native-image-inputs/2":"nex.native-image-inputs/1"},{"inputs",Object(seed)},{"images",Array(imageInventory)}};if(sharedTasks)linkRecord["task_providers"]=Array(providerInventory);if(taskProfiling){linkRecord["schema"]="nex.native-image-inputs/3";linkRecord["task_profile_catalogs"]=Array(profileInventory);}
    if(taskDebugging){linkRecord["schema"]="nex.native-image-inputs/4";linkRecord["task_debug_catalogs"]=Array(debugCatalogInventory);linkRecord["task_debug_sources"]=Array(debugSourceInventory);}
    auto meta=Object(stage.build);meta["key"]=key;meta["kind"]=server?"http_server":input.kind;meta["deferred_link"]=false;meta["compilation"]=built.compilation;meta["notices"]=built.notices;meta["completion_schema"]=sharedTasks?"nex.native-completion/5":"nex.native-completion/3";meta["completion_inputs"]=Array(completion);
    meta["stage_runtime_requirements"]=JSON(*stage.build.get("runtime_requirements"));meta["runtime_requirements"]=Object(requirements);
    meta["static_link_inputs"]=nativeStaticLinkInputs(tools,storage,foreign,server);
    meta["runtime_source_projection"]=projection.string();meta["runtime_inputs"]=JSON(*runtimeSeed.get("inputs"));meta["runtime_components"]=JSON(*runtimeSeed.get("components"));meta["shared_runtime_key"]=runtimeKey;
    if(taskProfiling){meta["completion_schema"]="nex.native-completion/6";meta["completion_mode"]=shared?"shared-image":"shared-application";meta["task_profile_catalog"]=nativeTaskProfileInfo(rootCatalog).catalogHash;}
    if(taskDebugging){meta["completion_schema"]="nex.native-completion/7";meta["completion_mode"]=shared?"shared-image":"shared-application";meta["task_debug_metadata_hash"]=nativeTaskDebugMetadataHash(rootDebug,rootSources);meta["task_debug_abi"]=2;meta["task_debug_catalog"]=nativeTaskDebugInfo(rootDebug,rootSources).catalogHash;meta["task_debug_sources"]=nativeTaskDebugInfo(rootDebug,rootSources).sourceUnionHash;}
    const auto profileCatalogText=taskProfiling?json(nativeTaskProfileCatalogJSON(localCatalog))+"\n":std::string{};
    const auto debugCatalogText=taskDebugging?json(nativeTaskDebugCatalogJSON(localDebug))+"\n":std::string{};
    const auto debugSourcesText=taskDebugging?json(nativeTaskDebugSourceUnionJSON(localSources))+"\n":std::string{};
    std::string taskProviderText;
    auto updateTask=[&]{if(!sharedTasks||!fs::is_regular_file(executable))return;
      built.taskProvider.image=NativeTaskImageIdentity{key,digest(executable),sha(executable),uuid(executable),runtimeKey,digest(runtime)};
      taskProviderText=json(nativeTaskProviderJSON(built.taskProvider))+"\n";built.taskProviderDigest=hash(taskProviderText);
      abiRecord["task_provider"]=nativeTaskProviderJSON(built.taskProvider);abiRecord["task_provider_hash"]=built.taskProviderDigest;
      meta["task_provider"]=nativeTaskProviderJSON(built.taskProvider);meta["task_provider_hash"]=built.taskProviderDigest;meta["task_provider_record"]="task-provider.json";
    };updateTask();
    (void)nativeCompletionInputs(meta);
    auto completionText=[&](){std::string contents=key;for(const auto &path:{executable,folder/"program.mlir",folder/"program.ll",folder/"compilation.json",folder/"build.json",folder/"source-bundle.json"})contents+=digest(path);for(const auto &path:nativeCompletionInputs(meta))contents+=digest(folder/path);return hash(contents)+"\n";};
    auto intact=[&](){try{
      if(taskProfiling&&readFile((folder/"task-profile-catalog.json").string())!=profileCatalogText)return false;
      if(taskDebugging&&(readFile((folder/"task-debug-catalog.json").string())!=debugCatalogText||readFile((folder/"task-debug-sources.json").string())!=debugSourcesText))return false;
      if(sharedTasks&&(taskProviderText.empty()||readFile(built.taskProviderFile)!=taskProviderText))return false;
      if(readFile((folder/"debug.json").string())!=debugText||readFile((folder/"build.json").string())!=json(JSON(Object(meta)))||readFile((folder/"image-inputs.json").string())!=json(JSON(Object(linkRecord)))||readFile((folder/"library-abi.json").string())!=json(JSON(Object(abiRecord))))return false;
      if(darwin&&readFile((folder/"debug-symbols.complete").string())!=digest(fs::path(executable.string()+".dSYM")/"Contents/Resources/DWARF"/executable.filename())+"\n")return false;
      return readFile((folder/"complete").string())==completionText();
    }catch(const std::exception &){return false;}};
    if(!intact()){
      auto compileFlags=flags(tools,projection,profile,foreign,false);
      if(taskDebug)compileFlags.push_back("-DNEX_TASK_DEBUG_ENABLED");
      if(taskProfiling)compileFlags.push_back("-DNEX_TASK_PROFILE_ENABLED");
      if(server){
        // The common runtime supports the union of all images. This server
        // entry only configures foreign authority when its own closure needs it.
        auto args=flags(tools,projection,profile,stage.build.getObject("runtime_requirements")->getBoolean("foreign").value_or(false),false);
        args.insert(args.end(),{"-I",tools.opensslInclude,"-pthread"});auto object=folder/"http_main.o";compile(tools,projection/"http_main.cpp",object,args);linkInputs.push_back(object.string());
        auto bridge=folder/"server-bridge.cpp";auto symbol=nativeSymbol(input.program->function(input.options.entry).name);
        writeFile(bridge.string(),"#include \"nex_host.h\"\nextern \"C\" nexrt::Handle *"+symbol+"(nexrt::Handle*);extern \"C\" nexrt::Handle *nex_server_dispatch(nexrt::Handle *p){return "+symbol+"(p);}\n");compile(tools,bridge,folder/"server-bridge.o",compileFlags);linkInputs.push_back((folder/"server-bridge.o").string());linkInputs.insert(linkInputs.end(),{tools.opensslSSL,tools.opensslCrypto,"-pthread"});
      }
      if(!shared){
        if(!server){
          if(!input.options.functionsOnly)fail("final application image requires function-only staging");
          const auto &entry=input.program->function(input.options.entry);auto sites=operationTree(*input.program,entry);auto site=std::find_if(sites.begin(),sites.end(),[](const auto &s){return s.path=="body";});if(site==sites.end())fail("missing application entry site");
          auto functionHash=hash(json(canonical(entry),false)),sourceHash=hash(input.program->definition(entry));
          std::string source="#include \"nex_host.h\"\nextern \"C\" "+std::string(entry.result==Type::Unit?"void":"int64_t")+" "+nativeSymbol(entry.name)+"();\n";
          source+="static const nexrt::NativeFunctionSite function={"+json(functionHash,false)+","+json(sourceHash,false)+","+json(std::string(NEX_BUILD_ID),false)+"};\n";
          source+="static const nexrt::NativeSite site={&function,"+json(site->site,false)+","+json(site->kind,false)+","+std::to_string(int64_t(site->span.begin)-int64_t(entry.span.begin))+","+std::to_string(int64_t(site->span.end)-int64_t(entry.span.begin))+"};\n";
          source+="extern \"C\" int64_t nex_application_run_at(void*,int64_t,const char*const*,const nexrt::NativeSite*);\n";
          if(stage.build.getObject("runtime_requirements")->getBoolean("foreign").value_or(false))source+="extern \"C\" void nex_foreign_configure_at(int64_t,const char*const*,const nexrt::NativeSite*);\n";
          source+="static int64_t entry(int64_t argc,const char *const *argv){";
          if(stage.build.getObject("runtime_requirements")->getBoolean("foreign").value_or(false))source+="nex_foreign_configure_at(argc,argv,&site);";
          if(sharedTasks){const auto &root=input.stage.taskApplication;
            if(!root.enabled||root.entry!=entry.name||root.descriptorAccessor!=nativeSymbol(entry.name)+"__task_code_address")fail("task root accessor differs from checked application entry");
            source="#include \"nex_task_application.h\"\n#include \"nex_host.h\"\nextern \"C\" const nexrt::TaskCodeDescriptor *"+root.descriptorAccessor+"();\n"+source.substr(source.find("static const nexrt::NativeFunctionSite"));
            if(taskProfiling){source="#include \"nex_task_profile_site.h\"\n"+source;
              for(const auto &registry:rootCatalog.registries)source="extern \"C\" const nexrt::TaskProfileCodeRegistry *"+registry.accessor+"();\n"+source;
              // Declarations must follow the POD header, before the thunk body.
              auto header=source.find("#include \"nex_task_profile_site.h\"");auto prefix=source.substr(0,header);source=source.substr(header);auto body=source.find("static const nexrt::NativeFunctionSite");source.insert(body,prefix);
              source+="const nexrt::TaskProfileCodeRegistry *registries[]={";for(size_t i=0;i<rootCatalog.registries.size();++i){if(i)source+=",";source+=rootCatalog.registries[i].accessor+"()";}source+="};nex_task_profile_prepare_registries(registries,"+std::to_string(rootCatalog.registries.size())+");";
            }
            if(taskDebugging){source="#include \"nex_task_debug_site.h\"\n"+source;std::string declarations;for(const auto &registry:rootDebug.registries)declarations+="extern \"C\" const nexrt::TaskDebugCodeRegistry *"+registry.accessor+"();\n";source.insert(source.find("static const nexrt::NativeFunctionSite"),declarations);
              source+="const nexrt::TaskDebugCodeRegistry *debugRegistries[]={";for(size_t i=0;i<rootDebug.registries.size();++i){if(i)source+=",";source+=rootDebug.registries[i].accessor+"()";}source+="};nex_task_debug_prepare_registries(debugRegistries,"+std::to_string(rootDebug.registries.size())+");";
            }
            source+="return nex_task_application_execute_limits_at("+root.descriptorAccessor+"(),argc,argv,"+std::to_string(root.configured.steps)+","+std::to_string(root.configured.timeoutMs)+","+std::to_string(root.configured.workers)+",&site); }\n";
          }else source+=(entry.result==Type::Unit?nativeSymbol(entry.name)+"();return 0;":"return "+nativeSymbol(entry.name)+"();")+"}\n";
          source+="int main(int argc,char **argv){return int(nex_application_run_at(reinterpret_cast<void*>(entry),argc,argv,&site));}\n";
          auto path=folder/"application-entry.cpp";writeFile(path.string(),source);compile(tools,path,folder/"application-entry.o",compileFlags);linkInputs.push_back((folder/"application-entry.o").string());
        }
        Object applicationIdentity{{"schema","nex.native-application/1"},{"toolchain",NEX_VERSION},{"language",programLanguage(*input.program)},{"revision",revision(*input.program)},{"source_hash",hash(json(sourceBundle(*input.program),false))},{"build_key",key},{"compiler_build",NEX_BUILD_ID}};
        if(sharedTasks){auto selection=nativeTaskApplicationStageJSON(input.stage.taskApplication);applicationIdentity["task_limits"]=JSON(*selection.getAsObject()->get("configured"));applicationIdentity["task_file_reads"]=input.stage.taskApplication.fileReads;applicationIdentity["task_file_writes"]=input.stage.taskApplication.fileWrites;applicationIdentity["task_execution_abi"]=input.stage.taskApplication.executionABI;if(input.stage.taskApplication.executionABI==nexrt::taskCodeStreamABI)applicationIdentity["task_file_streams"]=input.stage.taskApplication.fileStreams;}
        auto identity=json(JSON(std::move(applicationIdentity)),false);
        const auto identityExport=windows?"__declspec(dllexport) ":"";
        auto path=folder/"application-identity.cpp";writeFile(path.string(),"extern \"C\" "+std::string(identityExport)+"const char *nex_application_identity()noexcept{return "+json(identity,false)+";}\n");compile(tools,path,folder/"application-identity.o",compileFlags);linkInputs.push_back((folder/"application-identity.o").string());
        if(profiling){Object profileBuild{{"schema",taskProfiling?"nex.profile-build/2":"nex.profile-build/1"},{"toolchain",NEX_VERSION},{"language",programLanguage(*input.program)},{"revision",revision(*input.program)},{"build_key",key},{"entry",input.program->function(input.options.entry).name},
          {"compiler_build",NEX_BUILD_ID},{"source_hash",hash(json(sourceBundle(*input.program),false))},{"task_limits",stage.build.get("task_limits")?JSON(*stage.build.get("task_limits")):JSON(nullptr)}};if(taskProfiling)profileBuild["task_profile_catalog"]=nativeTaskProfileInfo(rootCatalog).catalogHash;auto profileIdentity=json(JSON(std::move(profileBuild)),false);auto path=folder/"profile-identity.cpp";writeFile(path.string(),"extern \"C\" "+std::string(identityExport)+"const char *nex_profile_build_info(){return "+json(profileIdentity,false)+";}\n");compile(tools,path,folder/"profile-identity.o",compileFlags);linkInputs.push_back((folder/"profile-identity.o").string());}
      }
      link(tools,projection,executable,std::move(linkInputs),darwin,shared,storage,foreign,server);
      verifyToolchain();
      debugText=debugTextFor();updateTask();
      if(sharedTasks)writeFile(built.taskProviderFile,taskProviderText);
      if(taskProfiling)writeFile((folder/"task-profile-catalog.json").string(),profileCatalogText);
      if(taskDebugging){writeFile((folder/"task-debug-catalog.json").string(),debugCatalogText);writeFile((folder/"task-debug-sources.json").string(),debugSourcesText);}
      if(darwin)writeFile((folder/"debug-symbols.complete").string(),digest(fs::path(executable.string()+".dSYM")/"Contents/Resources/DWARF"/executable.filename())+"\n");
      writeFile((folder/"debug.json").string(),debugText);writeFile((folder/"compilation.json").string(),json(JSON(Object(compilation)))+"\n");writeFile((folder/"library-abi.json").string(),json(JSON(Object(abiRecord))));writeFile((folder/"image-inputs.json").string(),json(JSON(Object(linkRecord))));writeFile((folder/"build.json").string(),json(JSON(Object(meta))));writeFile(built.notices,noticeText);writeFile((folder/"complete").string(),completionText());
    }else built.cached=true;
    result.images.emplace(input.name,std::move(built));
  }
  verifyToolchain();
  return result;
}
}
