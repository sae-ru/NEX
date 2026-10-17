#include "nex/native_toolchain.h"
#include "llvm/TargetParser/Host.h"
#include "llvm/TargetParser/Triple.h"
#include <cstdlib>
#include <filesystem>

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
}
NativeToolchain configureNative(const BuildOptions &options) {
  NativeToolchain result;
  auto host=llvm::sys::getDefaultTargetTriple();llvm::Triple hostABI(host);
  auto override=std::getenv("NEX_CLANG");result.compiler=override?override:NEX_CLANG;
  bool triple=!options.target.empty()&&options.target!="server"&&options.target!="native";
  result.target=triple?llvm::Triple::normalize(options.target):host;
  std::string manifest;
  if(!options.toolchain.empty()) {
    auto file=std::filesystem::absolute(options.toolchain);
    if(!std::filesystem::is_regular_file(file)||std::filesystem::file_size(file)>65536)throw Error("E_TOOLCHAIN","toolchain requires a JSON file of at most 64 KiB");
    manifest=readFile(file.string());auto parsed=llvm::json::parse(manifest);
    if(!parsed){llvm::consumeError(parsed.takeError());throw Error("E_TOOLCHAIN","invalid toolchain JSON");}
    auto object=parsed->getAsObject();if(!object)throw Error("E_TOOLCHAIN","toolchain must be an object");
    keys(*object,{"schema","target","compiler","sysroot","sqlite","openssl"});
    if(text(*object,"schema",true)!="nex.toolchain/1")throw Error("E_TOOLCHAIN","expected nex.toolchain/1");
    auto target=llvm::Triple::normalize(text(*object,"target",true));
    if(triple&&result.target!=target)throw Error("E_TOOLCHAIN","--target conflicts with toolchain target");
    result.target=target;
    auto path=[&](const llvm::json::Object &from,const std::string &key,bool directory){
      auto value=text(from,key);if(value.empty())return value;
      auto path=std::filesystem::path(value);if(path.is_relative())path=file.parent_path()/path;
      // Preserve clang++'s final symlink name: argv[0] selects C++ driver mode.
      path=key=="compiler"?std::filesystem::weakly_canonical(path.parent_path())/path.filename():std::filesystem::weakly_canonical(path);
      if(directory?!std::filesystem::is_directory(path):!std::filesystem::is_regular_file(path))throw Error("E_TOOLCHAIN","missing toolchain path: "+path.string());
      return path.string();
    };
    if(object->get("compiler"))result.compiler=path(*object,"compiler",false);
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
  if(result.hostCompatible){
    if(result.sqliteInclude.empty()){result.sqliteInclude=NEX_SQLITE_INCLUDE;result.sqliteLibrary=NEX_SQLITE_LIBRARY;}
    if(result.opensslInclude.empty()){result.opensslInclude=NEX_OPENSSL_INCLUDE;result.opensslSSL=NEX_OPENSSL_SSL;result.opensslCrypto=NEX_OPENSSL_CRYPTO;}
  }
  result.driver={result.compiler};
  if(triple||!options.toolchain.empty())result.driver.push_back("--target="+result.target);
  if(!result.sysroot.empty())result.driver.insert(result.driver.end(),{"--sysroot="+result.sysroot});
  std::string sdkIdentity;
  if(!result.sysroot.empty())for(const auto &name:{"SDKSettings.json","SDKSettings.plist"}){auto file=std::filesystem::path(result.sysroot)/name;if(std::filesystem::is_regular_file(file))sdkIdentity+=hash(readFile(file.string()));}
  llvm::json::Array arguments;for(const auto &argument:result.driver)arguments.push_back(argument);
  result.identity=json(llvm::json::Object{{"schema","nex.toolchain-input/1"},{"target",result.target},{"driver",std::move(arguments)},{"sdk_identity",sdkIdentity},
    {"sqlite_include",result.sqliteInclude},{"sqlite_library",result.sqliteLibrary},{"openssl_include",result.opensslInclude},{"openssl_ssl",result.opensslSSL},{"openssl_crypto",result.opensslCrypto}},false);
  return result;
}
void requireNativeHost(const BuildOptions &options) {
  if(!configureNative(options).hostCompatible)throw Error("E_TARGET_RUN","this command executes host code; build the selected target and run/test it on a matching machine; no emulator is configured");
}
void requireNativeHost(const BuildResult &result) {
  if(!result.hostCompatible)throw Error("E_TARGET_RUN","built artifact requires another architecture; run/test it on a matching machine; no emulator is configured");
}
}
