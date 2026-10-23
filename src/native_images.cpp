#include "nex/native_images.h"
#include "nex/native_toolchain.h"
#include "nex/operations.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/Object/BuildID.h"
#include "llvm/Object/MachO.h"
#include "llvm/Object/ObjectFile.h"
#include "llvm/Support/Error.h"
#include "llvm/Support/SHA256.h"
#include "llvm/TargetParser/Triple.h"
#include <algorithm>
#include <filesystem>
#include <set>

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
void copyCaptured(const fs::path &from,const fs::path &to){fs::create_directories(to.parent_path());copyFile(from.string(),to.string(),true);}
struct Captured {
  const NativeImageInput *input;
  Object build,debug,compilation;
  std::string objects;
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
  return {&input,std::move(meta),read(folder/"debug.json"),read(folder/"compilation.json"),std::move(objects)};
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
void link(const NativeToolchain &tools,const fs::path &destination,std::vector<std::string> inputs,bool darwin,bool shared,bool storage,bool foreign,bool server){
  Temporary temp;auto output=temp.path/destination.filename();auto args=tools.driver;
  if(!tools.linker.empty())args.push_back("--ld-path="+tools.linker);
  if(shared){
    if(darwin)args.push_back("-dynamiclib");else args.insert(args.end(),{"-shared","-Xlinker","-z","-Xlinker","defs"});
    args.insert(args.end(),{"-Xlinker",darwin?"-install_name":"-soname","-Xlinker",(darwin?"@rpath/":"")+destination.filename().string()});
  }else args.insert(args.end(),{"-Xlinker",darwin?"-export_dynamic":"--export-dynamic"});
  if(!darwin)args.insert(args.end(),{"-Xlinker","--build-id=sha1"});
  args.insert(args.end(),inputs.begin(),inputs.end());rpaths(args,darwin,tools,storage,foreign,server);args.insert(args.end(),{"-o",output.string(),"-g"});run(std::move(args));copyCaptured(output,destination);packageSymbols(destination,tools,darwin);
}
void provided(const Captured &stage,std::map<std::string,std::string> &contracts){
  for(const auto &unit:*stage.compilation.getArray("units")){
    auto name=text(*unit.getAsObject(),"identity");auto contract=stage.input->stage.functionContracts.at(name);
    auto [old,inserted]=contracts.emplace(name,contract);if(!inserted&&old->second!=contract)fail("conflicting emitted function contract: "+name);
  }
}
}


