#include "host_test.h"
#include "nex/backend.h"
#include "nex/web.h"
#include "nex/task_frontend.h"
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
    auto path=std::filesystem::absolute(argv[2]);auto p=parseSourceExceptionsPrototype(readFile(path.string()),path.string());check(p);
    if(std::string(argv[1])=="reference"){
      try{auto result=evaluate(p,"main",1000000);std::cout<<json(llvm::json::Object{{"kind","return"},{"value",std::move(result.value)},{"output",result.output}})<<'\n';}
      catch(const SourceException &error){std::cout<<json(llvm::json::Object{{"kind","exception"},{"code",error.code},{"message",error.message},{"line",int64_t(error.span.line)},{"column",int64_t(error.span.column)},{"file",error.span.file},{"output",error.output}})<<'\n';}
      catch(const Error &error){std::cout<<json(llvm::json::Object{{"kind","trap"},{"code",error.code},{"line",int64_t(error.span.line)},{"column",int64_t(error.span.column)},{"file",error.span.file}})<<'\n';}
      return 0;
    }
    if(argc==4&&std::string(argv[1])=="typescript"){
      writeWebModule(emitSourceExceptionsPrototypeTypeScript(p,{{"main","main"}}),std::filesystem::absolute(argv[3]).string());return 0;
    }
    if(argc!=7)throw std::runtime_error("emit expects source output triple layout optimized");
    auto out=std::filesystem::absolute(argv[3]);std::filesystem::create_directories(out);
    auto mlir=emitSourceExceptionsPrototypeMLIR(p,"main",std::string(argv[6])=="true");
    writeFile((out/"program.mlir").string(),mlir);
    writeFile((out/"program.ll").string(),lowerMLIRToLLVM(mlir,path.string(),argv[4],argv[5]));return 0;
  }catch(const Error &error){std::cerr<<error.code<<": "<<error.what()<<" at "<<error.span.line<<'\n';}
  catch(const std::exception &error){std::cerr<<error.what()<<'\n';}
  return 1;
}
