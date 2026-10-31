#include "nex_task_file_source.h"
#include <array>
#include <chrono>
#include <condition_variable>
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#include <mutex>
#include <optional>
#include <thread>
#include <unistd.h>

using namespace nexrt;
namespace fs=std::filesystem;
namespace {
void require(bool value,const char *why){if(!value)throw std::runtime_error(why);}
template<class F>void error(const char *code,F body){
  try{body();}catch(const DataError &e){require(e.code==code,"unexpected cleanup diagnostic");return;}
  throw std::runtime_error("expected cleanup rejection");
}
struct Gate {
  std::mutex mutex;std::condition_variable changed;bool arrived=false,released=false;
  void enter(){std::unique_lock lock(mutex);arrived=true;changed.notify_all();changed.wait(lock,[&]{return released;});}
  void wait(){std::unique_lock lock(mutex);require(changed.wait_for(lock,std::chrono::seconds(5),[&]{return arrived;}),"cleanup gate did not start");}
  void open(){{std::lock_guard lock(mutex);released=true;}changed.notify_all();}
  ~Gate(){open();}
};
struct Blocker final:ResourceExecutionOperation {
  std::shared_ptr<Gate> gate;
  explicit Blocker(std::shared_ptr<Gate> gate):gate(std::move(gate)){}
  void run(const ResourceExecutionControl&)override{gate->enter();}
};
struct Blocked {
  std::shared_ptr<Gate> gate=std::make_shared<Gate>();
  ResourceExecution work;
  explicit Blocked(const std::shared_ptr<ResourceExecutor> &executor){
    work=executor->submit(std::make_unique<Blocker>(gate));gate->wait();
  }
  ~Blocked(){gate->open();work.wait();}
  void release(){gate->open();work.wait();}
};
TaskExternalResult execute(const std::shared_ptr<TaskExternalOperation> &operation){
  return std::async(std::launch::async,[operation]{return operation->run(TaskExternalControl{});}).get();
}
void settled(const ResourceRegionRetirement &retirement){
  auto until=std::chrono::steady_clock::now()+std::chrono::seconds(5);
  while(!retirement.ready()){
    require(std::chrono::steady_clock::now()<until,"file finalizer did not settle");
    std::this_thread::sleep_for(std::chrono::milliseconds(1));
  }
}
}
int main(){try{
  auto model=(fs::temp_directory_path()/"nex-file-cleanup-XXXXXX").string();auto *created=::mkdtemp(model.data());require(created,"mkdtemp failed");fs::path root(created);
  struct Cleanup{fs::path root;~Cleanup(){std::error_code e;fs::remove_all(root,e);}}cleanup{root};
  std::ofstream(root/"input",std::ios::binary)<<"abcdef";
  std::ofstream(root/"existing",std::ios::binary)<<"unchanged";
  TextFiles files(root.string(),true);FileScope scope(files);auto reads=captureFileReadGrant(false);auto writes=captureFileWriteGrant(false);
  size_t cases=0;auto run=[&](const char *name,auto body){body();++cases;std::cout<<"PASS "<<name<<'\n';};
  for(auto family:{ResourceRegionFamily::Native,ResourceRegionFamily::Reference}){
    run("source close revokes immediately and queues complete physical cleanup",[&]{
      ResourceRegion region(family);auto actor=region.authority();auto executor=std::make_shared<ResourceExecutor>();Blocked blocked(executor);
      std::array<Value,1> path{Value(string("input"))};PreparedSourceTaskFile opening("file_open_read",path,reads,writes,actor,executor);
      auto result=opening.admit(execute(opening.operation()));require(result.object&&result.object->kind==Data::Success,"source file did not open");
      auto value=result.object->values.at(0);auto alias=fileResource(value.object);
      std::array<Value,1> argument{value};PreparedSourceTaskFile closing("file_close",argument,reads,writes,actor,executor);
      require(!closing.external()&&closing.admit().scalar==1,"logical close did not return true");
      require(!alias.isOpen(),"alias remained logically open");
      error("E_RESOURCE_CLOSED",[&]{alias.leaseInRegion(actor);});
      auto retirement=region.beginClose();retirement.requestClose();
      require(!retirement.ready()&&executor->stats().resources==1&&executor->stats().queued==1,"file payload/quota/fence retired on coordinator");
      blocked.release();executor->drain();settled(retirement);require(executor->stats().resources==0,"file cleanup slot leaked");executor->finish();
    });
    run("last physical stream lease queues cleanup after logical close",[&]{
      ResourceRegion region(family);auto executor=std::make_shared<ResourceExecutor>();Blocked blocked(executor);
      auto file=reads.openRead("input").openInRegion(region.authority(),{},executor);
      std::optional<FileStreamLease> pin(file.leaseInRegion(region.authority()));require(file.close(),"file did not close");
      auto retirement=region.beginClose();retirement.requestClose();
      require(!retirement.ready()&&executor->stats().queued==0,"physical pin was not retained");
      pin.reset();require(!retirement.ready()&&executor->stats().queued==1,"last lease did not enqueue finalizer");
      blocked.release();executor->drain();settled(retirement);executor->finish();
    });
    run("discarded unpublished open drains through its reserved cleanup slot",[&]{
      ResourceRegion region(family);auto executor=std::make_shared<ResourceExecutor>();Blocked blocked(executor);
      PreparedTaskFileOpen opening(reads.openRead("input"),region.authority(),executor);auto raw=execute(opening.operation());
      require(raw.errorCode.empty(),"prepared open failed");opening.discard();
      auto retirement=region.beginClose();retirement.requestClose();require(!retirement.ready()&&executor->stats().queued==1,"discard bypassed owning cleanup");
      blocked.release();executor->drain();settled(retirement);executor->finish();
    });
  }
  run("cleanup capacity rejects before a write open can truncate",[&]{
    ResourceRegion region;auto executor=std::make_shared<ResourceExecutor>(ResourceExecutorLimits{1,1,1024});
    auto first=reads.openRead("input").openInRegion(region.authority(),{},executor);
    PreparedTaskFileOpen opening(writes.openWrite("existing"),region.authority(),executor);
    error("E_RESOURCE_EXECUTOR_LIMIT",[&]{execute(opening.operation());});
    std::ifstream stream(root/"existing");std::string text;stream>>text;require(text=="unchanged","failed cleanup admission truncated file");
    first.close();executor->drain();region.close();executor->finish();
  });
  run("closed cleanup executor rejects before file creation",[&]{
    ResourceRegion region;auto executor=std::make_shared<ResourceExecutor>();executor->close();
    PreparedTaskFileOpen opening(writes.openWrite("must-not-create"),region.authority(),executor);
    error("E_RESOURCE_EXECUTOR",[&]{execute(opening.operation());});
    require(!fs::exists(root/"must-not-create"),"closed executor still created a file");
    auto retirement=region.beginClose();retirement.requestClose();require(retirement.ready(),"failed reservation stranded creation fence");executor->finish();
  });
  run("failed file factory returns cleanup credit and creation settlement",[&]{
    ResourceRegion region;auto executor=std::make_shared<ResourceExecutor>();
    PreparedTaskFileOpen opening(reads.openRead("missing"),region.authority(),executor);auto raw=execute(opening.operation());
    require(raw.errorCode=="NOT_FOUND","missing file error changed");error("NOT_FOUND",[&]{opening.admit(std::move(raw));});
    executor->drain();require(executor->stats().resources==0,"failed factory leaked cleanup credit");
    auto retirement=region.beginClose();retirement.requestClose();require(retirement.ready(),"failed factory lost creation settlement");executor->finish();
  });
  run("original cleanup is retained across a destructive open checkpoint",[&]{
    ResourceRegion region;auto executor=std::make_shared<ResourceExecutor>();auto retained=executor;
    auto file=reads.openRead("input").openInRegion(region.authority(),[&]{executor.reset();},executor);
    require(file.isOpen()&&retained->stats().resources==1,"checkpoint dropped original cleanup reservation");
    file.close();retained->drain();region.close();retained->finish();
  });
  run("closing last public executor handle preserves later file retirement",[&]{
    ResourceRegion region;auto executor=std::make_shared<ResourceExecutor>();Blocked blocked(executor);
    auto file=reads.openRead("input").openInRegion(region.authority(),{},executor);executor.reset();
    file.close();auto retirement=region.beginClose();retirement.requestClose();require(!retirement.ready(),"closed executor lost physical reservation");
    blocked.release();settled(retirement);
  });
  run("source opens cannot fall back to inline finalizers",[&]{
    ResourceRegion region;std::array<Value,1> path{Value(string("must-not-create"))};
    error("E_RESOURCE_EXECUTOR",[&]{PreparedSourceTaskFile opening("file_open_write",path,reads,writes,region.authority(),{});});
    require(!fs::exists(root/"must-not-create"),"missing source cleanup created a file");
  });
  std::cout<<"{\"ok\":true,\"file_cleanup_cases\":"<<cases<<",\"public024_published\":false}\n";return 0;
}catch(const std::exception &e){std::cerr<<e.what()<<'\n';return 1;}}
