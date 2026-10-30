#include "nex/wasm.h"
#include "nex/project.h"
#include "nex/task_reference.h"
#include "llvm/Support/Error.h"
#include <filesystem>
#include <iostream>
using namespace nex;
int main(int argc,char **argv){try{
  if(argc!=7)throw Error("E_OPTION","expected SOURCE LANGUAGE ENTRY PROFILE OUTPUT MODE");
  auto language=std::string(argv[2])=="0.27"?SourceLanguage::TypedErrors027:SourceLanguage::ExceptionHandlers026;
  auto p=loadVersionedProgram(argv[1],std::filesystem::path(argv[1]).parent_path().string(),language);
  if(std::string(argv[6])=="reference"){
    auto r=evaluateTaskReference(p,argv[3]);std::cout<<json(llvm::json::Object{{"ok",true},{"stdout",r.output},{"language",programLanguage(p)}})<<'\n';
  }else if(std::string(argv[6])=="emit")std::cout<<emitWasmMLIR(p,argv[3],std::string(argv[4])=="release");
  else std::cout<<json(buildWasm(p,argv[5],argv[3],argv[4]))<<'\n';
  return 0;
}catch(const Error &e){std::cout<<json(llvm::json::Object{{"ok",false},{"code",e.code},{"message",e.what()}})<<'\n';return 1;}
catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
