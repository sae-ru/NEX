#include "nex/task_native.h"
#include "nex/backend.h"
#include <filesystem>
#include <iostream>
int main(int argc,char **argv){
 using namespace nex;
 try{
  if(argc!=6)throw Error("E_OPTION","expected source, new output, triple, layout, optimized");
  auto path=std::filesystem::absolute(argv[1]),out=std::filesystem::absolute(argv[2]);
  if(!std::filesystem::create_directory(out))throw Error("E_OPTION","output must be new");
  auto p=parseVersioned(readFile(path.string()),path.string(),SourceLanguage::References030);check(p);
  auto code=emitManagedReferenceTasksDevelopmentNative(p,"main",std::string(argv[5])=="true");
  writeFile((out/"program.mlir").string(),code.mlir);
  writeFile((out/"program.ll").string(),lowerMLIRToLLVM(code.mlir,path.string(),argv[3],argv[4]));
  std::cout<<json(llvm::json::Object{{"ok",true},{"revision",revision(p)},{"descriptor_abi",code.descriptorABI},{"public_source_enabled",false}})<<'\n';
 }catch(const Error &error){std::cerr<<error.code<<": "<<error.message<<'\n';return 1;}
 catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 2;}
}
