#include "nex/native_toolchain.h"
#include "llvm/Support/FormatVariadic.h"
#include "llvm/Support/raw_ostream.h"
#include <iostream>

int main(int argc,char **argv){
  if(argc!=8)return 2;
  nex::NativeToolchain tools;
  tools.target=argv[1];tools.sqliteLibrary=argv[2];tools.opensslSSL=argv[3];tools.opensslCrypto=argv[4];
  try{
    llvm::json::Array paths;
    for(const auto &path:nex::nativeRuntimeSearchPaths(tools,std::string(argv[5])=="1",std::string(argv[6])=="1",std::string(argv[7])=="1"))paths.push_back(path);
    llvm::outs()<<nex::json(llvm::json::Object{{"ok",true},{"paths",std::move(paths)}},true)<<'\n';return 0;
  }catch(const nex::Error &error){
    llvm::outs()<<nex::json(llvm::json::Object{{"ok",false},{"code",error.code},{"message",error.what()}},true)<<'\n';return 1;
  }
}
