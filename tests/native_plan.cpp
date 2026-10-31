// Readonly compiler-private planning receipt. Not installed in an SDK.
#include "nex/incremental.h"
#include "llvm/Support/Error.h"
#include <filesystem>
#include <iostream>
#ifdef _WIN32
#include <io.h>
#include <fcntl.h>
#endif

int main(int argc,char **argv){
  using namespace nex;
  try{
    if(argc!=3)throw Error("E_OPTION","expected source and JSON options");
    auto options=llvm::json::parse(argv[2]);
    if(!options)throw Error("E_JSON",llvm::toString(options.takeError()));
    auto object=options->getAsObject();if(!object)throw Error("E_OPTION","expected options object");
    if(object->getBoolean("read_file").value_or(false)){
#ifdef _WIN32
      if(_setmode(_fileno(stdout),_O_BINARY)==-1)throw Error("E_FILE","cannot select binary probe output");
#endif
      auto bytes=readFile(argv[1]);std::cout.write(bytes.data(),static_cast<std::streamsize>(bytes.size()));return 0;
    }
    std::vector<std::string> exports;
    if(auto values=object->getArray("exports"))for(const auto &value:*values){
      auto name=value.getAsString();if(!name)throw Error("E_OPTION","export must be text");exports.push_back(name->str());
    }
    auto program=loadProgram(argv[1],std::filesystem::path(argv[1]).parent_path().parent_path().string());
    auto plan=planNative(program,object->getString("entry").value_or("main").str(),exports,object->getBoolean("all_callable").value_or(false));
    llvm::json::Array units;
    for(const auto &unit:plan.units){
      llvm::json::Array functions;for(const auto &name:unit.functions)functions.push_back(name);
      units.push_back(llvm::json::Object{{"identity",unit.identity},{"unit",unit.unit},{"module",unit.module},
        {"contract",unit.contract},{"source",unit.source},{"functions",std::move(functions)},
        {"wire",unit.wire},{"storage",unit.storage},{"files",unit.files},{"foreign",unit.foreign}});
    }
    std::cout<<json(llvm::json::Object{{"units",std::move(units)},{"dependencies",std::move(plan.dependencies)}},false)<<'\n';
    return 0;
  }catch(const Error &error){std::cout<<json(llvm::json::Object{{"code",error.code},{"message",error.what()}})<<'\n';return 1;}
  catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 2;}
}
