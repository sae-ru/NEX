#include "nex/web.h"
#include "nex/task_frontend.h"
#include "nex/operations.h"
#include "nex_task_limits.h"
#include <filesystem>
#include <iostream>

// Public execution must use the ordinary checked loader/emitter/test runner.
// This probe also retains the raw018 staging rejection as a separate boundary.
int main(int argc,char **argv)try{
  using namespace nex;
  if(argc!=5&&argc!=8)throw Error("E_OPTION","expected source, output, mode, entry and optional steps/timeoutMs/workers");
  nexrt::TaskExecutionLimits limits;
  if(argc==8){
    auto steps=nexrt::parseTaskLimitDecimal(argv[5],nexrt::maximumTaskExecutionSteps);
    auto timeout=nexrt::parseTaskLimitDecimal(argv[6],nexrt::maximumTaskExecutionTimeoutMs);
    auto workers=nexrt::parseTaskLimitDecimal(argv[7],nexrt::maximumTaskExecutionWorkers);
    if(!steps||!timeout||!workers)throw Error("E_OPTION","invalid probe task limits");
    limits={*steps,*timeout,static_cast<unsigned>(*workers)};
  }
  auto path=std::filesystem::absolute(argv[1]),directory=std::filesystem::absolute(argv[2]);
  std::string mode=argv[3],entry=argv[4];
  Program p=mode=="private"?loadTaskPrototype(path.string(),path.parent_path().string()):loadProgram(path.string(),path.parent_path().string(),false);
  if(mode=="historical")p=loadVersionedBundle(sourceBundle(p),path.parent_path().string(),"0.18");
  if(mode=="retained019")p=loadVersionedBundle(sourceBundle(p),path.parent_path().string(),"0.19");
  if(mode=="ui"){
    auto result=generateWebApp(p,directory.string());std::cout<<json(std::move(result))<<'\n';return 0;
  }
  if(mode!="emit"&&mode!="test"&&mode!="historical"&&mode!="retained019"&&mode!="private")throw Error("E_OPTION","unknown probe mode");
  auto module=emitTypeScript(p,{{"entry",entry}});
  if(std::filesystem::exists(directory))throw Error("E_EXISTS","public output directory must be new");
  llvm::json::Array sites;
  for(const auto &function:p.functions)for(const auto &operation:operationTree(p,function))sites.push_back(operation.site);
  llvm::json::Object result{{"ok",true},{"language",programLanguage(p)},{"revision",revision(p)},
    {"source_hash",hash(json(sourceBundle(p),false))},{"asynchronous",module.asynchronous},
    {"operation_sites",std::move(sites)}};
  if(mode=="test"){
    auto actual=runTypeScriptTest(module,directory.string(),30,argc==8?&limits:nullptr);
    result["exit_code"]=actual.code;result["stdout"]=actual.output;result["stderr"]=actual.errors;
  }else writeWebModule(module,directory.string());
  std::cout<<json(std::move(result))<<'\n';return 0;
}catch(const nex::Error &error){
  std::cout<<nex::json(llvm::json::Object{{"ok",false},{"code",error.code},{"message",error.what()},
    {"line",int64_t(error.span.line)}})<<'\n';return 1;
}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 2;}
