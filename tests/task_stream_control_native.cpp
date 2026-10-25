#include "nex_task_frame.h"
#include "nex_task_limits.h"
#include <array>
#include <atomic>
#include <chrono>
#include <future>
#include <iostream>
#include <map>
#include <thread>

extern "C" const nexrt::TaskCodeDescriptor *NEX_TEST_DESCRIPTOR();
namespace {
using namespace nexrt;
TaskGroup *active=nullptr;
std::string mode;
TaskRequestKind selected=TaskRequestKind::Yield;
size_t occurrence=0,observed=0;
bool fired=false;
std::chrono::steady_clock::time_point deadline;
std::promise<void> reached,release;
std::shared_future<void> released=release.get_future().share();
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
void observe(const NativeTaskFrame &frame,int64_t transition){
  if(mode=="none"||transition!=3||!frame.pendingRequest||frame.pendingRequest->operation!=selected||++observed!=occurrence)return;
  fired=true;
  if(mode=="cancel")active->cancel();
  else if(mode=="deadline")std::this_thread::sleep_until(deadline+std::chrono::milliseconds(1));
  else{reached.set_value();released.wait();}
}
struct Context {std::shared_ptr<const TaskFrameHostContext> host;};
TaskBody factory(TaskGroup &group,Value,Value,const void *raw){
  auto context=*static_cast<const Context*>(raw);
  return executeTaskFrame(group,NativeTaskFrame(*NEX_TEST_DESCRIPTOR(),{}, {},context.host),observe);
}
}
int main(int argc,char **argv){try{
  using namespace nexrt;
  require(argc==5,"native control expects mode, operation, occurrence, root");mode=argv[1];
  const std::map<std::string,TaskRequestKind> operations={{"none",TaskRequestKind::Yield},{"file_open_write",TaskRequestKind::FileOpenWrite},
    {"file_write",TaskRequestKind::FileWrite},{"file_flush",TaskRequestKind::FileFlush},{"file_close",TaskRequestKind::FileClose}};
  selected=operations.at(argv[2]);occurrence=std::stoull(argv[3]);
  require(mode=="none"||mode=="cancel"||mode=="deadline"||mode=="revoke","invalid native control mode");
  auto baseline=liveObjects.load();std::string failure;int64_t value=0;
  {
    TextFiles files(argv[4],true);RequestScope request(maximumTaskExecutionSteps,mode=="deadline"?5000:30000);deadline=request.deadline();
    auto scope=std::make_unique<FileScope>(files);auto host=std::make_shared<TaskFrameHostContext>();
    host->fileReads=captureFileReadGrant(false);host->fileWrites=captureFileWriteGrant(false);
    host->fileCleanup=std::make_shared<ResourceExecutor>();Context context{host};
    TaskGroup group(1,4096,{},true);group.enableResourceRegions({},true,true);active=&group;
    auto task=group.spawnWithContext(factory,&context);
    if(mode=="revoke"){
      auto event=reached.get_future();bool matched=event.wait_for(std::chrono::seconds(10))==std::future_status::ready;
      if(matched)scope.reset();release.set_value();require(matched,"native source did not reach revoke boundary");
    }
    try{value=group.join(task).scalar;}catch(const Trap &error){failure=error.code;}
    try{group.finish();}catch(const Trap &error){if(failure.empty())failure=error.code;else require(failure==error.code,"physical drain replaced first source failure");}
    require(group.externalStats().tickets==0&&group.externalStats().reservedBytes==0,"native control left physical IO credits");
    host->fileCleanup->drain();require(host->fileCleanup->stats().resources==0,"native control left physical file quota/finalizers");host->fileCleanup->finish();
  }
  require(liveObjects.load()==baseline,"native control leaked source values");nex_runtime_finish();
  std::cout<<"{\"ok\":true,\"control_error\":\""<<failure<<"\",\"control_fired\":"<<(fired?"true":"false")
    <<",\"value\":"<<value<<",\"physical_file_settlement\":true,\"live_objects_restored\":true}\n";return 0;
}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
