// Test driver for the compiler-private build API. Not installed in an SDK.
#include "nex/backend.h"
#include "llvm/Support/Error.h"
#include <filesystem>
#include <iostream>

int main(int argc,char **argv) {
  using namespace nex;
  try {
    if(argc!=4)throw Error("E_OPTION","expected source, cache and JSON options");
    auto parsed=llvm::json::parse(argv[3]);
    if(!parsed)throw Error("E_JSON",llvm::toString(parsed.takeError()));
    auto o=parsed->getAsObject();if(!o)throw Error("E_JSON","expected options object");
    if(auto completion=o->getObject("completion_metadata")){
      llvm::json::Array paths;for(const auto &path:nativeCompletionInputs(*completion))paths.push_back(path);
      std::cout<<json(llvm::json::Object{{"paths",std::move(paths)}})<<'\n';return 0;
    }
    BuildOptions options;
    options.projectLibraryABI=true;
    options.entry=o->getString("entry").value_or("main").str();
    options.profile=o->getString("profile").value_or("debug").str();
    options.target=o->getString("target").value_or("native").str();
    options.libraryEntry=o->getBoolean("library").value_or(false);
    options.codeOnlyLibrary=o->getBoolean("code_only").value_or(false);
    options.positionIndependent=o->getBoolean("pic").value_or(false);
    options.deferredLink=o->getBoolean("defer").value_or(false);
    if(auto entries=o->getArray("exports"))for(const auto &entry:*entries)options.libraryExports.push_back(entry.getAsString()->str());
    if(auto libraries=o->getArray("libraries"))for(const auto &library:*libraries){
      auto l=library.getAsObject();NativeLibraryInput input;
      input.path=l->getString("artifact")->str();input.digest=l->getString("hash")->str();input.abi=l->getString("library_abi")->str();
      for(const auto &[name,contract]:*l->getObject("contracts"))input.contracts[name.str()]=contract.getAsString()->str();
      options.libraries.push_back(std::move(input));
    }
    auto program=loadProgram(argv[1],std::filesystem::path(argv[1]).parent_path().parent_path().string());
    auto built=build(program,argv[2],options);
    llvm::json::Object contracts;for(const auto &[name,contract]:built.functionContracts)contracts[name]=contract;
    std::cout<<json(llvm::json::Object{{"artifact",built.executable},{"hash",hash(readFile(built.executable))},
      {"key",built.key},{"cached",built.cached},{"library_abi",built.libraryABI},{"contracts",std::move(contracts)},
      {"metadata",(std::filesystem::path(built.executable).parent_path()/"build.json").string()},
      {"compilation",built.compilation},{"compiled_functions",built.compiledFunctions},{"reused_functions",built.reusedFunctions}})<<'\n';
    return 0;
  }catch(const Error &error){std::cout<<json(llvm::json::Object{{"code",error.code},{"message",error.what()}})<<'\n';return 1;}
  catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 2;}
}
