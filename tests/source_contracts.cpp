#include "host_test.h"
#include "nex/backend.h"
#include "nex/web.h"
#include "nex/verification.h"
#include "nex/task_frontend.h"
#include "nex/task_reference.h"
#include "nex/task_native.h"
#include "llvm/Support/Error.h"
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
    const auto requested=std::string(argv[1]);
    if(requested=="cohort-import"&&argc!=7)throw Error("E_OPTION","cohort-import needs source, output, library, project root and provider record");
    auto root=requested=="cohort-import"?std::filesystem::absolute(argv[5]):path.parent_path();
    auto p=loadVersionedProgram(path.string(),root.string(),std::string(argv[1])=="retained"?SourceLanguage::TypedErrors027:SourceLanguage::Contracts028);
    std::string entry=p.function("main").name;auto mode=std::string(argv[1]);
    if(mode=="check"||mode=="retained"){
      llvm::json::Array functions;for(const auto &function:p.functions)functions.push_back(canonical(function));
      auto snapshot=sourceBundle(p);auto roundtrip=loadVersionedBundle(snapshot,path.parent_path().string(),programLanguage(p));
      if(revision(roundtrip)!=revision(p))throw Error("E_TEST","source contract archive failed roundtrip");
      std::cout<<json(llvm::json::Object{{"ok",true},{"language",programLanguage(p)},{"revision",revision(p)},{"functions",std::move(functions)}})<<'\n';return 0;
    }
    if(mode=="contract-template"){
      if(argc!=4)throw Error("E_OPTION","contract-template needs a symbol");
      std::cout<<json(contractTemplate(p,argv[3]))<<'\n';return 0;
    }
    if(mode=="runtime-contract"||mode=="verify-contract"){
      if(argc!=5)throw Error("E_OPTION","contract action needs input JSON and output path");
      auto value=llvm::json::parse(readFile(argv[3]));if(!value){llvm::consumeError(value.takeError());throw Error("E_TEST","invalid contract fixture");}
      auto result=mode=="runtime-contract"?runtimeContractCandidate(p,*value,root.string()):
        verifyContracts(p,*value,llvm::json::Object{{"nodes",llvm::json::Array{}}},VerificationOptions{"",argv[4]});
      if(mode=="runtime-contract")writeFile(argv[4],json(result)+"\n");
      std::cout<<json(result)<<'\n';return 0;
    }
    if(mode=="cohort-import"){
      auto value=llvm::json::parse(readFile(argv[6]));if(!value){llvm::consumeError(value.takeError());throw Error("E_TEST","invalid provider fixture");}
      auto provider=parseNativeTaskProvider(*value);
      NativeLibraryInput library;library.path=argv[4];library.digest=hash(readFile(library.path));library.abi=provider.cohort;
      library.taskProviderPath=argv[6];library.taskProviderDigest=hash(readFile(library.taskProviderPath));
      BuildOptions options;options.entry=entry;options.projectLibraryABI=true;options.staticTaskABI=true;
      options.taskLinkageMode=NativeTaskLinkageMode::Static;options.taskComponent="app";
      for(const auto &[name,exported]:provider.exports){library.contracts[name]=exported.contract;options.taskImportedFunctions.insert(name);}
      options.libraries.push_back(library);auto result=build(p,argv[3],options);
      std::cout<<json(llvm::json::Object{{"artifact",result.executable},{"language",programLanguage(p)},{"library_abi",result.libraryABI}})<<'\n';return 0;
    }
    if(mode=="typescript-run"){
      if(argc!=4)throw Error("E_OPTION","typescript-run needs output directory");
      auto result=runTypeScriptTest(emitTypeScript(p,{{"entry",entry}}),argv[3]);
      std::cout<<json(llvm::json::Object{{"exit_code",result.code},{"stdout",result.output},{"stderr",result.errors}})<<'\n';return 0;
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
