#include "nex_task_application.h"
#include <array>
#include <atomic>
#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <thread>
#include <vector>

namespace {
void require(bool value){if(!value)std::abort();}
void clean(){require(!nexrt::inRequestScope());require(nexrt::liveObjects==0);nex_runtime_finish();}
std::atomic<unsigned> entered{0},active{0},maximumActive{0};
unsigned expectedWorkers=1;
int64_t yielded(void *pointer){
  ++entered;
  if(!nex_task_frame_pc(pointer)){
    auto *value=nexrt::makeHandle(nexrt::Value(nexrt::string("retained🧠")));
    nex_task_frame_put_heap(pointer,0,value);nex_release(value);
    nex_task_frame_set_pc(pointer,1);return 1;
  }
  nex_task_frame_return_i64(pointer,42,0);return 0;
}
int64_t expired(void *pointer){
  (void)nexrt::makeHandle(nexrt::Value(nexrt::string("temporary🧠")));
  std::this_thread::sleep_for(std::chrono::milliseconds(10));
  nex_poll(7);nex_task_frame_return_i64(pointer,42,0);return 0;
}
nexrt::TaskCodeDescriptor childCode{},scopeCode{};
nexrt::Value closure(const nexrt::TaskCodeDescriptor &code){
  auto data=std::make_shared<nexrt::Data>(nexrt::Data::Closure);data->taskCode=&code;return nexrt::Value(std::move(data));
}
int64_t child(void *pointer){
  auto count=++active;auto maximum=maximumActive.load();
  while(maximum<count&&!maximumActive.compare_exchange_weak(maximum,count)){}
  auto deadline=std::chrono::steady_clock::now()+std::chrono::milliseconds(1000);
  while(maximumActive<expectedWorkers&&std::chrono::steady_clock::now()<deadline)std::this_thread::yield();
  --active;nex_task_frame_return_i64(pointer,21,0);return 0;
}
int64_t request(nexrt::NativeTaskFrame &frame,nexrt::TaskRequestKind operation,std::vector<nexrt::Value> arguments,int64_t destination,int64_t kind){
  frame.pendingRequest=nexrt::NativeTaskRequest{operation,std::move(arguments),destination,kind,{}};++frame.pc;return 3;
}
int64_t scope(void *pointer){
  auto &frame=*static_cast<nexrt::NativeTaskFrame*>(pointer);
  switch(frame.pc){
  case 0:case 1:return request(frame,nexrt::TaskRequestKind::Spawn,{frame.read(0,3),closure(childCode)},frame.pc+1,3);
  case 2:return request(frame,nexrt::TaskRequestKind::Wait,{frame.read(1,3)},3,0);
  case 3:return request(frame,nexrt::TaskRequestKind::Wait,{frame.read(2,3)},4,0);
  default:nex_task_frame_return_i64(pointer,frame.read(3,0).scalar+frame.read(4,0).scalar,0);return 0;
  }
}
int64_t root(void *pointer){
  auto &frame=*static_cast<nexrt::NativeTaskFrame*>(pointer);
  if(!frame.pc)return request(frame,nexrt::TaskRequestKind::WithTasks,{nexrt::Value(int64_t(2)),closure(scopeCode)},0,0);
  nex_task_frame_return_i64(pointer,frame.read(0,0).scalar,0);return 0;
}
const nexrt::TaskCodeDescriptor *selected=nullptr;
nexrt::TaskExecutionLimits ceilings;
std::vector<const char*> arguments;
const char *expected=nullptr;
int64_t application(int64_t,const char *const *){
  bool caught=false;
  try{nex_task_application_execute_limits(selected,arguments.size(),arguments.data(),ceilings.steps,ceilings.timeoutMs,ceilings.workers);}
  catch(const nexrt::Trap &trap){require(trap.code==expected);caught=true;}
  require(caught);return 0;
}
void rejects(const char *code,const nexrt::TaskCodeDescriptor &descriptor,nexrt::TaskExecutionLimits limits,std::initializer_list<const char*> argv){
  selected=&descriptor;ceilings=limits;arguments=argv;expected=code;
  require(nex_application_run(reinterpret_cast<void*>(application),0,nullptr)==0);clean();
}
void rejectsArguments(std::initializer_list<const char*> argv){
  std::vector<const char*> input(argv);bool rejected=false;
  try{(void)nexrt::parseTaskExecutionArguments({},int(input.size()),input.data());}
  catch(const nexrt::DataError &error){require(error.code=="E_OPTION");rejected=true;}
  require(rejected);
}
}
int main(){
  using namespace nexrt;
  require(validTaskExecutionLimits({}));
  require(parseTaskLimitDecimal("9007199254740991",maximumTaskExecutionSteps)==maximumTaskExecutionSteps);
  for(auto text:{"","0","-1","+1"," 1","1 ","1.0","1x","9007199254740992","184467440737095516160"})
    require(!parseTaskLimitDecimal(text,maximumTaskExecutionSteps));
  require(parseTaskLimitDecimal("0",0,0)==0);require(!parseTaskLimitDecimal("1",0));
  require(!validTaskExecutionLimits({0,5000,16}));require(!validTaskExecutionLimits({1,3600001,1}));require(!validTaskExecutionLimits({1,1,17}));
  for(auto input:{std::initializer_list<const char*>{"app","--nex-task-steps"},
      {"app","--nex-task-steps","1","--nex-task-steps","1"},
      {"app","--nex-task-timeout-ms","5001"},
      {"app","--nex-task-workers","17"},
      {"app","--nex-task-workers","-1"},
      {"app","--nex-task-steps=1"},
      {"app","--nex-task-stepp","1"}})rejectsArguments(input);
  const char *valid[]={"app","unrelated","--nex-task-steps","200","--nex-task-timeout-ms","1000","--nex-task-workers","1"};
  require(parseTaskExecutionArguments({},8,valid)==TaskExecutionLimits{200,1000,1});
  std::array<int64_t,1> retainedKinds{3};
  TaskCodeDescriptor descriptor{yielded,retainedKinds.data(),nullptr,nullptr,nullptr,taskCodeABI,1,0,0,0};
  require(nex_task_application_execute_limits(&descriptor,8,valid,1000,2000,2)==42);clean();
  entered=0;rejects("E_OPTION",descriptor,{100,1000,2},{"app","--nex-task-workers","3"});require(entered==0);
  rejects("E_LIMIT",descriptor,{1,1000,1},{"app"});require(entered<=1);
  descriptor.step=expired;rejects("E_TIMEOUT",descriptor,{100,1,1},{"app"});
  // Real concurrent children prove that the physical executor consumes the
  // configured pool size. Scope permits two; one worker must still serialize.
  std::array<int64_t,1> rootKinds{0};std::array<int64_t,5> scopeKinds{3,3,3,0,0};int64_t parameter=0;
  childCode={child,nullptr,nullptr,nullptr,nullptr,taskCodeABI,0,0,0,0};
  scopeCode={scope,scopeKinds.data(),&parameter,nullptr,nullptr,taskCodeABI,5,1,0,0};
  descriptor={root,rootKinds.data(),nullptr,nullptr,nullptr,taskCodeABI,1,0,0,0};
  for(unsigned workers:{1u,2u}){
    maximumActive=0;expectedWorkers=workers;
    require(nex_task_application_execute_limits(&descriptor,1,valid,10000,3000,workers)==42);
    require(active==0&&maximumActive==workers);clean();
  }
  std::puts("task limits runtime: decimal/argv validation, ceilings, shared step/deadline cleanup and actual worker caps passed");
}