NativeImageResults buildNativeImages(const std::string &directory,const std::vector<NativeImageInput> &inputs){
  if(inputs.empty())fail("shared image linking needs checked stages");
  auto root=fs::absolute(directory);auto tools=configureNative(inputs.front().options);llvm::Triple triple(tools.target);
  bool darwin=triple.isMacOSX();if(!darwin&&!triple.isOSLinux())fail("shared native images currently require macOS or Linux");
  std::map<std::string,Captured> stages;std::map<std::string,std::string> sources;std::set<std::string> components,notices;
  bool storage=false,foreign=false,profiling=false,wire=false,files=false,parallel=false,taskDebug=false;auto abi=inputs.front().stage.libraryABI;auto profile=inputs.front().options.profile;
  std::string foreignDefault;
  auto toolchainFingerprint=inspectNativeToolchain(inputs.front().options).hash;
  auto verifyToolchain=[&](){if(inspectNativeToolchain(inputs.front().options).hash!=toolchainFingerprint)fail("native image toolchain changed while linking");};
  for(const auto &input:inputs){
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
    if(stageTaskDebug&&(input.kind!="executable"||!input.dynamicDependencies.empty()||!input.staticDependencies.empty()))fail("task debug binary providers remain pending");
    taskDebug|=stageTaskDebug;
    storage|=requirements->getBoolean("storage").value_or(false);foreign|=requirements->getBoolean("foreign").value_or(false);profiling|=requirements->getBoolean("profiling").value_or(false);
    wire|=requirements->getBoolean("wire").value_or(false);files|=requirements->getBoolean("files").value_or(false);
    parallel|=requirements->getBoolean("parallel").value_or(false);
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
  Object requirements{{"wire",wire},{"storage",storage},{"files",files},{"foreign",foreign},{"profiling",profiling},{"parallel",parallel},{"task_debug",taskDebug}};
  Object runtimeSeed{{"schema","nex.native-runtime-input/1"},{"compiler_build",NEX_BUILD_ID},{"abi",abi},{"toolchain",tools.identity},{"toolchain_fingerprint",toolchainFingerprint},{"profile",profile},
    {"cache",root.string()},{"cwd",fs::current_path().string()},{"inputs",std::move(runtimeInputs)},{"components",std::move(componentNames)},
    {"shared_profile_identity",profiling},{"task_debug",taskDebug},{"foreign",foreign},{"storage",storage},{"parallel",parallel},{"foreign_catalogue",foreignDefault}};
  auto runtimeText=json(JSON(Object(runtimeSeed)),false),runtimeKey=hash(runtimeText);auto runtimeFolder=root/("runtime-"+runtimeKey);
  auto extension=darwin?".dylib":".so";auto runtime=runtimeFolder/("libnex_runtime_"+runtimeKey+extension);auto projection=runtimeFolder/"runtime-inputs";
  for(const auto &[name,data]:sources)writeFile((projection/name).string(),data);
  std::string noticeText;for(const auto &notice:notices)noticeText+=notice+'\n';
  auto runtimeIntact=[&](){try{
    auto record=read(runtimeFolder/"image.json");if(text(record,"key")!=runtimeKey||text(record,"hash")!=digest(runtime)||text(record,"sha256")!=sha(runtime)||text(record,"uuid")!=uuid(runtime)||readFile((runtimeFolder/"inputs.json").string())!=runtimeText)return false;
    auto symbols=record.getArray("symbols");if(!symbols)return false;for(const auto &s:*symbols)if(text(*s.getAsObject(),"hash")!=digest(text(*s.getAsObject(),"path")))return false;
    return readFile((runtimeFolder/"complete").string())==hash(runtimeKey+digest(runtime)+digest(runtimeFolder/"image.json")+hash(runtimeText))+"\n";
  }catch(const std::exception &){return false;}};
  if(!runtimeIntact()){
    std::vector<std::string> objects;auto runtimeFlags=flags(tools,projection,profile,foreign,true);
    if(parallel)runtimeFlags.insert(runtimeFlags.end(),{"-pthread","-DNEX_STRUCTURED_WORKERS"});
    if(taskDebug)runtimeFlags.insert(runtimeFlags.end(),{"-DNEX_TASK_DEBUG_ENABLED","-DNEX_ASYNC_TASKS","-DNEX_STRUCTURED_WORKERS","-pthread"});
    if(!foreignDefault.empty())runtimeFlags.push_back("-DNEX_FOREIGN_DEFAULT="+json(foreignDefault,false));
    for(const auto &component:components){auto object=runtimeFolder/("runtime-"+std::to_string(objects.size())+".o");compile(tools,projection/component,object,runtimeFlags);objects.push_back(object.string());}
    if(storage)objects.push_back(tools.sqliteLibrary);
    if(foreign){objects.insert(objects.end(),{tools.opensslCrypto,"-pthread"});if(!darwin)objects.push_back("-ldl");}
    if(profiling){objects.push_back("-pthread");if(!darwin)objects.push_back("-ldl");}
    if(parallel)objects.push_back("-pthread");
    link(tools,runtime,std::move(objects),darwin,true,storage,foreign,false);
    verifyToolchain();auto record=imageRecord(runtime,runtimeKey,abi,"runtime");record["symbols"]=symbolFiles(runtime);record["inputs"]=Object(runtimeSeed);record["requirements"]=Object(requirements);
    writeFile((runtimeFolder/"inputs.json").string(),runtimeText);writeFile((runtimeFolder/"image.json").string(),json(JSON(Object(record))));
    writeFile((runtimeFolder/"complete").string(),hash(runtimeKey+digest(runtime)+digest(runtimeFolder/"image.json")+hash(runtimeText))+"\n");
  }
  NativeImageResults result;result.runtime=read(runtimeFolder/"image.json");
  for(const auto &input:inputs){
    if(input.kind=="static_library")continue;
    const auto &stage=stages.at(input.name);bool shared=input.kind=="shared_library",server=input.kind=="server";
    Array statics,dynamics;
    for(const auto &name:input.staticDependencies){const auto &s=stages.at(name);statics.push_back(Object{{"component",name},{"hash",hash(s.objects)},{"abi",s.input->stage.libraryABI}});}
    for(const auto &name:input.dynamicDependencies){auto found=result.images.find(name);if(found==result.images.end())fail("dynamic image order is not dependency-first: "+name);dynamics.push_back(Object{{"component",name},{"hash",digest(found->second.executable)},{"key",found->second.key}});}
    Object seed{{"schema","nex.native-image-input/1"},{"compiler_build",NEX_BUILD_ID},{"component",input.name},{"kind",input.kind},{"stage",input.stage.key},{"objects",hash(stage.objects)},
      {"runtime_key",runtimeKey},{"runtime_hash",digest(runtime)},{"abi",abi},{"static_libraries",std::move(statics)},{"dynamic_libraries",std::move(dynamics)}};
    auto seedText=json(JSON(Object(seed)),false),key=hash(seedText);auto folder=root/key;
    auto executable=folder/(shared?"libnex_"+input.name+"_"+key+extension:"app");
    BuildResult built=input.stage;built.executable=executable.string();built.key=key;built.mlir=(folder/"program.mlir").string();built.llvm=(folder/"program.ll").string();built.compilation=(folder/"compilation.json").string();built.notices=(folder/"THIRD_PARTY_NOTICES.txt").string();built.cached=false;
    built.parallelCalls=parallel;
    built.functionContracts.clear();provided(stage,built.functionContracts);for(const auto &name:input.staticDependencies)provided(stages.at(name),built.functionContracts);
    fs::create_directories(folder/"images");copyCaptured(input.stage.executable,folder/"objects.a");
    Array completion;completion.push_back(Object{{"kind","abi"},{"path","library-abi.json"}});completion.push_back(Object{{"kind","link_inputs"},{"path","image-inputs.json"}});completion.push_back(Object{{"kind","objects"},{"path","objects.a"}});
    Array staticInventory;std::vector<std::string> linkInputs;archive(linkInputs,folder/"objects.a",darwin);
    for(size_t i=0;i<input.staticDependencies.size();++i){
      const auto &dependency=stages.at(input.staticDependencies[i]);auto relative="libraries/"+std::to_string(i)+".a";
      writeFile((folder/relative).string(),dependency.objects);archive(linkInputs,folder/relative,darwin);completion.push_back(Object{{"kind","static_library"},{"path",relative}});
      Object contracts;for(const auto &[name,digest]:dependency.input->stage.functionContracts)contracts[name]=digest;
      staticInventory.push_back(Object{{"component",input.staticDependencies[i]},{"path",(folder/relative).string()},{"hash",hash(dependency.objects)},{"abi",abi},{"contracts",std::move(contracts)}});
    }
    std::map<std::string,Object> images;images.emplace(runtime.filename().string(),read(runtimeFolder/"image.json"));
    for(const auto &name:input.dynamicDependencies){const auto &dependency=result.images.at(name);images.emplace(fs::path(dependency.executable).filename().string(),imageRecord(dependency.executable,dependency.key,abi,"library"));
      auto meta=read(fs::path(dependency.executable).parent_path()/"image-inputs.json");for(const auto &value:*meta.getArray("images")){const auto &record=*value.getAsObject();images.emplace(fs::path(text(record,"path")).filename().string(),Object(record));}}
    Array imageInventory;
    for(auto &[name,record]:images){
      auto original=fs::path(text(record,"path")),captured=folder/"images"/name;copyCaptured(original,captured);if(digest(captured)!=text(record,"hash"))fail("owned image changed during capture");
      record["path"]=captured.string();record["symbols"]=symbolFiles(original);
      Array capturedSymbols;
      for(const auto &value:*record.getArray("symbols")){const auto &s=*value.getAsObject();auto from=fs::path(text(s,"path"));auto suffix=from.lexically_relative(fs::path(original.string()+".dSYM"));auto to=fs::path(captured.string()+".dSYM")/suffix;copyCaptured(from,to);capturedSymbols.push_back(Object{{"path",to.string()},{"hash",digest(to)}});}
      record["symbols"]=std::move(capturedSymbols);imageInventory.push_back(Object(record));completion.push_back(Object{{"kind","owned_image"},{"path",(fs::path("images")/name).generic_string()}});
    }
    for(const auto &record:imageInventory)for(const auto &symbol:*record.getAsObject()->getArray("symbols"))completion.push_back(Object{{"kind","owned_symbols"},{"path",fs::path(text(*symbol.getAsObject(),"path")).lexically_relative(folder).generic_string()}});
    for(const auto &name:input.dynamicDependencies)linkInputs.push_back((folder/"images"/fs::path(result.images.at(name).executable).filename()).string());
    linkInputs.push_back((folder/"images"/runtime.filename()).string());
    auto stageFolder=fs::path(input.stage.executable).parent_path();copyCaptured(stageFolder/"program.mlir",folder/"program.mlir");copyCaptured(stageFolder/"program.ll",folder/"program.ll");copyCaptured(stageFolder/"source-bundle.json",folder/"source-bundle.json");
    auto debug=Object(stage.debug);debug["program"]=executable.string();debug["build_key"]=key;debug["owned_images"]=Array(imageInventory);
    for(const auto *file:{"lldb_nex.py","nex_dap.py"})copyCaptured(stageFolder/"debugger"/file,folder/"debugger"/file);
    debug["formatter"]=(folder/"debugger/lldb_nex.py").string();debug["dap_adapter"]=(folder/"debugger/nex_dap.py").string();
    auto debugTextFor=[&]{auto record=Object(debug);if(auto task=record.getObject("task_debug")){
      (*task)["image_sha256"]="";(*task)["image_uuid"]="";
      if(fs::is_regular_file(executable))try{(*task)["image_sha256"]=sha(executable);(*task)["image_uuid"]=uuid(executable);}catch(const Error &){}
    }return json(JSON(std::move(record)))+"\n";};
    auto debugText=debugTextFor();
    auto compilation=Object(stage.compilation);compilation["build_key"]=key;compilation["image_inputs"]=Object(seed);compilation["owned_images"]=Array(imageInventory);
    compilation["stage_binary_inputs"]=JSON(*stage.compilation.get("static_libraries"));compilation["static_libraries"]=Array(staticInventory);
    compilation["shared_runtime_key"]=runtimeKey;
    Object contracts;for(const auto &[name,digest]:built.functionContracts)contracts[name]=digest;
    Object abiRecord{{"schema","nex.native-library-abi/1"},{"abi",abi},{"compiler_build",NEX_BUILD_ID},{"target",built.target},{"code_only",shared},{"function_contracts",std::move(contracts)},{"static_libraries",Array(staticInventory)}};
    Object linkRecord{{"schema","nex.native-image-inputs/1"},{"inputs",Object(seed)},{"images",Array(imageInventory)}};
    auto meta=Object(stage.build);meta["key"]=key;meta["kind"]=server?"http_server":input.kind;meta["deferred_link"]=false;meta["compilation"]=built.compilation;meta["notices"]=built.notices;meta["completion_schema"]="nex.native-completion/3";meta["completion_inputs"]=Array(completion);
    meta["stage_runtime_requirements"]=JSON(*stage.build.get("runtime_requirements"));meta["runtime_requirements"]=Object(requirements);
    meta["runtime_source_projection"]=projection.string();meta["runtime_inputs"]=JSON(*runtimeSeed.get("inputs"));meta["runtime_components"]=JSON(*runtimeSeed.get("components"));meta["shared_runtime_key"]=runtimeKey;
    (void)nativeCompletionInputs(meta);
    auto completionText=[&](){std::string contents=key;for(const auto &path:{executable,folder/"program.mlir",folder/"program.ll",folder/"compilation.json",folder/"build.json",folder/"source-bundle.json"})contents+=digest(path);for(const auto &v:completion)contents+=digest(folder/text(*v.getAsObject(),"path"));return hash(contents)+"\n";};
    auto intact=[&](){try{
      if(readFile((folder/"debug.json").string())!=debugText||readFile((folder/"build.json").string())!=json(JSON(Object(meta)))||readFile((folder/"image-inputs.json").string())!=json(JSON(Object(linkRecord)))||readFile((folder/"library-abi.json").string())!=json(JSON(Object(abiRecord))))return false;
      if(darwin&&readFile((folder/"debug-symbols.complete").string())!=digest(fs::path(executable.string()+".dSYM")/"Contents/Resources/DWARF"/executable.filename())+"\n")return false;
      return readFile((folder/"complete").string())==completionText();
    }catch(const std::exception &){return false;}};
    if(!intact()){
      auto compileFlags=flags(tools,projection,profile,foreign,false);
      if(taskDebug)compileFlags.push_back("-DNEX_TASK_DEBUG_ENABLED");
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
          source+=(entry.result==Type::Unit?nativeSymbol(entry.name)+"();return 0;":"return "+nativeSymbol(entry.name)+"();")+"}\n";
          source+="int main(int argc,char **argv){return int(nex_application_run_at(reinterpret_cast<void*>(entry),argc,argv,&site));}\n";
          auto path=folder/"application-entry.cpp";writeFile(path.string(),source);compile(tools,path,folder/"application-entry.o",compileFlags);linkInputs.push_back((folder/"application-entry.o").string());
        }
        auto identity=json(Object{{"schema","nex.native-application/1"},{"toolchain",NEX_VERSION},{"language",programLanguage(*input.program)},{"revision",revision(*input.program)},{"source_hash",hash(json(sourceBundle(*input.program),false))},{"build_key",key},{"compiler_build",NEX_BUILD_ID}},false);
        auto path=folder/"application-identity.cpp";writeFile(path.string(),"extern \"C\" const char *nex_application_identity()noexcept{return "+json(identity,false)+";}\n");compile(tools,path,folder/"application-identity.o",compileFlags);linkInputs.push_back((folder/"application-identity.o").string());
        if(profiling){auto profileIdentity=json(Object{{"schema","nex.profile-build/1"},{"toolchain",NEX_VERSION},{"language",programLanguage(*input.program)},{"revision",revision(*input.program)},{"build_key",key},{"entry",input.program->function(input.options.entry).name},
          {"compiler_build",NEX_BUILD_ID},{"source_hash",hash(json(sourceBundle(*input.program),false))},{"task_limits",stage.build.get("task_limits")?JSON(*stage.build.get("task_limits")):JSON(nullptr)}},false);auto path=folder/"profile-identity.cpp";writeFile(path.string(),"extern \"C\" const char *nex_profile_build_info(){return "+json(profileIdentity,false)+";}\n");compile(tools,path,folder/"profile-identity.o",compileFlags);linkInputs.push_back((folder/"profile-identity.o").string());}
      }
      link(tools,executable,std::move(linkInputs),darwin,shared,storage,foreign,server);
      verifyToolchain();
      debugText=debugTextFor();
      if(darwin)writeFile((folder/"debug-symbols.complete").string(),digest(fs::path(executable.string()+".dSYM")/"Contents/Resources/DWARF"/executable.filename())+"\n");
      writeFile((folder/"debug.json").string(),debugText);writeFile((folder/"compilation.json").string(),json(JSON(Object(compilation)))+"\n");writeFile((folder/"library-abi.json").string(),json(JSON(Object(abiRecord))));writeFile((folder/"image-inputs.json").string(),json(JSON(Object(linkRecord))));writeFile((folder/"build.json").string(),json(JSON(Object(meta))));writeFile(built.notices,noticeText);writeFile((folder/"complete").string(),completionText());
    }else built.cached=true;
    result.images.emplace(input.name,std::move(built));
  }
  verifyToolchain();
  return result;
}
}
