#include "nex/native_toolchain.h"
#include "llvm/TargetParser/Host.h"
#include "llvm/TargetParser/Triple.h"
#include "llvm/Support/Program.h"
#include "llvm/Support/FileSystem.h"
#include <cstdlib>
#include <filesystem>
#include <functional>

namespace nex {
namespace {
void keys(const llvm::json::Object &object, const std::set<std::string> &allowed) {
  for (const auto &[key,value] : object)
    if (!allowed.contains(key.str())) throw Error("E_TOOLCHAIN", "unknown toolchain field: " + key.str());
}
std::string text(const llvm::json::Object &object, const std::string &key, bool required=false) {
  auto value=object.get(key);if(!value){if(required)throw Error("E_TOOLCHAIN","missing toolchain field: "+key);return "";}
  auto string=value->getAsString();if(!string||string->empty()||string->contains('\0'))throw Error("E_TOOLCHAIN","toolchain field must be a nonempty string: "+key);
  return string->str();
}
NativeToolchain hostDefaults() {
  namespace fs=std::filesystem;
  NativeToolchain result;
  result.compiler=NEX_CLANG;
  result.wasmLinker=NEX_WASM_LD;
  result.archiver=(fs::path(NEX_LLVM_TOOLS)/"llvm-ar").string();
  llvm::Triple host(llvm::sys::getDefaultTargetTriple());
  if(host.isOSLinux())result.linker=(fs::path(NEX_LLVM_TOOLS)/"ld.lld").string();
  if(host.isOSDarwin())result.debugPackager=(fs::path(NEX_LLVM_TOOLS)/"dsymutil").string();
  result.sqliteInclude=NEX_SQLITE_INCLUDE;result.sqliteLibrary=NEX_SQLITE_LIBRARY;
  result.opensslInclude=NEX_OPENSSL_INCLUDE;result.opensslSSL=NEX_OPENSSL_SSL;result.opensslCrypto=NEX_OPENSSL_CRYPTO;
  auto executable=llvm::sys::fs::getMainExecutable(nullptr,nullptr);
  if(executable.empty())return result;
  auto root=fs::weakly_canonical(fs::path(executable).parent_path().parent_path());
  auto manifest=root/"share/nex/sdk-host.json";
  if(fs::symlink_status(manifest).type()==fs::file_type::not_found)return result;
  try {
    if(!fs::is_regular_file(manifest)||fs::file_size(manifest)>65536)throw Error("E_TOOLCHAIN","SDK descriptor requires a JSON file of at most 64 KiB");
    auto parsed=llvm::json::parse(readFile(manifest.string()));
    if(!parsed){llvm::consumeError(parsed.takeError());throw Error("E_TOOLCHAIN","invalid SDK descriptor JSON");}
    auto object=parsed->getAsObject();if(!object)throw Error("E_TOOLCHAIN","SDK descriptor must be an object");
    keys(*object,{"schema","tools","sqlite","openssl"});
    if(text(*object,"schema",true)!="nex.sdk-host/1")throw Error("E_TOOLCHAIN","expected nex.sdk-host/1");
    auto group=[&](const std::string &name,const std::set<std::string> &fields)->const llvm::json::Object&{
      auto value=object->getObject(name);if(!value)throw Error("E_TOOLCHAIN","SDK descriptor requires object: "+name);
      keys(*value,fields);return *value;
    };
    auto path=[&](const llvm::json::Object &from,const std::string &key,bool directory){
      fs::path relative(text(from,key,true));
      if(relative.is_absolute()||relative.has_root_path())throw Error("E_TOOLCHAIN","SDK path must be relative: "+key);
      for(const auto &part:relative)if(part=="..")throw Error("E_TOOLCHAIN","SDK path cannot contain '..': "+key);
      auto candidate=(root/relative).lexically_normal(),real=fs::weakly_canonical(candidate);
      auto remainder=real.lexically_relative(root);
      if(remainder.empty()||*remainder.begin()==".."||(directory?!fs::is_directory(real):!fs::is_regular_file(real)))
        throw Error("E_TOOLCHAIN","missing or escaping SDK path: "+key);
      // Preserve the final name: clang++ and ld.lld dispatch through argv[0].
      return candidate.string();
    };
    const auto &tools=group("tools",{"compiler","archiver","linker","debug_packager","wasm_linker"});
    result.compiler=path(tools,"compiler",false);result.archiver=path(tools,"archiver",false);
    if(host.isOSLinux()||tools.get("linker"))result.linker=path(tools,"linker",false);
    if(host.isOSDarwin()||tools.get("debug_packager"))result.debugPackager=path(tools,"debug_packager",false);
    result.wasmLinker=tools.get("wasm_linker")?path(tools,"wasm_linker",false):"";
    const auto &sqlite=group("sqlite",{"include","library"});
    result.sqliteInclude=path(sqlite,"include",true);result.sqliteLibrary=path(sqlite,"library",false);
    const auto &ssl=group("openssl",{"include","ssl","crypto"});
    result.opensslInclude=path(ssl,"include",true);result.opensslSSL=path(ssl,"ssl",false);result.opensslCrypto=path(ssl,"crypto",false);
    result.sdkManifest=manifest.string();
  }catch(const Error &error){throw Error("E_SDK",std::string(error.what())+"; descriptor: "+manifest.string());}
  return result;
}
}
NativeToolchain configureNative(const BuildOptions &options) {
  NativeToolchain result;
  auto host=llvm::sys::getDefaultTargetTriple();llvm::Triple hostABI(host);
  auto defaults=hostDefaults();
  result.wasmLinker=defaults.wasmLinker;
  auto override=std::getenv("NEX_CLANG");result.compiler=override?override:defaults.compiler;
  result.archiver=defaults.archiver;result.debugPackager=defaults.debugPackager;result.sdkManifest=defaults.sdkManifest;
  bool triple=!options.target.empty()&&options.target!="server"&&options.target!="native";
  result.target=triple?llvm::Triple::normalize(options.target):host;
  std::string manifest;
  if(!options.toolchain.empty()) {
    auto file=std::filesystem::absolute(options.toolchain);
    if(!std::filesystem::is_regular_file(file)||std::filesystem::file_size(file)>65536)throw Error("E_TOOLCHAIN","toolchain requires a JSON file of at most 64 KiB");
    manifest=readFile(file.string());auto parsed=llvm::json::parse(manifest);
    if(!parsed){llvm::consumeError(parsed.takeError());throw Error("E_TOOLCHAIN","invalid toolchain JSON");}
    auto object=parsed->getAsObject();if(!object)throw Error("E_TOOLCHAIN","toolchain must be an object");
    keys(*object,{"schema","target","compiler","linker","archiver","debug_packager","sysroot","sqlite","openssl"});
    if(text(*object,"schema",true)!="nex.toolchain/1")throw Error("E_TOOLCHAIN","expected nex.toolchain/1");
    auto target=llvm::Triple::normalize(text(*object,"target",true));
    if(triple&&result.target!=target)throw Error("E_TOOLCHAIN","--target conflicts with toolchain target");
    result.target=target;
    auto path=[&](const llvm::json::Object &from,const std::string &key,bool directory){
      auto value=text(from,key);if(value.empty())return value;
      auto path=std::filesystem::path(value);if(path.is_relative())path=file.parent_path()/path;
      // Driver dispatch depends on argv[0]: clang++ selects C++, ld.lld selects ELF.
      path=(key=="compiler"||key=="linker")?std::filesystem::weakly_canonical(path.parent_path())/path.filename():std::filesystem::weakly_canonical(path);
      if(directory?!std::filesystem::is_directory(path):!std::filesystem::is_regular_file(path))throw Error("E_TOOLCHAIN","missing toolchain path: "+path.string());
      return path.string();
    };
    if(object->get("compiler"))result.compiler=path(*object,"compiler",false);
    if(object->get("archiver"))result.archiver=path(*object,"archiver",false);
    if(object->get("debug_packager"))result.debugPackager=path(*object,"debug_packager",false);
    result.linker=path(*object,"linker",false);
    result.sysroot=path(*object,"sysroot",true);
    auto dependency=[&](const std::string &name,const std::set<std::string> &fields){
      const auto *v=object->get(name);const auto *dep=v?v->getAsObject():nullptr;
      if(v&&!dep)throw Error("E_TOOLCHAIN",name+" must be an object");
      if(dep){keys(*dep,fields);for(const auto &key:fields)text(*dep,key,true);}return dep;
    };
    if(auto sqlite=dependency("sqlite",{"include","library"})){result.sqliteInclude=path(*sqlite,"include",true);result.sqliteLibrary=path(*sqlite,"library",false);}
    if(auto ssl=dependency("openssl",{"include","ssl","crypto"})){result.opensslInclude=path(*ssl,"include",true);result.opensslSSL=path(*ssl,"ssl",false);result.opensslCrypto=path(*ssl,"crypto",false);}
  }
  llvm::Triple abi(result.target);
  auto supportedArch=[](const llvm::Triple &t){auto name=t.getArchName();return name=="arm64"||name=="aarch64"||name=="x86_64";};
  bool sameOS=abi.getOS()==hostABI.getOS()||(abi.isMacOSX()&&hostABI.isMacOSX());
  bool sameArch=abi.getArch()==hostABI.getArch()&&abi.getSubArch()==hostABI.getSubArch();
  bool crossMac=abi.isMacOSX()&&hostABI.isMacOSX()&&supportedArch(abi)&&supportedArch(hostABI)&&abi.getVendor()==llvm::Triple::Apple;
  if(!abi.isArch64Bit()||!sameOS||abi.getEnvironment()!=hostABI.getEnvironment()||(!crossMac&&!sameArch))
    throw Error("E_TARGET","target is not configured: "+result.target+"; available: 64-bit host ABI and macOS arm64/x86_64 on a macOS host");
  result.hostCompatible=sameArch;
  if(result.linker.empty()&&abi.isOSLinux())result.linker=defaults.linker;
  if(!result.linker.empty()){
    auto linker=llvm::sys::findProgramByName(result.linker);if(!linker)throw Error("E_TOOLCHAIN","cannot find native linker: "+result.linker+"; Linux requires matching LLVM LLD or an explicit linker path");
    auto path=std::filesystem::absolute(*linker);result.linker=(std::filesystem::weakly_canonical(path.parent_path())/path.filename()).string();
  }
  if(result.hostCompatible){
    if(result.sqliteInclude.empty()){result.sqliteInclude=defaults.sqliteInclude;result.sqliteLibrary=defaults.sqliteLibrary;}
    if(result.opensslInclude.empty()){result.opensslInclude=defaults.opensslInclude;result.opensslSSL=defaults.opensslSSL;result.opensslCrypto=defaults.opensslCrypto;}
  }
  // Defaults and explicit manifests must normalize to the same captured inputs.
  for(auto path:{&result.sqliteInclude,&result.sqliteLibrary,&result.opensslInclude,&result.opensslSSL,&result.opensslCrypto})if(!path->empty())*path=std::filesystem::weakly_canonical(*path).string();
  result.driver={result.compiler};
  if(triple||!options.toolchain.empty())result.driver.push_back("--target="+result.target);
  if(!result.sysroot.empty())result.driver.insert(result.driver.end(),{"--sysroot="+result.sysroot});
  std::string sdkIdentity;
  if(!result.sysroot.empty())for(const auto &name:{"SDKSettings.json","SDKSettings.plist"}){auto file=std::filesystem::path(result.sysroot)/name;if(std::filesystem::is_regular_file(file))sdkIdentity+=hash(readFile(file.string()));}
  llvm::json::Array arguments;for(const auto &argument:result.driver)arguments.push_back(argument);
  result.identity=json(llvm::json::Object{{"schema","nex.toolchain-input/1"},{"target",result.target},{"driver",std::move(arguments)},{"sdk_identity",sdkIdentity},
    {"linker",result.linker},{"linker_hash",result.linker.empty()?"":hash(readFile(result.linker))},
    {"archiver",result.archiver},{"archiver_hash",hash(readFile(result.archiver))},
    {"debug_packager",result.debugPackager},{"debug_packager_hash",result.debugPackager.empty()?"":hash(readFile(result.debugPackager))},
    {"sqlite_include",result.sqliteInclude},{"sqlite_library",result.sqliteLibrary},{"openssl_include",result.opensslInclude},{"openssl_ssl",result.opensslSSL},{"openssl_crypto",result.opensslCrypto}},false);
  return result;
}
NativeToolchainSnapshot inspectNativeToolchain(const BuildOptions &options) {
  namespace fs=std::filesystem;
  auto configured=configureNative(options);
  auto driver=llvm::sys::findProgramByName(configured.compiler);
  if(!driver)throw Error("E_TOOLCHAIN","cannot locate toolchain compiler: "+configured.compiler);
  auto driverPath=fs::absolute(*driver);auto compiler=(fs::weakly_canonical(driverPath.parent_path())/driverPath.filename()).string();
  llvm::json::Object manifest{{"schema","nex.toolchain/1"},{"target",configured.target},{"compiler",compiler}};
  manifest["archiver"]=configured.archiver;
  if(!configured.debugPackager.empty())manifest["debug_packager"]=configured.debugPackager;
  if(!configured.linker.empty())manifest["linker"]=configured.linker;
  if(!configured.sysroot.empty())manifest["sysroot"]=configured.sysroot;
  if(!configured.sqliteInclude.empty())manifest["sqlite"]=llvm::json::Object{{"include",configured.sqliteInclude},{"library",configured.sqliteLibrary}};
  if(!configured.opensslInclude.empty())manifest["openssl"]=llvm::json::Object{{"include",configured.opensslInclude},{"ssl",configured.opensslSSL},{"crypto",configured.opensslCrypto}};
  llvm::json::Object files;uint64_t bytes=0;
  auto file=[&](const fs::path &path){
    if(!fs::is_regular_file(path)||fs::file_size(path)>512ULL*1048576)throw Error("E_TOOLCHAIN","missing/oversized toolchain input: "+path.string());
    auto name=fs::canonical(path).string();if(files.find(name)!=files.end())return;
    if(files.size()>=4096)throw Error("E_TOOLCHAIN","toolchain fingerprint file count exceeded");
    bytes+=fs::file_size(path);if(bytes>1024ULL*1048576)throw Error("E_TOOLCHAIN","toolchain fingerprint exceeds 1 GiB");
    auto contents=readFile(name);files[name]=llvm::json::Object{{"hash",hash(contents)},{"bytes",int64_t(contents.size())}};
  };
  file(compiler);
  file(configured.archiver);
  if(!configured.debugPackager.empty())file(configured.debugPackager);
  if(!configured.linker.empty())file(configured.linker);
  if(!configured.sqliteInclude.empty()){file(fs::path(configured.sqliteInclude)/"sqlite3.h");file(configured.sqliteLibrary);}
  if(!configured.opensslInclude.empty()){
    file(configured.opensslSSL);file(configured.opensslCrypto);
    std::set<fs::path> seen;
    std::function<void(const fs::path&,unsigned)> headers=[&](const fs::path &directory,unsigned depth){
      if(depth>32)throw Error("E_TOOLCHAIN","toolchain header directory depth exceeded");
      if(!seen.insert(fs::canonical(directory)).second)return;
      for(const auto &entry:fs::directory_iterator(directory)){
        if(entry.is_directory())headers(entry.path(),depth+1);
        else if(entry.is_regular_file())file(entry.path());
      }
    };
    headers(fs::path(configured.opensslInclude)/"openssl",0);
  }
  if(!configured.sysroot.empty())for(const auto &name:{"SDKSettings.json","SDKSettings.plist"}){
    auto path=fs::path(configured.sysroot)/name;if(fs::is_regular_file(path))file(path);
  }
  llvm::json::Value inputs=llvm::json::Object{{"schema","nex.toolchain-snapshot/2"},{"configuration",llvm::json::Object(manifest)},{"files",std::move(files)},
    {"scope","compiler, archiver, debug packager and selected linker binaries, configured SQLite headers/library, OpenSSL headers/libraries and explicit SDK settings; SDK contents, compiler support files, default system linker/libraries and environment are external"}};
  if(json(inputs).size()+1>4*1048576)throw Error("E_TOOLCHAIN","toolchain fingerprint metadata exceeds 4 MiB");
  NativeToolchainSnapshot result;result.hash=hash(json(inputs,false));result.target=configured.target;result.hostCompatible=configured.hostCompatible;result.manifest=std::move(manifest);result.inputs=std::move(inputs);return result;
}
void requireNativeHost(const BuildOptions &options) {
  if(!configureNative(options).hostCompatible)throw Error("E_TARGET_RUN","this command executes host code; build the selected target and run/test it on a matching machine; no emulator is configured");
}
void requireNativeHost(const BuildResult &result) {
  if(!result.hostCompatible)throw Error("E_TARGET_RUN","built artifact requires another architecture; run/test it on a matching machine; no emulator is configured");
}
}
