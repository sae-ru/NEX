#include "nex/task_frontend.h"
#include "nex/task_reference.h"
#include "task_stream_inflight_support.h"
#include <filesystem>
namespace {
struct Host final:nex::TaskReferenceExternalHost {
 size_t retired=0;
 std::optional<nex::TaskReferenceExternalRequest> prepare(size_t,nex::Span)override{return {};}
 void taskRetired(size_t)noexcept override{++retired;}
};
}
int main(int argc,char **argv){try{
 using namespace nexrt;using namespace inflight_test;
 require(argc==6,"reference inflight expects source, mode, operation, occurrence, root");auto path=std::filesystem::absolute(argv[1]);nex::Program program;
 if(path.extension()==".json"){
  auto bundle=llvm::json::parse(nex::readFile(path.string()));require(bool(bundle),"invalid inflight bundle");program=nex::loadVersionedBundle(*bundle,path.parent_path().string(),"0.24");
 }else{program=nex::parseVersioned(nex::readFile(path.string()),path.string(),nex::SourceLanguage::TaskStreams024);nex::check(program);}
 auto result=exercise(argv[5],argv[2],operation(argv[3]),std::stoull(argv[4]),[&](Gate &gate,RequestScope &request,const FileReadGrant &reads,const FileWriteGrant &writes){
  Execution result;std::stop_source stop;ResourceRegion parent(ResourceRegionFamily::Request);Host host;host.cancellation=stop.get_token();host.resourceRegions=true;host.resourceRequestParent=parent.authority();
  gate.setup(request.deadline(),[&]{request.cancel();stop.request_stop();});TaskExecutionLimits limits;limits.workers=1;limits.steps=16000000;limits.timeoutMs=30000;
  auto observer=[&](size_t,const nex::TaskTransition &transition){
   if(transition.kind!=nex::TaskTransition::Waiting)return;
   if(transition.operation=="task_cancel")gate.beforeSourceCancel();else if(transition.operation=="file_close")gate.beforeSourceClose();else if(transition.operation=="task_wait")gate.afterSourceControl();
  };
  try{auto evaluated=nex::evaluateTaskReference(program,"main",{},limits.steps,observer,&limits,&host,&reads,&writes);result.value=evaluated.value.scalar;require(evaluated.external.pending==0&&evaluated.external.reservedBytes==0,"reference inflight retained IO credits");}
  catch(const nex::Error &e){result.error=e.code;}
  auto settlement=parent.beginClose();settlement.requestClose();require(settlement.ready(),"reference returned before physical file retirement");result.physicalSettlement=true;result.retiredTasks=host.retired;return result;
 });
 print(result);return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
