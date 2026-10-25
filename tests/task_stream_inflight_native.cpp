#include "nex_task_frame.h"
#include "task_stream_inflight_support.h"
extern "C" const nexrt::TaskCodeDescriptor *NEX_TEST_DESCRIPTOR();
namespace {
using namespace nexrt;using namespace inflight_test;
Gate *activeGate=nullptr;
void observe(const NativeTaskFrame &frame,int64_t transition){
  if(transition!=3||!frame.pendingRequest)return;
  if(frame.pendingRequest->operation==TaskRequestKind::Cancel)activeGate->beforeSourceCancel();
  else if(frame.pendingRequest->operation==TaskRequestKind::Wait)activeGate->afterSourceCancel();
}
struct Context {std::shared_ptr<TaskFrameHostContext> host;};
TaskBody factory(TaskGroup &group,Value,Value,const void *raw){auto context=*static_cast<const Context*>(raw);return executeTaskFrame(group,NativeTaskFrame(*NEX_TEST_DESCRIPTOR(),{}, {},context.host),observe);}
}
int main(int argc,char **argv){try{
 using namespace nexrt;using namespace inflight_test;
 require(argc==5,"native inflight expects mode, operation, occurrence, root");
 auto result=exercise(argv[4],argv[1],operation(argv[2]),std::stoull(argv[3]),[](Gate &gate,RequestScope &request,const FileReadGrant &reads,const FileWriteGrant &writes){
  Execution result;auto host=std::make_shared<TaskFrameHostContext>();host->fileReads=reads;host->fileWrites=writes;host->fileCleanup=std::make_shared<ResourceExecutor>();Context context{host};
  {TaskGroup group(1,4096,{},true);group.enableResourceRegions({},true,true);activeGate=&gate;
   gate.setup(request.deadline(),[&]{request.cancel();},[&]{auto s=group.externalStats();return std::pair{s.tickets,s.running};});
   auto task=group.spawnWithContext(factory,&context);
   try{result.value=group.join(task).scalar;}catch(const Trap &e){result.error=e.code;}
   try{group.finish();}catch(const Trap &e){if(result.error.empty())result.error=e.code;else require(result.error==e.code,"physical drain replaced first failure");}
   require(group.externalStats().tickets==0&&group.externalStats().reservedBytes==0,"native inflight retained IO credits");
  }
  host->fileCleanup->drain();require(host->fileCleanup->stats().resources==0,"native inflight retained owning cleanup");host->fileCleanup->finish();result.physicalSettlement=true;return result;
 });
 require(result.externalTickets>0&&result.externalRunning>0,"native physical IO was not running at its gate");nex_runtime_finish();print(result);return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
