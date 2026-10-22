#include "nex/task_native.h"
#include "nex/task_frontend.h"
#include "nex/backend.h"
#include <filesystem>
#include <iostream>
int main(int argc,char **argv){
  using namespace nex;
  std::string stage="arguments";
  try{
    if(argc!=6)throw Error("E_OPTION","expected source, output, triple, layout, entry");
    auto source=std::filesystem::absolute(argv[1]);auto out=std::filesystem::absolute(argv[2]);std::filesystem::create_directories(out);
    stage="load";auto program=loadTaskPrototype(source.string(),source.parent_path().string());
    stage="emit";
    auto step=emitTaskNativeStep(program,argv[5]);
    writeFile((out/"program.mlir").string(),step.mlir);
    stage="lower";writeFile((out/"program.ll").string(),lowerMLIRToLLVM(step.mlir,source.string(),argv[3],argv[4]));
    llvm::json::Array slots,parameters;
    for(auto kind:step.slotKinds)slots.push_back(kind);for(auto id:step.parameters)parameters.push_back(int64_t(id));
    std::cout<<json(llvm::json::Object{{"symbol",step.symbol},{"descriptor",step.descriptorSymbol},{"slots",std::move(slots)},{"parameters",std::move(parameters)},{"public_source_tasks",false}})<<'\n';return 0;
  }catch(const Error &e){std::cout<<json(llvm::json::Object{{"code",e.code},{"message",e.what()},{"stage",stage}})<<'\n';return 1;}
  catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 2;}
}
