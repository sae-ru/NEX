#include "nex/debug_session.h"
#include "nex/native_toolchain.h"
#include "nex/task_limits.h"
#include "nex/task_frontend.h"
#include "nex/task_provider_debug.h"
#include "llvm/Support/Program.h"
#include "llvm/Support/Error.h"
#include "nex/native_images.h"
#include "llvm/Support/SHA256.h"
#include "llvm/ADT/StringExtras.h"
#include "nex_json.h"
#include <filesystem>
#include <array>
#include <cerrno>
#include <cstdlib>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
#ifdef _WIN32
#include "nex_host_windows.h"
#endif
namespace nex {
namespace fs=std::filesystem;
namespace {
llvm::json::Value parseJSON(const std::string &text){auto v=llvm::json::parse(text);if(!v)throw Error("E_JSON",llvm::toString(v.takeError()));return std::move(*v);}
std::string readBoundedText(const std::string &path,size_t limit,const std::string &label,const std::string &code){
#ifdef _WIN32
  std::string text;
  try{text=nexrt::host_windows::readRegular(nexrt::platform::wide(path),limit);}
  catch(const nexrt::DataError &error){throw Error(code,label+": "+error.message);}
#else
  struct File{int fd;~File(){if(fd>=0)::close(fd);}} file{::open(path.c_str(),O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC)};
  struct stat info{};
  if(file.fd<0||::fstat(file.fd,&info)||!S_ISREG(info.st_mode)||info.st_size<0||uint64_t(info.st_size)>limit)throw Error(code,label+" requires a regular non-symlink file of at most "+std::to_string(limit)+" bytes");
  std::string text;std::array<char,65536> buffer{};
  for(;;){auto count=::read(file.fd,buffer.data(),buffer.size());if(count<0){if(errno==EINTR)continue;throw Error("E_FILE","cannot read "+label);}if(!count)break;if(size_t(count)>limit-text.size())throw Error(code,label+" exceeds "+std::to_string(limit)+" bytes");text.append(buffer.data(),size_t(count));}
#endif
  try{nexrt::unicodeOffsets(text,false);}catch(const nexrt::DataError&){throw Error("E_JSON",label+" must be valid UTF-8");}
  return text;
}
}
void validateNativeDebugArguments(const std::vector<std::string> &arguments){
  if(arguments.size()>128)throw Error("E_OPTION","native debug accepts at most128 runtime arguments");
  size_t bytes=0;for(const auto &argument:arguments){
    if(argument.size()>4096||argument.find('\0')!=std::string::npos||!llvm::json::isUTF8(argument)||argument.size()>65536-bytes)
      throw Error("E_OPTION","native debug runtime arguments require UTF-8 without NUL,4 KiB per argument and64 KiB total");
    bytes+=argument.size();
  }
}
std::vector<std::string> nativeLLDBCommands(const llvm::json::Value &session){
  auto object=session.getAsObject();auto launch=object?object->getObject("launch"):nullptr;
  auto initialized=launch?launch->getArray("initCommands"):nullptr;
  if(!initialized)throw Error("E_DEBUG","native debugger session requires launch initialization commands");
  std::vector<std::string> commands,arguments;
  for(const auto &value:*initialized){auto text=value.getAsString();if(!text)throw Error("E_DEBUG","debugger initialization command must be text");commands.push_back(text->str());}
  if(auto values=launch->get("args")){
    auto array=values->getAsArray();if(!array)throw Error("E_DEBUG","debugger launch args must be an array");
    for(const auto &value:*array){auto text=value.getAsString();if(!text)throw Error("E_DEBUG","debugger launch argument must be text");arguments.push_back(text->str());}
  }
  validateNativeDebugArguments(arguments);
  if(!arguments.empty()){
    std::string command="settings set -- target.run-args";
    for(const auto &argument:arguments)command+=" "+json(argument,false);
    commands.push_back(std::move(command));
  }
  return commands;
}
std::string nativeDebugBuildDirectory(const std::string &directory){
#ifdef __APPLE__
  auto original=fs::weakly_canonical(directory);
  if(original.string().find('\\')!=std::string::npos){
    // Darwin LLDB loses loaded images when the executable path contains '\\'.
    // Keep one owned native build cache for this project in a usable location.
    auto base=fs::canonical(fs::temp_directory_path());
    if(base.string().find_first_of("\\%")!=std::string::npos)base=fs::canonical("/tmp");
    fs::create_directories(original);auto pointer=original/"debug-cache-directory.json";
    if(fs::is_symlink(pointer))throw Error("E_DEBUG_CACHE","debug cache pointer must not be a symlink");
    try{
      auto record=parseJSON(readBoundedText(pointer.string(),8192,"debug cache pointer","E_DEBUG_CACHE"));
      auto path=record.getAsString();
      if(path){
        fs::path cached(path->str());
#ifdef _WIN32
        bool ownedPrivate=nexrt::host_windows::isPrivateDirectory(cached);
#else
        struct stat info{};
        bool ownedPrivate=::lstat(cached.c_str(),&info)==0&&S_ISDIR(info.st_mode)&&info.st_uid==::getuid()&&(info.st_mode&0777)==0700;
#endif
        if(cached.parent_path()==base&&cached.filename().string().starts_with("nex-debug-")&&
           ownedPrivate&&fs::canonical(cached)==cached&&
           readBoundedText((cached/"owner.json").string(),8192,"debug cache owner","E_DEBUG_CACHE")==json(original.string(),false)+"\n")return cached.string();
      }
    }catch(const std::exception&){/* Missing/stale cache pointers are cache misses. */}
    fs::path cached(createTemporaryDirectory("nex-debug",base.string()));
    try{
      fs::permissions(cached,fs::perms::owner_all,fs::perm_options::replace);
      writeFile((cached/"owner.json").string(),json(original.string(),false)+"\n");
      writeFile(pointer.string(),json(cached.string(),false)+"\n");return cached.string();
    }catch(...){std::error_code ignored;fs::remove_all(cached,ignored);throw;}
  }
#endif
  return directory;
}
llvm::json::Value nativeDebugSession(const Program &p,const BuildResult &built,
  const std::string &directory,const std::string &compiler,const std::string &kind,
  const std::vector<std::string> &arguments){
  if(kind!="lldb"&&kind!="dap"&&kind!="nex-dap")throw Error("E_OPTION","debug adapter must be lldb, dap or nex-dap");
  requireNativeHost(built);
  validateNativeDebugArguments(arguments);
  auto folder=fs::path(built.executable).parent_path(),manifest=folder/"debug.json";
  auto metadata=parseJSON(readFile((folder/"build.json").string()));auto build=metadata.getAsObject();
  if(!build||build->getString("key")!=built.key||build->getString("revision")!=revision(p)||build->getString("compiler_build")!=NEX_BUILD_ID||
     (build->getString("kind")!="executable"&&build->getString("kind")!="http_server"))
    throw Error("E_DEBUG","debug launch requires its matching checked native application or HTTP server artifact");
  auto requirements=build->getObject("runtime_requirements");
  const bool tasks=requirements&&requirements->getBoolean("tasks").value_or(false);
  auto debugManifest=llvm::json::parse(readBoundedText(manifest.string(),8*1048576,"debug manifest","E_DEBUG"));
  if(!debugManifest)throw Error("E_DEBUG","invalid build debug manifest: "+llvm::toString(debugManifest.takeError()));
  if(!debugManifest->getAsObject())throw Error("E_DEBUG","invalid build debug manifest");
  auto debug=debugManifest->getAsObject();llvm::json::Object taskControl;
  if(tasks){
    const bool provider=debug->getString("schema")=="nex.debug/3";
    auto view=debug->getObject("task_debug");auto limits=build->get("task_limits");
    if(kind=="dap")throw Error("E_TASK_DEBUG","logical source task debugging requires lldb or nex-dap; raw DAP is pending");
    if(!supportsTaskFileReads(p)||build->getString("kind")!="executable"||build->getString("profile")!="debug"||build->getBoolean("task_debug")!=true||
       debug->getString("schema")!=(provider?"nex.debug/3":"nex.debug/2")||debug->getString("language")!=programLanguage(p)||debug->getString("revision")!=revision(p)||debug->getString("build_key")!=built.key||
       debug->getString("program")!=built.executable||debug->getString("compiler_build")!=NEX_BUILD_ID||debug->getString("source_hash")!=hash(json(sourceBundle(p),false))||
       !view||view->getString("schema")!=(provider?"nex.task-debug-view/2":"nex.task-debug-view/1")||view->getInteger("abi")!=(provider?2:1)||view->getString("metadata_hash")!=build->getString("task_debug_metadata_hash")||
       !view->getString("image_sha256")||view->getString("image_sha256")->size()!=64||!view->getString("image_uuid")||view->getString("image_uuid")->empty()||!limits)
      throw Error("E_TASK_DEBUG","task debug launch requires its matching020 native debug executable and catalog");
    if(provider){(void)inspectNativeTaskDebugBuildInputs(built);(void)validateNativeTaskDebugManifest(*debug,folder.string());
      for(const auto &[key,name]:std::vector<std::pair<std::string,std::string>>{{"formatter","lldb_nex.py"},{"dap_adapter","nex_dap.py"}}){auto file=folder/"debugger"/name;if((!debug->getString(key)||fs::path(debug->getString(key)->str()).make_preferred()!=fs::path(file).make_preferred())||(debug->getString(key+"_hash")!=hash(readBoundedText(file.string(),8*1048576,"captured debugger script","E_DEBUG"))||debug->getString(key+"_hash")!=hash(readFile(resourceFile("debug/"+name)))))throw Error("E_DEBUG","provider debug scripts differ from their captured build");}
    }
    auto configured=parseTaskLimitsJSON(*limits,"E_DEBUG");
    if(json(llvm::json::Value(taskLimitsJSON(configured)),false)!=json(*limits,false))throw Error("E_DEBUG","task debug limits are not canonical");
    auto argv=arguments;argv.insert(argv.begin(),built.executable);auto effective=taskEffectiveLimits(configured,argv);
    taskControl=llvm::json::Object{{"schema",provider?"nex.task-debug-session/2":"nex.task-debug-session/1"},{"catalog_abi",provider?2:1},{"deadline_advances_while_stopped",true},
      {"task_execution",taskExecutionJSON(configured,effective,"native")}};
    if(provider){taskControl["registry_abi"]=1;taskControl["metadata_hash"]=view->getString("metadata_hash")->str();taskControl["catalog_hash"]=view->getString("catalog_hash")->str();taskControl["source_union_hash"]=view->getString("source_union_hash")->str();}
  }
  llvm::json::Array commands{
    "command script import "+json((folder/"debugger/lldb_nex.py").string(),false),
    "nex-load-debug "+json(manifest.string(),false)+" --compiler "+json(compiler,false)};
  auto backend=std::getenv("NEX_LLDB_DAP");std::string dap=backend?backend:"lldb-dap";
  auto found=llvm::sys::findProgramByName(dap);bool available=bool(found);if(found)dap=*found;
#ifdef __APPLE__
  if(!available&&!backend){auto result=capture({"xcrun","--find","lldb-dap"});if(result.code==0){dap=llvm::StringRef(result.output).trim().str();available=!dap.empty();}}
#endif
  llvm::json::Array adapterCommand{pythonProgram(),"-X","utf8",(folder/"debugger/nex_dap.py").string(),"--backend",dap};
  llvm::json::Object launch{{"type",tasks||kind=="nex-dap"?"nex":"lldb-dap"},{"request","launch"},{"name","NEX"},
    {"program",built.executable},{"cwd",directory},{"stopOnEntry",false},{"initCommands",std::move(commands)}};
  if(tasks)launch["nexTaskDebug"]=true;
  if(auto mappings=debugManifest->getAsObject()->getArray("source_map"))launch["sourceMap"]=llvm::json::Array(*mappings);
  if(!arguments.empty()){llvm::json::Array values;for(const auto &argument:arguments)values.push_back(argument);launch["args"]=std::move(values);}
  auto nexLaunch=launch;nexLaunch["type"]="nex";
  llvm::json::Object session{{"schema","nex.debug-session/1"},{"ok",true},{"revision",revision(p)},{"build_key",built.key},
    {"application_kind",build->getString("kind")->str()},{"host_compatible",built.hostCompatible},
    {"manifest",manifest.string()},{"adapter",tasks||kind=="nex-dap"?"nex-dap":"lldb-dap"},{"launch",std::move(launch)},
    {"nex_adapter",llvm::json::Object{{"schema","nex.dap-adapter/1"},{"available",available},{"command",llvm::json::Array(adapterCommand)},{"launch",std::move(nexLaunch)}}}};
  if(tasks)session["task_debug"]=std::move(taskControl);
  if(tasks||kind=="nex-dap")session["adapter_command"]=std::move(adapterCommand);
  return session;
}
llvm::json::Object relocateNativeTaskDebugSession(const Program &p,const BuildResult &built,
    const std::string &rawDirectory,const std::string &physicalDirectory,
    const std::string &publishedDirectory,const std::string &compiler,
    const std::map<std::string,std::string> &imageOutputs){
  using Object=llvm::json::Object;using Array=llvm::json::Array;using JSON=llvm::json::Value;
  (void)inspectNativeTaskDebugBuildInputs(built);
  auto raw=fs::absolute(rawDirectory).lexically_normal(),physical=fs::absolute(physicalDirectory).lexically_normal(),published=fs::absolute(publishedDirectory).lexically_normal();
  auto relative=raw.lexically_relative(physical);if(relative.is_absolute()||std::any_of(relative.begin(),relative.end(),[](const auto &part){return part=="..";}))throw Error("E_DEBUG","relocated raw namespace escapes its owned output");
  auto finalRaw=(relative=="."?published:published/relative).lexically_normal();
  // lexically_normal() preserves a directory's trailing separator. The
  // published namespace uses one canonical spelling in JSON and Python.
  if(finalRaw!=finalRaw.root_path()&&finalRaw.filename().empty())finalRaw=finalRaw.parent_path();
  auto original=fs::path(built.executable).parent_path();
  auto value=parseJSON(readBoundedText((original/"debug.json").string(),8*1048576,"debug manifest","E_DEBUG"));auto manifest=value.getAsObject();if(!manifest||manifest->getString("schema")!="nex.debug/3")throw Error("E_DEBUG","relocation requires provider debug3");
  auto buildValue=parseJSON(readFile((original/"build.json").string()));auto build=buildValue.getAsObject();std::vector<std::string> names{fs::path(built.executable).filename().string(),"program.mlir","program.ll","compilation.json","build.json","source-bundle.json"};auto completed=nativeCompletionInputs(*build);names.insert(names.end(),completed.begin(),completed.end());names.push_back("complete");
  Array rawPins;for(const auto &name:names){auto target=raw/name;fs::path current;for(const auto &part:target){current/=part;if(fs::is_symlink(current))throw Error("E_DEBUG","symlink relocated raw input");}if(!fs::is_regular_file(target)||fs::file_size(target)>512ULL*1048576)throw Error("E_DEBUG","missing/oversized relocated raw input");auto a=readFile((original/name).string()),b=readFile(target.string());if(a!=b)throw Error("E_DEBUG","relocation changed raw completed input: "+name);rawPins.push_back(Object{{"path",name},{"hash",hash(b)},{"bytes",int64_t(b.size())}});}
  auto view=manifest->getObject("task_debug");auto catalog=parseNativeTaskDebugCatalog(*view->get("catalog"));auto sources=parseNativeTaskDebugSourceUnion(*view->get("source_union"));std::map<std::string,std::string> bundles;for(const auto &source:sources.components)bundles.emplace(source.component,readFile((raw/source.bundleFile).string()));
  auto sha=[](const std::string &bytes){return llvm::toHex(llvm::SHA256::hash(llvm::arrayRefFromStringRef(bytes)),true);};Array mappings;std::set<std::string> mappedImages;
  auto relocate=[&](Object row){auto old=row.getString("path");if(!old||!imageOutputs.contains(old->str()))throw Error("E_DEBUG","relocation omitted a loaded image");auto inputPath=old->str();auto file=fs::absolute(imageOutputs.at(inputPath)).lexically_normal();auto suffix=file.lexically_relative(physical);if(suffix.is_absolute()||std::any_of(suffix.begin(),suffix.end(),[](const auto &part){return part=="..";}))throw Error("E_DEBUG","relocated image escapes output");fs::path current;for(const auto &part:file){current/=part;if(fs::is_symlink(current))throw Error("E_DEBUG","relocated image is a symlink");}auto bytes=readFile(file.string());auto target=(published/suffix).lexically_normal();auto input=Object(row);row["path"]=target.string();row["hash"]=hash(bytes);row["sha256"]=sha(bytes);row["uuid"]=nativeImageUUID(file.string());if(mappedImages.insert(inputPath).second)mappings.push_back(Object{{"input",std::move(input)},{"output",Object(row)}});return row;};
  Array images;for(const auto &image:*view->getArray("images"))images.push_back(relocate(Object(*image.getAsObject())));auto runtime=relocate(Object(*view->getObject("runtime_image")));
  auto base=Object(*manifest);base["artifact_directory"]=finalRaw.string();auto root=std::find_if(images.begin(),images.end(),[](const JSON &v){return v.getAsObject()->getString("kind")=="application";});if(root==images.end())throw Error("E_DEBUG","relocation omitted application");base["program"]=root->getAsObject()->getString("path")->str();base["formatter"]=(finalRaw/"debugger/lldb_nex.py").string();base["dap_adapter"]=(finalRaw/"debugger/nex_dap.py").string();
  if(manifest->get("owned_images"))base["owned_images"]=relocateNativeTaskDebugOwnedImages(*manifest,mappings,raw.string(),finalRaw.string());
  auto fresh=finalizeNativeTaskDebugManifest(std::move(base),catalog,sources,bundles,std::move(images),std::move(runtime));auto freshPath=finalRaw/"debug-relocated.json";
  auto sessionValue=nativeDebugSession(p,built,physical.string(),compiler,"nex-dap",{});auto session=Object(*sessionValue.getAsObject());session["manifest"]=freshPath.string();
  auto launch=Object(*session.getObject("launch"));launch["program"]=fresh.getString("program")->str();launch["cwd"]=published.string();launch["sourceMap"]=Array(*fresh.getArray("source_map"));launch["initCommands"]=Array{"command script import "+json((finalRaw/"debugger/lldb_nex.py").string(),false),"nex-load-debug "+json(freshPath.string(),false)+" --compiler "+json(compiler,false)};session["launch"]=Object(launch);
  auto adapter=Object(*session.getObject("nex_adapter"));auto command=Array(*adapter.getArray("command"));if(command.size()!=6||command[1].getAsString()!="-X"||command[2].getAsString()!="utf8"||command[4].getAsString()!="--backend")throw Error("E_DEBUG","invalid captured Python adapter command");command[3]=(finalRaw/"debugger/nex_dap.py").string();adapter["command"]=Array(command);adapter["launch"]=std::move(launch);session["nex_adapter"]=std::move(adapter);session["adapter_command"]=std::move(command);
  Object receipt{{"schema","nex.task-debug-relocation/1"},{"compiler_build",NEX_BUILD_ID},{"build_key",built.key},{"original_directory",original.string()},{"artifact_directory",finalRaw.string()},{"metadata_rewritten",false},{"raw_files",std::move(rawPins)},{"images",std::move(mappings)}};
  fresh["relocation"]=Object{{"path","debug-relocation.json"},{"hash",hash(json(Object(receipt),false))}};
  writeFile((raw/"debug-relocated.json").string(),json(Object(fresh))+"\n");writeFile((raw/"debug-session.json").string(),json(Object(session))+"\n");writeFile((raw/"debug-relocation.json").string(),json(Object(receipt))+"\n");
  return Object{{"debug_manifest",freshPath.string()},{"debug_session",(finalRaw/"debug-session.json").string()},{"debug_relocation",(finalRaw/"debug-relocation.json").string()}};
}

}
