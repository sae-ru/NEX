#include "nex/language.h"
#include "nex/backend.h"
#include "nex/task_typescript.h"
#include "nex_foreign.h"
#include <algorithm>
#include <filesystem>
#include <iostream>
int main(int argc,char **argv)try{
  using namespace nex;using Object=llvm::json::Object;
  if(argc<5||argc>6)throw Error("E_OPTION","usage: private source resource probe COMMAND BUNDLE ROOT OUTPUT [LANGUAGE]");
  std::string command=argv[1],language=argc==6?argv[5]:"0.21";
  auto bundle=llvm::json::parse(readFile(argv[2]));if(!bundle)throw Error("E_JSON","invalid probe input bundle");
  auto p=loadVersionedBundle(*bundle,std::filesystem::absolute(argv[3]).string(),language);
  Object result{{"ok",true},{"public_source_resources",std::string(languageVersion)=="0.21"},{"language",programLanguage(p)},{"revision",revision(p)}};
  if(command=="check"){
    Object resources,signatures;
    for(const auto &s:p.structures)if(s.opaqueResource&&s.typeParameters.empty()&&std::none_of(s.typeArguments.begin(),s.typeArguments.end(),containsParameter)){
      auto [name,identity]=sourceResourceClass(p,s);resources[s.name]=Object{{"name",name},{"identity",identity},{"canonical",canonical(s)}};
    }
    for(const auto &f:p.functions)if(f.foreign)signatures[f.foreign->symbol]=foreignSignature(p,f);
    result["resources"]=std::move(resources);result["signatures"]=std::move(signatures);if(std::string(argv[4])!="-")writeFile(argv[4],json(Object(result))+"\n");
  }else if(command=="reference"||command=="reference-timeout"){
    std::shared_ptr<nexrt::ForeignLibraries> libraries;
    std::unique_ptr<nexrt::ForeignScope> scope;
    if(std::string(argv[4])!="-"){libraries=nexrt::loadForeignLibraries(argv[4]);scope=std::make_unique<nexrt::ForeignScope>(libraries);}
    nexrt::TaskExecutionLimits limits;limits.timeoutMs=1000;limits.workers=1;
    auto evaluated=evaluate(p,"main",1000000,command=="reference-timeout"?&limits:nullptr);result["output"]=evaluated.output;result["value"]=std::move(evaluated.value);result["steps"]=int64_t(evaluated.steps);
    scope.reset();if(libraries){if(libraries->resourceBytesUsed()!=0)throw Error("E_RESOURCE_BYTES","reference exit retained external capacity");result["external_capacity_after_scope"]=int64_t(libraries->resourceBytesUsed());}
  }else if(command=="native"){
    BuildOptions options;options.profile="release";auto built=build(p,argv[4],options);
    result["executable"]=built.executable;result["mlir"]=built.mlir;result["llvm"]=built.llvm;result["cached"]=built.cached;result["foreign_calls"]=built.foreignCalls;
  }else if(command=="web"){
    auto module=emitTypeScript(p,{{"entry","client_value"}});std::filesystem::create_directories(argv[4]);writeWebModule(module,argv[4]);result["directory"]=argv[4];
  }else throw Error("E_OPTION","unknown private resource probe command");
  std::cout<<json(std::move(result))<<'\n';return 0;
}catch(const nex::Error &e){std::cout<<nex::json(llvm::json::Object{{"ok",false},{"code",e.code},{"message",e.what()},{"line",int64_t(e.span.line)}})<<'\n';return 1;}
catch(const nexrt::DataError &e){std::cout<<nex::json(llvm::json::Object{{"ok",false},{"code",e.code},{"message",e.what()}})<<'\n';return 1;}
catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 2;}
