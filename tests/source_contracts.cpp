#include "host_test.h"
#include "nex/backend.h"
#include "nex/web.h"
#include "nex/task_frontend.h"
#include "nex/task_reference.h"
#include "nex/task_native.h"
#include "nex_host.h"
#include "nex_value.h"
#ifndef _WIN32
#include <dlfcn.h>
#endif
#include <filesystem>
#include <iostream>
using namespace nex;
int main(int argc,char **argv){
  try{
    if(argc==3&&std::string(argv[1])=="run"){
      auto baseline=nexrt::liveObjects.load();
      void *library=dlopen(argv[2],RTLD_NOW|RTLD_LOCAL);if(!library)throw std::runtime_error(dlerror());
      auto entry=reinterpret_cast<int(*)(int,const char *const*)>(dlsym(library,"main"));if(!entry)throw std::runtime_error(dlerror());
      // Force the linked runtime object into this test host; generated code uses
      // exactly these exported runtime definitions, including application cleanup.
      if(!nexrt::inRequestScope())nex_runtime_finish();
      int status=entry(0,nullptr);
      if(nexrt::liveObjects.load()!=baseline)throw std::runtime_error("native values survived application exit");
      dlclose(library);return status;
    }
    if(argc<3)throw std::runtime_error("expected reference source, or emit source output triple layout optimized");
    auto path=std::filesystem::absolute(argv[2]);
    auto p=loadVersionedProgram(path.string(),path.parent_path().string(),std::string(argv[1])=="retained"?SourceLanguage::TypedErrors027:SourceLanguage::Contracts028);
    std::string entry=p.function("main").name;auto mode=std::string(argv[1]);
    if(mode=="check"||mode=="retained"){
      llvm::json::Array functions;for(const auto &function:p.functions)functions.push_back(canonical(function));
      auto snapshot=sourceBundle(p);auto roundtrip=loadVersionedBundle(snapshot,path.parent_path().string(),programLanguage(p));
      if(revision(roundtrip)!=revision(p))throw Error("E_TEST","source contract archive failed roundtrip");
      std::cout<<json(llvm::json::Object{{"ok",true},{"language",programLanguage(p)},{"revision",revision(p)},{"functions",std::move(functions)}})<<'\n';return 0;
    }
    if(mode=="typescript"){
      if(argc!=4)throw Error("E_OPTION","typescript needs output directory");
      writeWebModule(emitTypeScript(p,{{"main",entry}}),argv[3]);return 0;
    }
    if(mode=="ast"||mode=="ir"){
      try{
        auto result=mode=="ast"?evaluateTaskReference(p,entry):evaluateTaskIRReference(p,entry);
        std::cout<<json(llvm::json::Object{{"kind","return"},{"value",result.value.scalar},{"output",result.output}})<<'\n';
      }catch(const Error &error){std::cout<<json(llvm::json::Object{{"kind","trap"},{"code",error.code},{"output",error.output},{"line",int64_t(error.span.line)}})<<'\n';}
      return 0;
    }
    if(std::string(argv[1])=="reference"){
      try{auto result=evaluate(p,entry,1000000);std::cout<<json(llvm::json::Object{{"kind","return"},{"value",std::move(result.value)},{"output",result.output}})<<'\n';}
      catch(const SourceException &error){std::cout<<json(llvm::json::Object{{"kind","exception"},{"code",error.code},{"message",error.message},{"line",int64_t(error.span.line)},{"column",int64_t(error.span.column)},{"file",error.span.file},{"output",error.output}})<<'\n';}
      catch(const Error &error){std::cout<<json(llvm::json::Object{{"kind","trap"},{"code",error.code},{"output",error.output},{"line",int64_t(error.span.line)},{"column",int64_t(error.span.column)},{"file",error.span.file}})<<'\n';}
      return 0;
    }
    if(argc!=7)throw std::runtime_error("emit expects source output triple layout optimized");
    auto out=std::filesystem::absolute(argv[3]);std::filesystem::create_directories(out);
    auto mlir=usesTaskEffects(p,entry)?emitTypedErrorTasksDevelopmentNative(p,entry,std::string(argv[6])=="true").mlir:emitMLIR(p,entry);
    writeFile((out/"program.mlir").string(),mlir);
    writeFile((out/"program.ll").string(),lowerMLIRToLLVM(mlir,path.string(),argv[4],argv[5]));return 0;
  }catch(const Error &error){std::cerr<<error.code<<": "<<error.what()<<" at "<<error.span.line<<'\n';}
  catch(const std::exception &error){std::cerr<<error.what()<<'\n';}
  return 1;
}
