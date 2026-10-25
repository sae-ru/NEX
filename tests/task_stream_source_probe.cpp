#include "nex/backend.h"
#include "nex/task_frontend.h"
#include "nex/task_native.h"
#include "nex/task_reference.h"
#include "nex/web.h"
#include "nex_files.h"
#include "nex_host.h"
#include <filesystem>
#include <iostream>
#include <stop_token>
#include <thread>

namespace {
struct ControlHost final:nex::TaskReferenceExternalHost {
  size_t retired=0;
  std::optional<nex::TaskReferenceExternalRequest> prepare(size_t,nex::Span)override{return {};}
  void taskRetired(size_t)noexcept override{++retired;}
};
llvm::json::Object controlledReference(const nex::Program &p,const std::string &mode,const std::string &selection){
  auto separator=selection.find(':');if(separator==std::string::npos)throw nex::Error("E_OPTION","control selection requires operation:occurrence");
  auto operation=selection.substr(0,separator);auto occurrence=std::stoull(selection.substr(separator+1));
  if(mode!="cancel"&&mode!="deadline"&&mode!="revoke"&&mode!="none")throw nex::Error("E_OPTION","invalid control mode");
  const auto baseline=nexrt::liveObjects.load();std::string failure;int64_t value=0;size_t observed=0;bool fired=false;
  size_t retired=0;
  {
    nexrt::RequestScope request(nexrt::maximumTaskExecutionSteps,mode=="deadline"?5000:30000);
    auto files=std::make_unique<nexrt::FileScope>(true);auto reads=nexrt::captureFileReadGrant();auto writes=nexrt::captureFileWriteGrant();
    nexrt::ResourceRegion parent(nexrt::ResourceRegionFamily::Request);std::stop_source stop;ControlHost host;
    host.cancellation=stop.get_token();host.resourceRegions=true;host.resourceRequestParent=parent.authority();
    nexrt::TaskExecutionLimits limits;limits.workers=1;limits.steps=16000000;limits.timeoutMs=30000;
    auto observer=[&](size_t,const nex::TaskTransition &transition){
      if(mode=="none"||transition.kind!=nex::TaskTransition::Waiting||transition.operation!=operation||++observed!=occurrence)return;
      fired=true;
      if(mode=="cancel")stop.request_stop();
      else if(mode=="deadline")std::this_thread::sleep_until(request.deadline()+std::chrono::milliseconds(1));
      else files.reset(); // The reference observer is the original coordinator.
    };
    try{auto result=nex::evaluateTaskReference(p,"main",{},limits.steps,observer,&limits,&host,&reads,&writes);value=result.value.scalar;
      if(result.external.pending||result.external.reservedBytes)throw nex::Error("E_TEST","reference left physical IO credits");}
    catch(const nex::Error &error){failure=error.code;}
    auto settlement=parent.beginClose();settlement.requestClose();
    if(!settlement.ready())throw nex::Error("E_TEST","reference returned before physical file settlement");
    retired=host.retired;
  }
  if(nexrt::liveObjects.load()!=baseline)throw nex::Error("E_TEST","reference control leaked source values");
  return llvm::json::Object{{"ok",true},{"control_error",failure},{"control_fired",fired},{"value",value},
    {"physical_file_settlement",true},{"live_objects_restored",true},{"retired_tasks",int64_t(retired)}};
}
}

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
  if(mode=="eval-control"){
    if(argc!=7||language!="0.24")throw nex::Error("E_OPTION","controlled source evaluation requires private024, mode and operation:occurrence");
    auto controlled=controlledReference(p,argv[5],argv[6]);for(auto &entry:controlled)output[entry.first]=std::move(entry.second);
  }else if(mode=="eval"||mode=="eval-read-grant"){
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
  }else if(mode=="stage"){
    if(argc!=7||language!="0.24")throw nex::Error("E_OPTION","staging requires private024, target triple and data layout");
    auto directory=std::filesystem::absolute(argv[3]);std::filesystem::create_directories(directory);
    auto step=nex::emitTaskNativeStep(p,"main");auto mlir=(directory/"program.mlir").string(),llvm=(directory/"program.ll").string();
    nex::writeFile(mlir,step.mlir);nex::writeFile(llvm,nex::lowerMLIRToLLVM(step.mlir,path.string(),argv[5],argv[6]));
    output["mlir"]=mlir;output["llvm"]=llvm;output["descriptor"]=step.descriptorSymbol;
  }else if(mode=="emit"){
    output["mlir"]=nex::emitTaskNativeStep(p,argc>5?argv[5]:"main").mlir;
  }else if(mode=="typescript"){
    auto emitted=nex::emitTypeScript(p,{{"main","main"}});output["typescript"]=emitted.source;
  }else if(mode!="check")throw nex::Error("E_OPTION","unsupported write probe mode");
  std::cout<<nex::json(std::move(output))<<'\n';return 0;
}catch(const nex::Error &error){std::cout<<nex::json(llvm::json::Object{{"ok",false},{"code",error.code},{"message",error.what()},{"line",int64_t(error.span.line)},{"stdout",error.output}})<<'\n';return 1;}
catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 2;}}
