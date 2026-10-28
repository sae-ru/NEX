#include "nex/backend.h"
#include "nex/task_native.h"
#include "nex/task_frontend.h"
#include "nex/operations.h"
#include "nex/native_images.h"
#include <filesystem>
#include <iostream>
using namespace nex;
int main(int argc,char **argv){try{
  if(argc==3&&std::string(argv[1])=="identity"){std::cout<<nativeImageUUID(argv[2])<<'\n';return 0;}
  if(argc==3&&(std::string(argv[1])=="signatures"||std::string(argv[1])=="signatures-context")){
    auto path=std::filesystem::absolute(argv[2]);auto text=readFile(path.string());auto p=[&](){if(std::string(argv[1])=="signatures-context"){auto value=llvm::json::parse(text);if(!value){llvm::consumeError(value.takeError());throw std::runtime_error("expected context JSON");}if(!value->getAsObject())throw std::runtime_error("expected context object");return loadSourceExceptionTaskContext(*value->getAsObject());}return parseSourceExceptionTasksPrototype(text,path.string());}();check(p);
    llvm::json::Object result;for(const auto &f:p.functions)if(f.foreign)result[f.foreign->symbol]=foreignSignature(p,f);
    std::cout<<json(std::move(result))<<'\n';return 0;
  }
  if(argc!=7&&!(argc==8&&(std::string(argv[7])=="profile"||std::string(argv[7])=="debug"||std::string(argv[7])=="debug-lldb"||std::string(argv[7])=="http")))throw std::runtime_error("expected emit source output triple layout optimized [profile|debug|debug-lldb]");
  auto path=std::filesystem::absolute(argv[2]);auto text=readFile(path.string());auto p=[&](){if(std::string(argv[1])=="emit-context"){auto decoded=llvm::json::parse(text);if(!decoded){llvm::consumeError(decoded.takeError());throw std::runtime_error("expected private source context");}if(!decoded->getAsObject())throw std::runtime_error("expected private source context object");return loadSourceExceptionTaskContext(*decoded->getAsObject());}return parseSourceExceptionTasksPrototype(text,path.string());}();check(p);
  auto out=std::filesystem::absolute(argv[3]);std::filesystem::create_directories(out);
  auto result=argc==8?(std::string(argv[7])=="http"?emitSourceExceptionTasksPrototypeNativeHttp(p,"handle",std::string(argv[6])=="true"):std::string(argv[7])=="profile"?emitSourceExceptionTasksPrototypeNativeProfile(p,"main",std::string(argv[6])=="true"):emitSourceExceptionTasksPrototypeNativeDebug(p,"main",std::string(argv[6])=="true",std::string(argv[7])=="debug-lldb"?60000:5000)):emitSourceExceptionTasksPrototypeNative(p,"main",std::string(argv[6])=="true");
  if(!result.debugContext.empty())writeFile((out/"debug-context.json").string(),result.debugContext);
  writeFile((out/"program.mlir").string(),result.mlir);
  llvm::json::Array operations;
  for(const auto &function:p.functions)for(const auto &operation:operationTree(p,function))operations.push_back(llvm::json::Object{{"site",operation.site},{"kind",operation.kind},{"begin",int64_t(operation.span.begin)-int64_t(function.span.begin)},{"end",int64_t(operation.span.end)-int64_t(function.span.begin)},{"function_hash",hash(json(canonical(function),false))},{"function_source_hash",hash(p.definition(function))},{"line",int64_t(operation.span.line)},{"column",int64_t(operation.span.column)}});
  writeFile((out/"metadata.json").string(),json(llvm::json::Object{{"descriptor_symbol",result.descriptorSymbol},{"descriptor_abi",result.descriptorABI},{"private_task_exceptions",true},{"operations",std::move(operations)}}));
  writeFile((out/"program.ll").string(),lowerMLIRToLLVM(result.mlir,path.string(),argv[4],argv[5]));return 0;
}catch(const Error &e){std::cerr<<e.code<<": "<<e.what()<<" at "<<e.span.line<<'\n';}
catch(const std::exception &e){std::cerr<<e.what()<<'\n';}return 1;}
