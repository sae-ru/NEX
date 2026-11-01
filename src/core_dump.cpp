#include "nex/core_dump.h"
#include "nex/backend.h"
#include "nex/native_images.h"
#include "nex/task_process.h"
#include "nex/native_diagnostics.h"
#include "nex/operations.h"
#include "llvm/ADT/StringExtras.h"
#include "llvm/Support/SHA256.h"
#include "llvm/Support/Error.h"
#include <array>
#include <cerrno>
#include <cstdlib>
#include <cstring>
#include <cstdio>
#include <fcntl.h>
#include <filesystem>
#include <sys/stat.h>
#include <unistd.h>
#ifdef _WIN32
#include "nex_host_windows.h"
#endif
#ifdef __linux__
#include <sys/syscall.h>
#include <linux/fs.h>
#endif

namespace nex {
namespace {
#ifdef _WIN32
constexpr const char *applicationFile="app.exe";
#else
constexpr const char *applicationFile="app";
#endif
namespace fs=std::filesystem;
using JSON=llvm::json::Value;using Object=llvm::json::Object;
constexpr uint64_t coreLimit=uint64_t(32)*1024*1024*1024;
struct Input {
  int fd=-1;uint64_t initialSize=0;
#ifdef _WIN32
  std::optional<nexrt::host_windows::Identity> initial;
#else
  struct stat initial{};
#endif
  Input(const fs::path &path,uint64_t limit){
#ifdef _WIN32
    fd=nexrt::host_windows::openRegularDescriptor(path,O_RDONLY);
    auto size=fd<0?-1:nexrt::host_windows::fileSize(fd);
    if(fd>=0)initial=nexrt::host_windows::identity(reinterpret_cast<HANDLE>(::_get_osfhandle(fd)));
    if(size<0||uint64_t(size)>limit||!initial||initial->directory){if(fd>=0)::close(fd);fd=-1;throw Error("E_CORE_INPUT","expected a bounded regular non-reparse Windows file");}
    initialSize=uint64_t(size);
#else
    fd=::open(path.c_str(),O_RDONLY|O_NONBLOCK|O_NOFOLLOW|O_CLOEXEC);
    if(fd<0||::fstat(fd,&initial)||!S_ISREG(initial.st_mode)||initial.st_size<0||uint64_t(initial.st_size)>limit){
      if(fd>=0)::close(fd);fd=-1;throw Error("E_CORE_INPUT","expected a bounded regular non-symlink core/build file: "+path.string());
    }
    initialSize=uint64_t(initial.st_size);
#endif
  }
  ~Input(){if(fd>=0)::close(fd);}
  Input(const Input&)=delete;Input &operator=(const Input&)=delete;
  template<class F>void chunks(F consume){
    if(::lseek(fd,0,SEEK_SET)<0)throw Error("E_CORE_INPUT","cannot seek core/build file");
    std::array<char,65536> buffer{};uint64_t total=0;
    for(;;){auto count=::read(fd,buffer.data(),buffer.size());if(count<0){if(errno==EINTR)continue;throw Error("E_CORE_INPUT","cannot read core/build file");}if(!count)break;
      total+=uint64_t(count);if(total>initialSize)throw Error("E_CORE_CHANGED","core/build file grew during inspection");consume(llvm::StringRef(buffer.data(),size_t(count)));
    }
#ifdef _WIN32
    if(nexrt::host_windows::fileSize(fd)<0||uint64_t(nexrt::host_windows::fileSize(fd))!=initialSize||total!=initialSize)throw Error("E_CORE_CHANGED","core/build file changed during inspection");
#else
    struct stat current{};if(::fstat(fd,&current)||current.st_size!=initial.st_size||total!=initialSize)throw Error("E_CORE_CHANGED","core/build file changed during inspection");
#endif
  }
  std::string text(){std::string value;value.reserve(size_t(initialSize));chunks([&](llvm::StringRef part){value.append(part.data(),part.size());});return value;}
  std::string sha(){llvm::SHA256 h;chunks([&](llvm::StringRef part){h.update(part);});return llvm::toHex(h.final(),true);}
  void samePath(const fs::path &path){
#ifdef _WIN32
    if(nexrt::host_windows::identity(path)!=initial)throw Error("E_CORE_CHANGED","core/build pathname changed during inspection");
#else
    struct stat current{};if(::lstat(path.c_str(),&current)||current.st_dev!=initial.st_dev||current.st_ino!=initial.st_ino||!S_ISREG(current.st_mode))throw Error("E_CORE_CHANGED","core/build pathname changed during inspection");
#endif
  }
};
int64_t readAt(int fd,void *buffer,size_t size,int64_t offset){
#ifdef _WIN32
  return nexrt::host_windows::readAt(fd,buffer,size,offset);
#else
  return ::pread(fd,buffer,size,offset);
#endif
}
std::string text(const fs::path &path,uint64_t limit){return Input(path,limit).text();}
JSON read(const fs::path &path,uint64_t limit){return parseNativeManifest(text(path,limit));}
const Object &object(const JSON &value){auto result=value.getAsObject();if(!result)throw Error("E_CORE_BUILD","expected a debug build object");return *result;}
std::string required(const Object &value,const char *key){auto result=value.getString(key);if(!result||result->empty()||result->size()>16384||result->contains('\0'))throw Error("E_CORE_BUILD",std::string("missing/invalid debug field: ")+key);return result->str();}
struct Temporary{fs::path path;~Temporary(){if(!path.empty()){std::error_code ignored;fs::remove_all(path,ignored);}}};
std::string capsuleStagingDirectory(const fs::path &parent){
  // Publication must stay on the destination filesystem. The general LLVM
  // staging helper redirects percent-bearing paths to /tmp for object writers;
  // capsule files do not use LLVM filename models. POSIX mkdtemp treats the
  // complete parent literally and creates a private adjacent directory.
  auto model=(parent/"nex-core-capsule-XXXXXX").string();
  if(!::mkdtemp(model.data()))throw Error("E_CORE_CAPSULE",std::string("cannot create adjacent core capsule staging directory: ")+std::strerror(errno));
  return model;
}
void validateCoreOptions(const CoreOptions &options){
  if(options.timeout<1||options.timeout>300||options.thread<-1||options.thread>63||options.frame<-1||options.frame>63||options.expression.size()>8192)throw Error("E_CORE_LIMIT","core inspection requires timeout1..300, thread/frame0..63 and expression at most8192 bytes");
}
Object capsuleIdentity(){return Object{{"compiler_build",NEX_BUILD_ID},{"toolchain",NEX_VERSION},{"language",languageVersion}};}
JSON capsuleWork(Object request){
  Temporary temporary{createTemporaryDirectory("nex-core-files")};
  auto file=temporary.path/"request.json";writeFile(file.string(),json(std::move(request)));

  auto child=runTaskProcess({pythonProgram(),"-X","utf8",resourceFile("tools/core_capsule.py"),file.string()},temporary.path.string(),{},900,(temporary.path/"logs").string());
  if(child.timedOut||child.outputLimit||child.interrupted)throw Error("E_CORE_CAPSULE","core capsule helper exceeded its execution/output limit");
  if(child.process.output.empty())throw Error("E_CORE_CAPSULE","core capsule helper returned no report: "+child.process.errors.substr(0,4096));
  auto result=parseNativeManifest(child.process.output);const auto &o=object(result);
  if(child.process.code!=0||!o.getBoolean("ok").value_or(false))throw Error("E_CORE_CAPSULE",o.getString("error").value_or("core capsule helper failed").str());
  return result;
}
void requireCapsuleProgram(const Program &program){
  for(const auto &function:program.functions)if(function.foreign)throw Error("E_CORE_CAPSULE","core capsules with source foreign declarations are not yet supported");
}
}
JSON inspectCore(const CoreOptions &options){
  validateCoreOptions(options);
  auto path=fs::absolute(options.manifest).lexically_normal(),folder=path.parent_path();
  auto manifest=read(path,8*1048576);const auto &m=object(manifest);
  if(m.getString("schema")!="nex.debug/1"||m.getString("compiler_build")!=NEX_BUILD_ID||m.getString("toolchain")!=NEX_VERSION||m.getString("language")!=languageVersion||m.getString("runtime_view")!="nex.runtime-view/3"||m.getString("expression_protocol")!="nex.debug-expression/3")throw Error("E_CORE_BUILD","core inspection requires its matching compiler/debug manifest");
  if(!m.getBoolean("host_compatible").value_or(false))throw Error("E_CORE_BUILD","core inspection currently requires a matching-host build");
  auto bundle=read(folder/"source-bundle.json",16*1048576);auto program=loadBundle(bundle,folder.string());
  if(!options.recordedProgram.empty())requireCapsuleProgram(program);
  if(required(m,"source_hash")!=hash(json(bundle,false))||required(m,"revision")!=revision(program))throw Error("E_CORE_BUILD","core source bundle/revision differs from the debug manifest");
  auto formatter=resourceFile("debug/lldb_nex.py");
  if(required(m,"formatter_hash")!=hash(text(formatter,1048576)))throw Error("E_CORE_BUILD","core inspection requires the matching trusted formatter");
  std::multiset<std::string> expectedSources;for(const auto &[key,unit]:program.units){(void)key;expectedSources.insert(hash(unit.source));}if(program.units.empty())expectedSources.insert(hash(program.source));
  auto sources=m.getArray("sources");if(!sources||sources->size()!=expectedSources.size())throw Error("E_CORE_BUILD","core frozen source list differs");
  for(const auto &entry:*sources){const auto &source=object(entry);auto digest=hash(text(required(source,"projection"),16*1048576));auto found=expectedSources.find(digest);if(found==expectedSources.end()||digest!=required(source,"hash"))throw Error("E_CORE_BUILD","core frozen source projection differs");expectedSources.erase(found);}
  auto image=fs::absolute(required(m,"program")).lexically_normal();
  if(image.parent_path()!=folder||image.filename()!=applicationFile||folder.filename().string()!=required(m,"build_key"))throw Error("E_CORE_BUILD","core inspection requires its content-addressed retained executable build workspace");
  if(!options.recordedProgram.empty()){
    fs::path recorded(options.recordedProgram);
    if(!recorded.is_absolute()||recorded.lexically_normal()!=recorded||recorded.filename()!=applicationFile||recorded.parent_path().filename()!=folder.filename())throw Error("E_CORE_CAPSULE","relocated core requires its original executable build key");
  }
  auto build=read(folder/"build.json",8*1048576);const auto &b=object(build);
  for(const auto *key:{"revision","compiler_build","profile","target"})if(required(b,key)!=required(m,key))throw Error("E_CORE_BUILD",std::string("debug/build identity differs: ")+key);
  if(required(b,"key")!=required(m,"build_key")||b.getString("kind")=="static_library")throw Error("E_CORE_BUILD","core build key/kind differs");
  // The retained completion record binds executable, IR, compilation metadata
  // and source bundle. No compiler or application is run to repair this build.
  std::string completion=required(m,"build_key"),imageHash;uint64_t imageBytes=0;
  for(const auto &file:{image,folder/"program.mlir",folder/"program.ll",folder/"compilation.json",folder/"build.json",folder/"source-bundle.json"}){auto contents=text(file,512*1048576);auto digest=hash(contents);completion+=digest;if(file==image){imageHash=digest;imageBytes=contents.size();}}
  for(const auto &file:nativeCompletionInputs(b))completion+=hash(text(folder/file,512*1048576));
  if(text(folder/"complete",1024)!=hash(completion)+"\n")throw Error("E_CORE_BUILD","retained executable/build completion record differs");
  std::vector<std::pair<fs::path,std::string>> ownedHashes;
  if(b.getString("completion_schema")=="nex.native-completion/3"){
    const auto original=options.originalProgram.empty()?image:fs::path(options.originalProgram);
    if(!original.is_absolute()||original.lexically_normal()!=original||original.filename()!=applicationFile||original.parent_path().filename()!=folder.filename())
      throw Error("E_CORE_BUILD","invalid original shared-image application path");
    auto link=read(folder/"image-inputs.json",8*1048576);auto captured=object(link).getArray("images"),projected=m.getArray("owned_images");
    if(!captured||!projected||captured->size()!=projected->size()||captured->empty()||captured->size()>129)
      throw Error("E_CORE_BUILD","shared-image manifest/input inventory differs");
    std::set<std::string> expectedImages,expectedSymbols,seenImages,seenSymbols;
    for(const auto &entry:*b.getArray("completion_inputs")){
      auto &o=object(entry);if(o.getString("kind")=="owned_image")expectedImages.insert(required(o,"path"));
      if(o.getString("kind")=="owned_symbols")expectedSymbols.insert(required(o,"path"));
    }
    fs::path originalImageBase;bool relocated=!options.recordedProgram.empty();
    for(size_t i=0;i<captured->size();++i){
      const auto &record=object((*captured)[i]);auto current=Object(record);fs::path old(required(record,"path"));
      auto relative=old.extension()==".dll"?old.filename():fs::path("images")/old.filename();auto path=folder/relative;
      auto base=old.extension()==".dll"?old.parent_path():old.parent_path().parent_path();if(originalImageBase.empty())originalImageBase=base;
      std::error_code directoryError;
      if(!old.is_absolute()||old.lexically_normal()!=old||(old.extension()!=".dll"&&old.parent_path().filename()!="images")||base.filename()!=folder.filename()||base!=originalImageBase||
         (!relocated&&!fs::equivalent(base,folder,directoryError))||!expectedImages.contains(relative.generic_string())||!seenImages.insert(relative.generic_string()).second)
        throw Error("E_CORE_BUILD","owned image path/order differs from completion inputs");
      Input input(path,512*1048576);auto bytes=input.text();auto sha=input.sha();
      if(hash(bytes)!=required(record,"hash")||sha!=required(record,"sha256")||nativeImageUUID(path.string())!=required(record,"uuid"))
        throw Error("E_CORE_BUILD","owned native image bytes/UUID differ");
      input.samePath(path);ownedHashes.emplace_back(path,sha);if(relocated)current["path"]=path.string();
      const auto *symbols=record.getArray("symbols");if(!symbols)throw Error("E_CORE_BUILD","missing owned image symbol inventory");
      llvm::json::Array currentSymbols;
      for(const auto &value:*symbols){const auto &symbol=object(value);fs::path oldSymbol(required(symbol,"path"));
        auto relativeSymbol=oldSymbol.lexically_relative(base),insideSymbols=oldSymbol.lexically_relative(fs::path(old.string()+".dSYM"));
        if(!expectedSymbols.contains(relativeSymbol.generic_string())||!seenSymbols.insert(relativeSymbol.generic_string()).second||
           insideSymbols.empty()||insideSymbols.is_absolute()||std::any_of(insideSymbols.begin(),insideSymbols.end(),[](const auto &part){return part=="..";})||
           hash(text(folder/relativeSymbol,512*1048576))!=required(symbol,"hash"))throw Error("E_CORE_BUILD","owned native symbols differ");
        ownedHashes.emplace_back(folder/relativeSymbol,Input(folder/relativeSymbol,512*1048576).sha());
        auto projectedSymbol=Object(symbol);if(relocated)projectedSymbol["path"]=(folder/relativeSymbol).string();currentSymbols.push_back(std::move(projectedSymbol));
      }
      current["symbols"]=std::move(currentSymbols);
      if(json(JSON(std::move(current)),false)!=json((*projected)[i],false))throw Error("E_CORE_BUILD","projected owned image manifest differs");
    }
    if(seenImages!=expectedImages||seenSymbols!=expectedSymbols)throw Error("E_CORE_BUILD","owned image/symbol inventory is incomplete");
  }else if(m.get("owned_images"))throw Error("E_CORE_BUILD","legacy build cannot add an owned-image inventory");
#ifdef __APPLE__
  auto symbols=fs::path(image.string()+".dSYM")/"Contents/Resources/DWARF/app";
  if(text(folder/"debug-symbols.complete",1024)!=hash(text(symbols,512*1048576))+"\n")throw Error("E_CORE_BUILD","retained native symbols differ");
#endif
  auto functions=m.getArray("functions");if(!functions||functions->size()>10000)throw Error("E_CORE_BUILD","invalid core function table");
  std::set<std::string> seen;
  for(const auto &entry:*functions){const auto &f=object(entry);auto name=required(f,"name");if(!seen.insert(name).second)throw Error("E_CORE_BUILD","duplicate core function");const auto &checked=program.function(name);
    if(required(f,"native_symbol")!=nativeSymbol(name)||required(f,"function_hash")!=hash(json(canonical(checked),false))||required(f,"function_source_hash")!=hash(program.definition(checked))||!f.getArray("operation_sites")||json(*f.get("operation_sites"),false)!=json(operationSites(checked,operationTree(program,checked)),false))throw Error("E_CORE_BUILD","core function/operation table differs from checked source");
  }
  auto core=fs::absolute(options.core).lexically_normal();Input input(core,coreLimit);
  std::array<unsigned char,64> header{};auto headerSize=readAt(input.fd,header.data(),header.size(),0);
  auto word=[&](unsigned offset,bool little){uint32_t value=0;for(unsigned i=0;i<4;++i)value|=uint32_t(header[offset+i])<<(8*(little?i:3-i));return value;};
  bool elf=headerSize>=64&&std::memcmp(header.data(),"\x7f" "ELF",4)==0&&header[4]==2&&(header[5]==1||header[5]==2)&&
    (header[5]==1?(header[16]==4&&header[17]==0):(header[16]==0&&header[17]==4));
  bool macho=headerSize>=32&&((word(0,true)==0xfeedfacf&&word(12,true)==4)||(word(0,false)==0xfeedfacf&&word(12,false)==4));
  bool minidump=headerSize>=32&&word(0,true)==0x504d444d&&(word(4,true)&0xffff)==0xa793;
  if(minidump){
    uint64_t count=word(8,true),directory=word(12,true);bool system64=false;
    if(!count||count>4096||directory<32||directory+count*12>input.initialSize)minidump=false;
    else for(uint64_t i=0;i<count;++i){
      std::array<unsigned char,12> entry{};
      if(readAt(input.fd,entry.data(),entry.size(),int64_t(directory+i*12))!=ssize_t(entry.size())){minidump=false;break;}
      auto number=[&](unsigned offset){uint32_t n=0;for(unsigned j=0;j<4;++j)n|=uint32_t(entry[offset+j])<<(8*j);return n;};
      uint64_t size=number(4),offset=number(8);
      if(offset+size>input.initialSize){minidump=false;break;}
      if(number(0)==7){
        std::array<unsigned char,2> arch{};
        if(size<56||readAt(input.fd,arch.data(),arch.size(),int64_t(offset))!=ssize_t(arch.size())){minidump=false;break;}
        auto architecture=uint16_t(arch[0])|(uint16_t(arch[1])<<8);
        if(system64||(architecture!=9&&architecture!=12)){minidump=false;break;}
        system64=true;
      }
    }
    minidump=minidump&&system64;
  }
  if(!elf&&!macho&&!minidump)throw Error("E_CORE_INPUT","core reader requires a64-bit ELF, Mach-O or LLDB minidump core file");auto before=input.sha();
  Temporary temporary{createTemporaryDirectory("nex-core")};auto request=temporary.path/"request.json";
  Object recordedImages;for(const auto &[current,recorded]:options.recordedImages)recordedImages[current]=recorded;
  writeFile(request.string(),json(Object{{"core",core.string()},{"manifest",path.string()},{"compiler",options.compiler},{"formatter",formatter},{"program",image.string()},{"recorded_program",options.recordedProgram},{"recorded_images",std::move(recordedImages)},{"expression",options.expression},{"thread",options.thread},{"frame",options.frame}}));
  auto driver=std::getenv("NEX_LLDB");std::string lldb=driver?driver:"lldb";
  auto script=resourceFile("debug/core_report.py");
  auto child=runTaskProcess({lldb,"--no-lldbinit","--batch","--no-use-colors","-o","settings set target.load-script-from-symbol-file false","-o","settings set symbols.enable-external-lookup false","-o","command script import "+json(script,false)},temporary.path.string(),{{"NEX_CORE_REQUEST",request.string()}},options.timeout,(temporary.path/"logs").string());
  input.samePath(core);if(input.sha()!=before)throw Error("E_CORE_CHANGED","core bytes changed during inspection");
  for(const auto &[path,sha]:ownedHashes)if(Input(path,512*1048576).sha()!=sha)throw Error("E_CORE_CHANGED","owned image changed during core inspection");
  if(child.timedOut||child.outputLimit||child.interrupted||child.process.code!=0)throw Error("E_CORE_READ","native core reader failed (exit="+std::to_string(child.process.code)+", timeout="+std::to_string(child.timedOut)+", output_limit="+std::to_string(child.outputLimit)+", signal="+std::to_string(child.interrupted)+", deadline_seconds="+std::to_string(options.timeout)+"): "+child.process.errors.substr(0,4096));
  std::string marker="NEX_CORE_RESULT ";JSON report=nullptr;unsigned found=0;llvm::StringRef remaining(child.process.output);
  while(!remaining.empty()){auto [line,rest]=remaining.split('\n');remaining=rest;if(line.consume_front(marker)){if(++found!=1)throw Error("E_CORE_READ","duplicate native core report");report=parseNativeManifest(line.str());}}
  if(found!=1||!report.getAsObject())throw Error("E_CORE_READ","native core reader returned no checked report: "+child.process.errors.substr(0,4096));
  auto &result=*report.getAsObject();if(!result.getBoolean("ok").value_or(false))throw Error("E_CORE_READ",result.getString("error").value_or("native core inspection failed").str());
  result["toolchain"]=NEX_VERSION;result["language"]=languageVersion;result["compiler_build"]=NEX_BUILD_ID;result["revision"]=required(m,"revision");result["source_hash"]=required(m,"source_hash");result["build_key"]=required(m,"build_key");
  result["core"]=Object{{"path",core.string()},{"bytes",int64_t(input.initialSize)},{"sha256",before},{"unchanged",true}};result["build_completion_checked"]=true;
  auto executable=result.getObject("executable");if(!executable)throw Error("E_CORE_READ","native core report lacks executable identity");(*executable)["blake3"]=imageHash;(*executable)["bytes"]=int64_t(imageBytes);
  return report;
}
JSON inspectCoreCapsule(const std::string &directory,const CoreOptions &options){
  validateCoreOptions(options);
  auto capsule=fs::absolute(directory).lexically_normal();
  Temporary temporary{createTemporaryDirectory("nex-core-capsule-read")};
  auto prepared=capsuleWork(Object{{"mode","prepare"},{"capsule",capsule.string()},{"work",temporary.path.string()},{"identity",capsuleIdentity()}});
  const auto &p=object(prepared);CoreOptions projected=options;
  projected.core=required(p,"core");projected.manifest=required(p,"manifest");projected.recordedProgram=required(p,"recorded_program");
  projected.originalProgram=required(p,"original_program");
  if(auto images=p.getObject("recorded_images"))for(const auto &[name,value]:*images){auto recorded=value.getAsString();if(!recorded)throw Error("E_CORE_CAPSULE","invalid recorded owned image map");projected.recordedImages[name.str()]=recorded->str();}
  auto report=inspectCore(projected);auto &result=*report.getAsObject();
  auto core=result.getObject("core");
  if(!core||core->getString("sha256")!=required(p,"core_sha256")||Input(capsule/"capsule.json",8*1048576).sha()!=required(p,"manifest_sha256"))throw Error("E_CORE_CHANGED","capsule core or manifest changed during inspection");
  result["capsule"]=Object{{"directory",capsule.string()},{"manifest_sha256",required(p,"manifest_sha256")},{"recorded_program",projected.recordedProgram},{"files_verified",p.getInteger("files").value_or(0)},{"inventory_checked",true},{"inspection_workspace_ephemeral",true},{"dependency_scope",required(p,"dependency_scope")}};
  return report;
}
JSON exportCoreCapsule(const std::string &directory,const CoreOptions &options){
  validateCoreOptions(options);
  auto destination=fs::absolute(directory).lexically_normal();std::error_code error;
  if(fs::exists(fs::symlink_status(destination,error)))throw Error("E_CORE_CAPSULE","core capsule destination already exists");
  auto parent=fs::canonical(destination.parent_path(),error);
  if(error||!fs::is_directory(parent))throw Error("E_CORE_CAPSULE","core capsule destination requires an existing parent directory");
  destination=parent/destination.filename();
  auto original=fs::absolute(options.manifest).lexically_normal();
  requireCapsuleProgram(loadBundle(read(original.parent_path()/"source-bundle.json",16*1048576),original.parent_path().string()));
  auto inspected=inspectCore(options);const auto &initial=object(inspected);const auto *core=initial.getObject("core");
  if(!core)throw Error("E_CORE_CAPSULE","core export lacks checked input identity");
  Temporary staging{capsuleStagingDirectory(parent)};
  auto copied=capsuleWork(Object{{"mode","export"},{"work",staging.path.string()},{"manifest",original.string()},{"core",fs::absolute(options.core).lexically_normal().string()},{"core_sha256",required(*core,"sha256")},{"identity",capsuleIdentity()}});
  auto verified=inspectCoreCapsule(staging.path.string(),options);const auto &v=object(verified);const auto *binding=v.getObject("capsule");
  if(!binding)throw Error("E_CORE_CAPSULE","core export lacks verified capsule inventory");
#ifdef __APPLE__
  int status=::renameatx_np(AT_FDCWD,staging.path.c_str(),AT_FDCWD,destination.c_str(),RENAME_EXCL);
#elif defined(__linux__) && defined(SYS_renameat2)
  int status=int(::syscall(SYS_renameat2,AT_FDCWD,staging.path.c_str(),AT_FDCWD,destination.c_str(),RENAME_NOREPLACE));
#elif defined(_WIN32)
  int status=MoveFileExW(staging.path.c_str(),destination.c_str(),MOVEFILE_WRITE_THROUGH)?0:-1;
  if(status)errno=GetLastError()==ERROR_ALREADY_EXISTS||GetLastError()==ERROR_FILE_EXISTS?EEXIST:EIO;
#else
  int status=-1;
  errno=ENOTSUP;
#endif
  if(status!=0)throw Error("E_CORE_CAPSULE",std::string("cannot publish capsule without replacing an existing destination: ")+std::strerror(errno));
  staging.path.clear();
  return Object{{"schema","nex.core-capsule-export/1"},{"ok",true},{"directory",destination.string()},{"manifest",(destination/"capsule.json").string()},{"manifest_sha256",required(*binding,"manifest_sha256")},{"build_key",required(v,"build_key")},{"revision",required(v,"revision")},{"files",object(copied).getInteger("files").value_or(0)},{"bytes",object(copied).getInteger("bytes").value_or(0)},{"read_after_export",true},{"inferior_execution",false}};
}
}
