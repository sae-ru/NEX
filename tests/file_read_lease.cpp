#include "host_test.h"
#include "nex_files.h"
#include "nex_host.h"
#include "nex_task_file_read.h"
#ifdef NEX_ASYNC_TASKS
#include "nex_tasks.h"
#endif
#include <atomic>
#include <filesystem>
#include <fstream>
#include <future>
#include <cstdlib>
#include <iostream>
#include <thread>
#include <unistd.h>

namespace fs=std::filesystem;
using namespace nexrt;
namespace {
size_t cases=0;
void require(bool value,const char *message){if(!value)throw std::runtime_error(message);}
template<class F>void rejects(const std::string &code,F function){
  try{function();}catch(const DataError &error){require(error.code==code,"unexpected file lease error");++cases;return;}
  throw std::runtime_error("expected file lease failure");
}
void write(const fs::path &path,const std::string &bytes){std::ofstream file(path,std::ios::binary);file.write(bytes.data(),bytes.size());require(bool(file),"cannot write fixture");}
struct Directory {
  fs::path path;
  Directory(){std::string pattern=(fs::temp_directory_path()/"nex-read-lease-XXXXXX").string();auto value=::mkdtemp(pattern.data());require(value,"mkdtemp failed");path=value;}
  ~Directory(){std::error_code ignored;fs::remove_all(path,ignored);}
};
struct Environment {
  std::string key;std::optional<std::string> previous;
  Environment(std::string key,const std::string &value):key(std::move(key)){
    if(auto *old=std::getenv(this->key.c_str()))previous=old;
    ::setenv(this->key.c_str(),value.c_str(),1);
  }
  ~Environment(){if(previous)::setenv(key.c_str(),previous->c_str(),1);else ::unsetenv(key.c_str());resetFileEnvironment();}
};
#ifdef NEX_ASYNC_TASKS
struct GrantTaskState {
  FileReadGrant grant;std::promise<void> entered,release,progress;
  std::shared_future<void> released=release.get_future().share();
  std::atomic<bool> physicalExited{false};std::atomic<unsigned> admitted{0};
};
struct GatedRead final:TaskExternalOperation {
  std::shared_ptr<TaskExternalOperation> read;std::shared_ptr<GrantTaskState> state;
  GatedRead(std::shared_ptr<TaskExternalOperation> read,std::shared_ptr<GrantTaskState> state):read(std::move(read)),state(std::move(state)){}
  TaskExternalResult run(const TaskExternalControl &control)override {
    struct Retired {std::shared_ptr<GrantTaskState> state;~Retired(){state->physicalExited=true;}} retired{state};
    unsigned polls=0;
    return read->run(TaskExternalControl([&]{
      control.checkpoint();
      // The third poll is the first read-loop checkpoint, after open/fstat.
      if(++polls==3){state->entered.set_value();state->released.wait();}
    }));
  }
};
TaskBody grantTask(TaskGroup &group,FileReadGrant grant,std::shared_ptr<GrantTaskState> state){
  // The first resume RequestScope must end before any per-path preparation.
  co_await group.yield();
  auto prepare=[&]{FileScope denied(false);return PreparedTaskFileRead(grant,"data",false);};
  auto first=prepare();
  auto ticket=group.submitExternal(std::make_shared<GatedRead>(first.operation(),state),PreparedTaskFileRead::reservation);
  auto raw=co_await group.awaitExternal(ticket);auto value=first.admit(std::move(raw));++state->admitted;
  auto count=byteBuffer(unwrap(value).object).length();
  co_await group.yield();
  auto second=prepare();ticket=group.submitExternal(second.operation(),PreparedTaskFileRead::reservation);
  raw=co_await group.awaitExternal(ticket);value=second.admit(std::move(raw));++state->admitted;
  co_return Value(int64_t(count+byteBuffer(unwrap(value).object).length()));
}
TaskBody grantProgress(TaskGroup &,std::shared_ptr<GrantTaskState> state){state->progress.set_value();co_return Value(int64_t(0));}
// Only the synchronous root factory reads this fixture; the coroutine receives
// an explicit grant copy before enqueue, with no task/IO worker TLS discovery.
std::shared_ptr<GrantTaskState> coordinatorFactoryState;
TaskBody makeGrantTask(TaskGroup &group,Value,Value){return grantTask(group,coordinatorFactoryState->grant,coordinatorFactoryState);}
TaskBody makeGrantProgress(TaskGroup &group,Value,Value){return grantProgress(group,coordinatorFactoryState);}
void taskGrantTests(TextFiles &capability){
  {
    FileScope files(capability);RequestScope request;auto state=std::make_shared<GrantTaskState>();state->grant=captureFileReadGrant(false);
    coordinatorFactoryState=state;TaskGroup group(1);auto entered=state->entered.get_future(),progress=state->progress.get_future();
    auto reader=group.spawn(makeGrantTask),sibling=group.spawn(makeGrantProgress);
    bool began=entered.wait_for(std::chrono::seconds(2))==std::future_status::ready;
    bool advanced=progress.wait_for(std::chrono::seconds(2))==std::future_status::ready;
    bool physical=state->physicalExited.load();state->release.set_value();
    require(began&&advanced&&!physical,"file operation blocked the source task executor");
    require(group.join(reader).scalar==6&&state->admitted==2,"grant did not survive task parking and a second preparation");
    (void)group.join(sibling);group.finish();coordinatorFactoryState.reset();state->grant.check();
    require(group.externalStats().tickets==0&&group.externalStats().reservedBytes==0,"file task leaked physical transport credits");++cases;
  }
  {
    FileScope files(capability);RequestScope request;auto state=std::make_shared<GrantTaskState>();state->grant=captureFileReadGrant(false);
    coordinatorFactoryState=state;TaskGroup group(1);auto entered=state->entered.get_future();auto reader=group.spawn(makeGrantTask);
    bool began=entered.wait_for(std::chrono::seconds(2))==std::future_status::ready;
    request.cancel();rejects("E_RESOURCE_SCOPE",[&]{state->grant.check();});
    bool physical=state->physicalExited.load();state->release.set_value();
    require(began&&!physical,"root revoke pretended a physical read had retired");
    bool cancelled=false;try{(void)group.join(reader);}catch(const Trap &error){cancelled=error.code=="E_CANCELLED";}
    require(cancelled&&state->physicalExited&&!state->admitted,"cancelled file task admitted a source value or escaped physical drain");
    try{group.finish();}catch(const Trap &error){require(error.code=="E_CANCELLED","unexpected file task drain failure");}
    require(group.externalStats().tickets==0&&group.externalStats().reservedBytes==0,"cancelled file read returned credits before physical retirement");
    coordinatorFactoryState.reset();++cases;
  }
}
#endif
void tests(){
  Directory temporary;auto root=temporary.path/"root",other=temporary.path/"other";fs::create_directory(root);fs::create_directory(other);
  const std::string bytes("A\0\xff",3);write(root/"data",bytes);write(other/"data","wrong grant");
  auto before=liveObjects.load();TextFiles capability(root.string(),false);
  {
    FileScope scope(capability);auto lease=captureFileReadLease("data");
    require(lease.identity()!=0,"lease has no identity");
    // A worker's unrelated TLS grant cannot replace the captured coordinator.
    auto future=std::async(std::launch::async,[lease,other](){
      TextFiles wrong(other.string(),false);FileScope scope(wrong);
      return lease.read();
    });
    auto result=future.get();require(std::string(result.begin(),result.end())==bytes,"worker consulted its ambient grant");++cases;
    auto denied=std::async(std::launch::async,[lease](){FileScope scope(false);rejects("CAPABILITY",[]{(void)captureFileReadLease("data",false);});return lease.read();});
    result=denied.get();require(std::string(result.begin(),result.end())==bytes,"explicit lease was lost on a worker");++cases;
    fs::rename(root,temporary.path/"pinned");fs::create_directory(root);write(root/"data","replaced root");
    auto pinned=captureFileReadLease("data").read();require(std::string(pinned.begin(),pinned.end())==bytes,"root pathname replacement redirected a lease");++cases;
    rejects("VALIDATION",[]{(void)captureFileReadLease("../escape");});
    rejects("VALIDATION",[]{(void)captureFileReadLease("/absolute");});
    rejects("E_UTF8",[]{(void)captureFileReadLease(std::string("\xff",1));});
    auto absent=captureFileReadLease("missing");rejects("NOT_FOUND",[&]{(void)absent.read();});
    fs::create_symlink(other/"data",temporary.path/"pinned/link");
    auto link=captureFileReadLease("link");rejects("VALIDATION",[&]{(void)link.read();});
    write(temporary.path/"pinned/large",std::string(TextFiles::byteLimit+1,'x'));
    auto large=captureFileReadLease("large");rejects("LIMIT",[&]{(void)large.read();});
  }
  {
    auto scope=std::make_unique<FileScope>(capability);auto lease=captureFileReadLease("data");
    std::promise<void> entered,release;auto ready=entered.get_future(),go=release.get_future();
    auto worker=std::async(std::launch::async,[lease,&entered,&go](){
      unsigned polls=0;
      try{(void)lease.read([&]{if(++polls==2){entered.set_value();go.wait();}});return std::string("unexpected success");}
      catch(const DataError &error){return error.code;}
    });
    ready.wait();scope.reset();rejects("E_RESOURCE_SCOPE",[&]{lease.check();});
    require(worker.wait_for(std::chrono::milliseconds(0))==std::future_status::timeout,"logical revoke pretended physical completion");
    release.set_value();require(worker.get()=="E_RESOURCE_SCOPE","in-flight read ignored grant revocation");++cases;
  }
  {
    FileScope scope(capability);FileReadLease requestLease;
    {RequestScope request;requestLease=captureFileReadLease("data");(void)requestLease.read();}
    rejects("E_RESOURCE_SCOPE",[&]{requestLease.check();});
    (void)captureFileReadLease("data").read();++cases;
  }
  {
    FileScope scope(capability);std::vector<FileReadLease> held;
    for(size_t i=0;i<64;++i)held.push_back(captureFileReadLease("data"));
    rejects("E_RESOURCE_LIMIT",[]{(void)captureFileReadLease("data");});
    held.clear();(void)captureFileReadLease("data").read();++cases;
  }
  {
    FileScope scope(capability);
    PreparedTaskFileRead binary("data",false),text("data",true);
    auto result=std::async(std::launch::async,[operation=binary.operation()](){FileScope deny(false);return operation->run(TaskExternalControl{});}).get();
    require(result.bytes.capacity()<=TextFiles::byteLimit,"raw physical capacity exceeded its reservation");
    auto value=binary.admit(std::move(result));auto actual=byteBuffer(unwrap(value).object).view();
    require(std::string(actual.begin(),actual.end())==bytes,"coordinator binary admission changed bytes");++cases;
    auto invalid=text.admit(text.operation()->run(TaskExternalControl{}));
    require(invalid.object->kind==Data::Failure&&invalid.object->text=="E_UTF8","text admission accepted invalid UTF-8");++cases;
    PreparedTaskFileRead missing("missing",false);
    auto rawMissing=std::async(std::launch::async,[operation=missing.operation()](){return operation->run(TaskExternalControl{});}).get();
    require(rawMissing.errorCode=="NOT_FOUND"&&rawMissing.bytes.empty(),"ordinary file error did not use raw transport");
    auto failed=missing.admit(std::move(rawMissing));
    require(failed.object->kind==Data::Failure&&failed.object->text=="NOT_FOUND","ordinary file error was raised instead of returned");++cases;
    TaskExternalResult limit;limit.errorCode="E_TIMEOUT";limit.errorMessage="root expired";
    rejects("E_TIMEOUT",[&]{(void)binary.admit(std::move(limit));});
  }
  {
    auto scope=std::make_unique<FileScope>(capability);PreparedTaskFileRead read("data",false);
    auto result=read.operation()->run(TaskExternalControl{});scope.reset();
    rejects("E_RESOURCE_SCOPE",[&]{(void)read.admit(std::move(result));});
  }
  {
    Environment environment("NEX_FILES_ROOT",other.string());
    FileScope scope(capability);auto grant=captureFileReadGrant(false);
    auto result=std::async(std::launch::async,[grant,other](){
      TextFiles wrong(other.string(),false);FileScope scope(wrong);
      return grant.lease("data").read();
    }).get();
    require(std::string(result.begin(),result.end())==bytes,"per-path grant preparation consulted worker TLS or environment");++cases;
    auto denied=std::async(std::launch::async,[grant](){FileScope scope(false);return grant.lease("data").read();}).get();
    require(std::string(denied.begin(),denied.end())==bytes,"explicit root grant was denied by unrelated worker TLS");++cases;
    rejects("VALIDATION",[&]{(void)grant.lease("../escape");});
    PreparedTaskFileRead prepared(grant,"data",false);auto value=prepared.admit(prepared.operation()->run(TaskExternalControl{}));
    require(byteBuffer(unwrap(value).object).length()==3,"explicit prepared read changed bytes");++cases;
    std::string boundary;
    for(size_t i=0;i<17;++i){if(i)boundary+='/';boundary.append(240,'x');}
    require(boundary.size()==TextFiles::pathLimit,"wrong maximum-path fixture");
    auto maximum=grant.lease(boundary);
    require(maximum.retainedPathBytes()==TextFiles::pathLimit&&PreparedTaskFileRead::reservation>=TextFiles::byteLimit+maximum.retainedPathBytes(),"retained path backing exceeds its declared reservation");
    (void)PreparedTaskFileRead(grant,boundary,false);++cases;
    rejects("VALIDATION",[&]{(void)grant.lease(boundary+"x");});
  }
  {
    Environment environment("NEX_FILES_ROOT",root.string());resetFileEnvironment();auto grant=captureFileReadGrant();
    ::setenv("NEX_FILES_ROOT",other.c_str(),1);
    auto actual=std::async(std::launch::async,[grant](){FileScope denied(false);return grant.lease("data").read();}).get();
    require(std::string(actual.begin(),actual.end())=="replaced root","environment change redirected a coordinator-captured root grant");++cases;
    resetFileEnvironment();rejects("E_RESOURCE_SCOPE",[&]{grant.check();});
  }
  {
    Environment environment("NEX_FILES_ROOT",other.string());FileScope denied(false);
    auto unavailable=captureFileReadGrant(); // Capturing a skipped read cannot throw CAPABILITY.
    bool read=false;if(read)(void)unavailable.lease("data");++cases;
    rejects("CAPABILITY",[&]{unavailable.check();});
    rejects("CAPABILITY",[&]{(void)PreparedTaskFileRead(unavailable,"data",false);});
    rejects("CAPABILITY",[]{(void)FileReadGrant().lease("data");});
  }
  {
    FileReadGrant grant;FileReadLease lease;
    {FileScope scope(capability);grant=captureFileReadGrant(false);lease=grant.lease("data");}
    rejects("E_RESOURCE_SCOPE",[&]{grant.check();});
    rejects("E_RESOURCE_SCOPE",[&]{(void)grant.lease("data");});
    rejects("E_RESOURCE_SCOPE",[&]{lease.check();});
  }
  {
    FileScope scope(capability);FileReadGrant grant;
    {RequestScope request;grant=captureFileReadGrant(false);(void)grant.lease("data").read();}
    rejects("E_RESOURCE_SCOPE",[&]{grant.check();});
    rejects("E_RESOURCE_SCOPE",[&]{(void)grant.lease("data");});
  }
  {
    FileScope scope(capability);RequestScope request;auto grant=captureFileReadGrant(false);std::vector<FileReadLease> held;
    for(size_t i=0;i<64;++i)held.push_back(grant.lease("data"));
    rejects("E_RESOURCE_LIMIT",[&]{(void)grant.lease("data");});
    held.clear();(void)grant.lease("data").read();++cases;
  }
#ifdef NEX_ASYNC_TASKS
  taskGrantTests(capability);
#endif
  rejects("E_RESOURCE_CLOSED",[]{(void)FileReadLease().read();});
  require(liveObjects.load()==before,"raw worker lease created/leaked managed source values");++cases;
}
}
int main(){try{tests();std::cout<<"{\"ok\":true,\"cases\":"<<cases<<",\"worker_reads_explicit_physical_lease\":true,\"explicit_root_grant\":true,\"lexical_revoke\":true,\"request_revoke\":true,\"logical_cancel_is_not_physical_completion\":true,\"public_async_io\":false}\n";return 0;}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
