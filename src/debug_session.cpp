#include "nex/debug_session.h"
#include "nex/native_toolchain.h"
#include "nex/task_limits.h"
#include "llvm/Support/Program.h"
#include "llvm/Support/Error.h"
#include "nex_json.h"
#include <filesystem>
#include <array>
#include <cerrno>
#include <cstdlib>
#include <fcntl.h>
#include <sys/stat.h>
#include <unistd.h>
namespace nex {
namespace fs=std::filesystem;
namespace {
llvm::json::Value parseJSON(const std::string &text){auto v=llvm::json::parse(text);if(!v)throw Error("E_JSON",llvm::toString(v.takeError()));return std::move(*v);}
std::string readBoundedText(const std::string &path,size_t limit,const std::string &label,const std::string &code){
  struct File{int fd;~File(){if(fd>=0)::close(fd);}} file{::open(path.c_str(),O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC)};
  struct stat info{};
  if(file.fd<0||::fstat(file.fd,&info)||!S_ISREG(info.st_mode)||info.st_size<0||uint64_t(info.st_size)>limit)throw Error(code,label+" requires a regular non-symlink file of at most "+std::to_string(limit)+" bytes");
  std::string text;std::array<char,65536> buffer{};
  for(;;){auto count=::read(file.fd,buffer.data(),buffer.size());if(count<0){if(errno==EINTR)continue;throw Error("E_FILE","cannot read "+label);}if(!count)break;if(size_t(count)>limit-text.size())throw Error(code,label+" exceeds "+std::to_string(limit)+" bytes");text.append(buffer.data(),size_t(count));}
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
        fs::path cached(path->str());struct stat info{};
        if(cached.parent_path()==base&&cached.filename().string().starts_with("nex-debug-")&&
           ::lstat(cached.c_str(),&info)==0&&S_ISDIR(info.st_mode)&&info.st_uid==::getuid()&&
           (info.st_mode&0777)==0700&&fs::canonical(cached)==cached&&
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
    auto view=debug->getObject("task_debug");auto limits=build->get("task_limits");
    if(kind=="dap")throw Error("E_TASK_DEBUG","logical source task debugging requires lldb or nex-dap; raw DAP is pending");
    if(std::string(programLanguage(p))!="0.20"||build->getString("kind")!="executable"||build->getString("profile")!="debug"||build->getBoolean("task_debug")!=true||
       debug->getString("schema")!="nex.debug/2"||debug->getString("language")!=programLanguage(p)||debug->getString("revision")!=revision(p)||debug->getString("build_key")!=built.key||
       debug->getString("program")!=built.executable||debug->getString("compiler_build")!=NEX_BUILD_ID||debug->getString("source_hash")!=hash(json(sourceBundle(p),false))||
       !view||view->getString("schema")!="nex.task-debug-view/1"||view->getInteger("abi")!=1||view->getString("metadata_hash")!=build->getString("task_debug_metadata_hash")||
       !view->getString("image_sha256")||view->getString("image_sha256")->size()!=64||!view->getString("image_uuid")||view->getString("image_uuid")->empty()||!limits)
      throw Error("E_TASK_DEBUG","task debug launch requires its matching020 native debug executable and catalog ABI1");
    auto configured=parseTaskLimitsJSON(*limits,"E_DEBUG");
    if(json(llvm::json::Value(taskLimitsJSON(configured)),false)!=json(*limits,false))throw Error("E_DEBUG","task debug limits are not canonical");
    auto argv=arguments;argv.insert(argv.begin(),built.executable);auto effective=taskEffectiveLimits(configured,argv);
    taskControl=llvm::json::Object{{"schema","nex.task-debug-session/1"},{"catalog_abi",1},{"deadline_advances_while_stopped",true},
      {"task_execution",taskExecutionJSON(configured,effective,"native")}};
  }
  llvm::json::Array commands{
    "command script import "+json((folder/"debugger/lldb_nex.py").string(),false),
    "nex-load-debug "+json(manifest.string(),false)+" --compiler "+json(compiler,false)};
  if(!arguments.empty()){
    std::string command="settings set -- target.run-args";
    for(const auto &argument:arguments)command+=" "+json(argument,false);
    commands.push_back(std::move(command));
  }
  auto backend=std::getenv("NEX_LLDB_DAP");std::string dap=backend?backend:"lldb-dap";
  auto found=llvm::sys::findProgramByName(dap);bool available=bool(found);if(found)dap=*found;
#ifdef __APPLE__
  if(!available&&!backend){auto result=capture({"xcrun","--find","lldb-dap"});if(result.code==0){dap=llvm::StringRef(result.output).trim().str();available=!dap.empty();}}
#endif
  llvm::json::Array adapterCommand{std::getenv("NEX_PYTHON")?std::getenv("NEX_PYTHON"):"python3",(folder/"debugger/nex_dap.py").string(),"--backend",dap};
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
}
