#include "nex/backend.h"
#include "nex/task_frontend.h"
#include "nex/task_native.h"
#include "nex/task_reference.h"
#include "nex/web.h"
#include "nex_files.h"
#include "nex_host.h"
#include <filesystem>
#include <iostream>

int main(int argc,char **argv){try{
  if(argc<5||argc>7)throw nex::Error("E_OPTION","write probe requires MODE SOURCE OUTPUT LANGUAGE [PROFILE]");
  const std::string mode=argv[1],language=argv[4];
  auto version=language=="0.24"?nex::SourceLanguage::TaskStreams024:language=="0.23"?nex::SourceLanguage::TaskWrites023:language=="0.22"?nex::SourceLanguage::TaskForeign022:nex::SourceLanguage::Language018;
  if(language!="0.24"&&language!="0.23"&&language!="0.22")throw nex::Error("E_OPTION","stream probe accepts retained022/023 or private024 only");
  auto path=std::filesystem::absolute(argv[2]);nex::Program p;
  if(path.extension()==".json"){
    auto bundle=llvm::json::parse(nex::readFile(path.string()));if(!bundle)throw nex::Error("E_BUNDLE","invalid source bundle JSON");
    p=nex::loadVersionedBundle(*bundle,path.parent_path().string(),language);
  }else{p=nex::parseVersioned(nex::readFile(path.string()),path.string(),version);nex::check(p);}
  llvm::json::Object output{{"ok",true},{"language",nex::programLanguage(p)},{"revision",nex::revision(p)},{"public_default",nex::languageVersion}};
  if(mode=="eval"||mode=="eval-read-grant"){
    nexrt::TaskExecutionLimits limits;limits.workers=1;limits.steps=16000000;limits.timeoutMs=30000;
    std::unique_ptr<nexrt::RequestScope> request;std::unique_ptr<nexrt::FileScope> files;
    nexrt::FileReadGrant readGrant;const nexrt::FileReadGrant *explicitRead=nullptr;
    if(mode=="eval-read-grant"){
      request=std::make_unique<nexrt::RequestScope>();files=std::make_unique<nexrt::FileScope>(true);
      readGrant=nexrt::captureFileReadGrant();explicitRead=&readGrant;
    }
    auto result=nex::evaluateTaskReference(p,"main",{},limits.steps,{},&limits,nullptr,explicitRead);
    output["value"]=result.value.scalar;output["stdout"]=result.output;
    output["external_tickets_after_scope"]=int64_t(result.external.pending);
    output["external_reserved_bytes_after_scope"]=int64_t(result.external.reservedBytes);
  }else if(mode=="build"){
    nex::BuildOptions options;options.profile=argc>5?argv[5]:"debug";options.taskLimits.workers=1;options.taskLimits.steps=16000000;options.taskLimits.timeoutMs=30000;
    auto result=nex::build(p,argv[3],options);output["executable"]=result.executable;output["mlir"]=result.mlir;output["llvm"]=result.llvm;
  }else if(mode=="emit"){
    output["mlir"]=nex::emitTaskNativeStep(p,argc>5?argv[5]:"main").mlir;
  }else if(mode=="typescript"){
    auto emitted=nex::emitTypeScript(p,{{"main","main"}});output["typescript"]=emitted.source;
  }else if(mode!="check")throw nex::Error("E_OPTION","unsupported write probe mode");
  std::cout<<nex::json(std::move(output))<<'\n';return 0;
}catch(const nex::Error &error){std::cout<<nex::json(llvm::json::Object{{"ok",false},{"code",error.code},{"message",error.what()},{"line",int64_t(error.span.line)},{"stdout",error.output}})<<'\n';return 1;}
catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 2;}}
