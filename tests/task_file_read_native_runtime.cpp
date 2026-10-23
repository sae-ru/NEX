#include "nex_task_application.h"
#include "nex_task_file_read.h"
#include <array>
#include <atomic>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#include <new>
#include <unistd.h>

// Controlled actual allocation failure on a source scheduler, not an ambient
// runtime option. The first failed allocation disarms before cleanup runs.
thread_local bool failAllocation=false;
void *operator new(std::size_t size){if(failAllocation){failAllocation=false;throw std::bad_alloc();}if(auto p=std::malloc(size?size:1))return p;throw std::bad_alloc();}
void operator delete(void *p)noexcept{std::free(p);}
void *operator new[](std::size_t size){return ::operator new(size);}
void operator delete[](void *p)noexcept{::operator delete(p);}

using namespace nexrt;
namespace fs=std::filesystem;
namespace {
size_t cases=0;
void require(bool condition,const char *message){if(!condition)throw std::runtime_error(message);}
template<class F>void rejects(const char *code,F action){
  try{action();}catch(const DataError &error){require(error.code==code,"unexpected raw read error");++cases;return;}
  catch(const Trap &error){require(error.code==code,"unexpected compiled read error");++cases;return;}
  throw std::runtime_error("expected read failure");
}
struct Directory {
  fs::path path;
  Directory(){std::string name=(fs::temp_directory_path()/"nex-native-read-XXXXXX").string();auto p=::mkdtemp(name.data());require(p,"mkdtemp failed");path=p;}
  ~Directory(){std::error_code ignored;fs::remove_all(path,ignored);}
};
std::string selectedPath="data",expectedError,expectedBinary("A\0\xff",3);
bool text=false,skip=false;
std::array<int64_t,1> kinds{3};
constexpr int64_t requirements=taskCodeDeclaredTask|taskCodeServer|taskCodeDeclaredFs|taskCodeFileRead|taskCodeImageFileRead;
int64_t readStep(void *pointer){
  auto &frame=*static_cast<NativeTaskFrame*>(pointer);
  if(skip){nex_task_frame_return_i64(pointer,42,0);return 0;}
  if(frame.pc==0){
    auto arguments=makeHandle(Value(std::make_shared<Data>(Data::List)));
    readHandle(arguments).object->values.push_back(Value(string(selectedPath)));
    nex_task_frame_pause_at(pointer,int64_t(text?TaskRequestKind::FileReadText:TaskRequestKind::FileReadBytes),arguments,0,3,17,nullptr);
    nex_release(arguments);nex_task_frame_set_pc(pointer,1);return 3;
  }
  auto value=frame.read(0,3);
  if(!expectedError.empty())require(value.object->kind==Data::Failure&&value.object->text==expectedError,"ordinary preparation/IO failure did not become a typed result");
  else if(text)require(unwrap(value).object->text==std::string("A\0\xf0\x9f\xa7\xa0",6),"compiled text read changed UTF-8/NUL");
  else {auto bytes=byteBuffer(unwrap(value).object).view();require(std::string(bytes.begin(),bytes.end())==expectedBinary,"compiled byte read changed arbitrary octets or grant");}
  nex_task_frame_return_i64(pointer,42,0);return 0;
}
TaskCodeDescriptor descriptor{readStep,kinds.data(),nullptr,nullptr,nullptr,taskCodeABI,1,0,0,0,requirements};
void clean(){require(!inRequestScope()&&liveObjects==0,"compiled file read leaked source ownership");nex_runtime_finish();}
void execute(TextFiles &files){FileScope scope(files);require(executeTaskApplication(descriptor,{1000000,5000,1},{})==42,"compiled read returned wrong process value");++cases;}
std::promise<void> *paused=nullptr;std::shared_future<void> resume;
void revokeObserver(const NativeTaskFrame &frame,int64_t transition){if(transition==3&&frame.pendingRequest){paused->set_value();resume.wait();}}
void allocationObserver(const NativeTaskFrame &frame,int64_t transition){if(transition==3&&frame.pendingRequest)failAllocation=true;}
void timeoutObserver(const NativeTaskFrame &frame,int64_t transition){if(transition==3&&frame.pendingRequest)throw Trap("E_TIMEOUT","first source failure",17);}
struct FactoryContext {std::shared_ptr<const TaskFrameHostContext> host;TaskStepObserver observer=nullptr;};
TaskBody frameFactory(TaskGroup &group,Value,Value,const void *pointer){
  const auto &context=*static_cast<const FactoryContext*>(pointer);
  return executeTaskFrame(group,NativeTaskFrame(descriptor,{}, {},context.host),context.observer);
}
struct HeldState {
  std::promise<void> entered,release;std::shared_future<void> released=release.get_future().share();
  std::atomic<bool> retired{false},admitted{false};std::atomic<unsigned> progress{0};bool lateLimit=false;
};
struct HeldOperation final:TaskExternalOperation {
  std::shared_ptr<HeldState> state;explicit HeldOperation(std::shared_ptr<HeldState> state):state(std::move(state)){}
  TaskExternalResult run(const TaskExternalControl &)override {
    struct Retired {HeldState &state;~Retired(){state.retired=true;}} retired{*state};
    state->entered.set_value();state->released.wait();
    if(state->lateLimit)throw DataError("E_LIMIT","late held failure");throw std::bad_alloc();
  }
};
TaskBody heldTask(TaskGroup &group,std::shared_ptr<HeldState> state){
  auto ticket=group.submitExternal(std::make_shared<HeldOperation>(state),PreparedTaskFileRead::reservation);
  (void)co_await group.awaitExternal(ticket);state->admitted=true;co_return Value(int64_t(0));
}
TaskBody progressTask(TaskGroup &group,std::shared_ptr<HeldState> state){for(;;){co_await group.yield();++state->progress;}co_return Value(int64_t(0));}
TaskBody heldFactory(TaskGroup &group,Value,Value,const void *context){return heldTask(group,*static_cast<const std::shared_ptr<HeldState>*>(context));}
TaskBody progressFactory(TaskGroup &group,Value,Value,const void *context){return progressTask(group,*static_cast<const std::shared_ptr<HeldState>*>(context));}
void stickyFatal(TextFiles &files,const char *first,TaskStepObserver observer){
  FileScope scope(files);RequestScope request;
  FactoryContext context{std::make_shared<TaskFrameHostContext>(captureFileReadGrant(false)),observer};
  TaskExternalLimits limits;limits.workers=1;limits.reservedBytes=PreparedTaskFileRead::reservation;
  TaskGroup group(1,4096,limits,true);auto state=std::make_shared<HeldState>();state->lateLimit=std::string(first)=="E_MEMORY";
  auto entered=state->entered.get_future();auto held=group.spawnWithContext(heldFactory,&state);
  bool started=entered.wait_for(std::chrono::seconds(2))==std::future_status::ready;
  if(!started){state->release.set_value();throw std::runtime_error("held physical operation did not start");}
  auto progress=group.spawnWithContext(progressFactory,&state);auto reader=group.spawnWithContext(frameFactory,&context);
  // The read's real byte admission limit, prepare allocation failure or source
  // timeout must stop unrelated source before the held operation can retire.
  rejects(first,[&]{(void)group.join(reader);});rejects(first,[&]{(void)group.join(progress);});
  require(!state->retired&&!state->admitted&&group.externalStats().tickets==1,"first source fatal did not retain held physical ownership");
  auto stopped=state->progress.load();state->release.set_value();
  rejects(first,[&]{group.finish();});
  require(state->retired&&!state->admitted&&state->progress==stopped,"source ran/admitted after first fatal or physical drain was skipped");
  require(group.externalStats().tickets==0&&group.externalStats().reservedBytes==0,"fatal source drain leaked physical credits");
  (void)held;
}
void tests(){
  Directory directory;
  {std::ofstream file(directory.path/"data",std::ios::binary);file.write("A\0\xff",3);}
  {std::ofstream file(directory.path/"text",std::ios::binary);file.write("A\0\xf0\x9f\xa7\xa0",6);}
  TextFiles files(directory.path.string(),false);
  execute(files);clean();selectedPath="text";text=true;execute(files);clean();
  selectedPath="data";expectedError="E_UTF8";execute(files);clean();text=false;
  selectedPath="missing";expectedError="NOT_FOUND";execute(files);clean();
  selectedPath="../escape";expectedError="VALIDATION";execute(files);clean();
  selectedPath="data";expectedError="CAPABILITY";
  {FileScope denied(false);require(executeTaskApplication(descriptor,{1000000,5000,1},{})==42,"denied grant failed entry instead of attempted read");++cases;}clean();
  skip=true;expectedError.clear();
  {FileScope denied(false);require(executeTaskApplication(descriptor,{1000000,5000,1},{})==42,"non-taken read required a grant");++cases;}clean();skip=false;
  {
    std::optional<std::string> previous;if(auto p=std::getenv("NEX_FILES_ROOT"))previous=p;
    Directory other;{std::ofstream file(other.path/"data",std::ios::binary);file<<"xyz";}
    ::setenv("NEX_FILES_ROOT",directory.path.c_str(),1);
    require(executeTaskApplication(descriptor,{1000000,5000,1},{})==42,"first standalone invocation failed");
    ::setenv("NEX_FILES_ROOT",other.path.c_str(),1);expectedBinary="xyz";
    require(executeTaskApplication(descriptor,{1000000,5000,1},{})==42,"later standalone invocation reused a stale environment root");++cases;
    expectedBinary=std::string("A\0\xff",3);if(previous)::setenv("NEX_FILES_ROOT",previous->c_str(),1);else ::unsetenv("NEX_FILES_ROOT");
  }clean();
  {
    RequestScope request;auto plain=descriptor;plain.requirements=0;NativeTaskFrame frame(plain,{},{});
    auto arguments=makeHandle(Value(std::make_shared<Data>(Data::List)));readHandle(arguments).object->values.push_back(Value(string("data")));
    rejects("E_TASK_STATE",[&]{nex_task_frame_pause_at(&frame,int64_t(TaskRequestKind::FileReadBytes),arguments,0,3,1,nullptr);});
    auto bad=descriptor;bad.requirements=taskCodeFileRead;rejects("E_TASK_STATE",[&]{NativeTaskFrame invalid(bad,{},{});});
    bad=descriptor;bad.requirements=taskCodeDeclaredFs|taskCodeServer;rejects("E_TASK_STATE",[&]{NativeTaskFrame invalid(bad,{},{});});
    bad=descriptor;bad.abi=INT64_C(0x4e45585400000001);rejects("E_TASK_STATE",[&]{NativeTaskFrame invalid(bad,{},{});});
    NativeTaskFrame valid(descriptor,{},{});
    rejects("E_TASK_STATE",[&]{nex_task_frame_pause_at(&valid,int64_t(TaskRequestKind::FileReadBytes),arguments,0,0,1,nullptr);});
    readHandle(arguments).object->values[0]=Value(7);rejects("E_TASK_STATE",[&]{nex_task_frame_pause_at(&valid,int64_t(TaskRequestKind::FileReadBytes),arguments,0,3,1,nullptr);});
    readHandle(arguments).object->values.clear();rejects("E_TASK_STATE",[&]{nex_task_frame_pause_at(&valid,int64_t(TaskRequestKind::FileReadBytes),arguments,0,3,1,nullptr);});
    nex_release(arguments);
  }clean();
  {
    auto scope=std::make_unique<FileScope>(files);RequestScope request;
    FactoryContext context{std::make_shared<TaskFrameHostContext>(captureFileReadGrant(false)),revokeObserver};TaskGroup group(1,4096,{},true);
    std::promise<void> entered,release;auto ready=entered.get_future();paused=&entered;resume=release.get_future().share();
    auto task=group.spawnWithContext(frameFactory,&context);
    bool reached=ready.wait_for(std::chrono::seconds(2))==std::future_status::ready;scope.reset();release.set_value();require(reached,"compiled read did not reach request boundary");
    rejects("E_RESOURCE_SCOPE",[&]{(void)group.join(task);});
    try{group.finish();}catch(const Trap &error){require(error.code=="E_RESOURCE_SCOPE","revoked frame cleanup changed failure");}
    require(group.externalStats().tickets==0,"prepare after revocation created an external ticket");
  }clean();
  {
    FileScope scope(files);RequestScope request;
    FactoryContext context{std::make_shared<TaskFrameHostContext>(captureFileReadGrant(false)),allocationObserver};TaskGroup group(1,4096,{},true);
    auto task=group.spawnWithContext(frameFactory,&context);rejects("E_MEMORY",[&]{(void)group.join(task);});
    try{group.finish();}catch(const Trap &error){require(error.code=="E_MEMORY","prepare allocation failure lost fatal priority");}
    require(group.externalStats().tickets==0,"allocation failure leaked an external ticket");
  }clean();
  {
    FileScope scope(files);RequestScope request;auto grant=captureFileReadGrant(false);PreparedTaskFileRead prepared(grant,"data",false);
    auto raw=prepared.operation()->run(TaskExternalControl{});
    rejects("E_MEMORY",[&]{hostOperation({},[&]{failAllocation=true;(void)prepared.admit(std::move(raw));});});
  }clean();
  {
    auto scope=std::make_unique<FileScope>(files);PreparedTaskFileRead prepared(captureFileReadGrant(false),"data",false);scope.reset();
    TaskExternalResult raw;raw.errorCode="E_TIMEOUT";raw.errorMessage="first fatal before revoked grant";
    rejects("E_TIMEOUT",[&]{(void)prepared.admit(std::move(raw));});
    TaskExternalResult oversized;oversized.bytes.reserve(PreparedTaskFileRead::reservation+1);
    rejects("E_LIMIT",[&]{(void)prepared.admit(std::move(oversized));});
  }clean();
  stickyFatal(files,"E_LIMIT",nullptr);clean();
  stickyFatal(files,"E_TIMEOUT",timeoutObserver);clean();
  stickyFatal(files,"E_MEMORY",allocationObserver);clean();
}
}
int main(){try{tests();std::cout<<"{\"ok\":true,\"cases\":"<<cases<<",\"compiled_request_file_reads\":true,\"public_source_test_separate\":true}\n";return 0;}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
