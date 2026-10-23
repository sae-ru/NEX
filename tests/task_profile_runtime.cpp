#include "nex_task_application.h"
#include <array>
#include <atomic>
#include <filesystem>
#include <fstream>
#include <future>
#include <iostream>
#include <regex>
#include <sys/wait.h>
#include <unistd.h>
using namespace nexrt;
extern "C" const char *nex_profile_build_info(){return "{\"schema\":\"nex.profile-build/1\",\"toolchain\":\"probe\",\"language\":\"0.20\",\"revision\":\"probe\",\"build_key\":\"probe\",\"compiler_build\":\"probe\",\"source_hash\":\"probe\",\"task_limits\":{\"steps\":1000000,\"timeout_ms\":5000,\"workers\":2}}";}
namespace {
size_t checks=0;
void require(bool value,const char *message){++checks;if(!value)throw std::runtime_error(message);}
constexpr TaskProfileCodeSite sites[]={
  {"main","profile.nex","probe",1},{"child","profile.nex","probe",2},{"pure","profile.nex","probe",3},
  {"trap","profile.nex","probe",4},{"throwing_helper","profile.nex","probe",5},{"channel_owner","profile.nex","probe",6},
  {"channel_sender","profile.nex","probe",7},{"external","profile.nex","probe",8}};
std::array<int64_t,2> kinds{3,0};
TaskCodeDescriptor childCode;
void helper(){nex_profile_enter("pure","profile.nex",3,"probe");auto handle=makeHandle(Value(string("helper🧠")));nex_release(handle);nex_profile_leave();}
int64_t childStep(void *pointer){auto &frame=*static_cast<NativeTaskFrame*>(pointer);if(frame.pc++<2)return 1;nex_task_frame_return_i64(pointer,40,0);return 0;}
int64_t mainStep(void *pointer){
  auto &frame=*static_cast<NativeTaskFrame*>(pointer);
  if(frame.pc==0){helper();auto value=makeHandle(Value(string("parked🧠")));nex_task_frame_put_heap(pointer,0,value);nex_release(value);frame.pc=1;return 1;}
  if(frame.pc==1){auto args=makeHandle(Value(std::make_shared<Data>(Data::List)));nex_task_frame_call_at(pointer,&childCode,nullptr,args,1,1,nullptr);nex_release(args);frame.pc=2;return 2;}
  helper();nex_task_frame_return_i64(pointer,frame.read(1,0).scalar+2,0);return 0;
}
int64_t trapStep(void *pointer){
  if(nex_task_frame_pc(pointer)==0){nex_task_frame_set_pc(pointer,1);return 1;}
  nex_profile_enter("throwing_helper","profile.nex",5,"probe");
  (void)makeHandle(Value(string("unwind temporary🧠")));throw Trap("E_ITEM","controlled source trap",4);
}
std::atomic<bool> senderEntered{false};
TaskBody sender(TaskGroup &group,TaskGroup::Channel channel){
  auto call=taskProfileCollector()?taskProfileCollector()->invocation(6):TaskProfileInvocation{};
  senderEntered=true;co_await group.send(channel,Value(string("blocked sender")));call.complete();co_return Value{};
}
TaskBody senderFactory(TaskGroup &group,Value,Value,const void *context){return sender(group,*static_cast<const TaskGroup::Channel*>(context));}
TaskBody channelOwner(TaskGroup &group,Value,Value){
  auto call=taskProfileCollector()?taskProfileCollector()->invocation(5):TaskProfileInvocation{};
  auto scope=group.openScope(1);auto channel=group.channel(scope,1);
  co_await group.send(channel,Value(string("buffer released by scope cancellation")));
  group.spawnWithContext(scope,senderFactory,&channel);
  while(!senderEntered)co_await group.yield();
  co_await group.leaveScope(scope,true);call.complete();co_return Value{};
}
struct Gate {std::promise<void> entered,release;std::shared_future<void> released=release.get_future().share();std::atomic<bool> retired{false};};
struct Held final:TaskExternalOperation {std::shared_ptr<Gate> gate;explicit Held(std::shared_ptr<Gate> gate):gate(std::move(gate)){}TaskExternalResult run(const TaskExternalControl &)override{gate->entered.set_value();gate->released.wait();gate->retired=true;return {};}};
TaskBody external(TaskGroup &group,std::shared_ptr<Gate> gate){auto call=taskProfileCollector()?taskProfileCollector()->invocation(7):TaskProfileInvocation{};auto ticket=group.submitExternal(std::make_shared<Held>(gate),16);(void)co_await group.awaitExternal(ticket);call.complete();co_return Value{};}
TaskBody externalFactory(TaskGroup &group,Value,Value,const void *context){return external(group,*static_cast<const std::shared_ptr<Gate>*>(context));}
void clean(){require(!inRequestScope()&&liveObjects==0,"source ownership survived application/group destruction");nex_runtime_finish();}
void exercise(bool enabled,bool truncated=false,bool overflow=false){
  nex_task_profile_prepare(sites,std::size(sites));require(bool(taskProfileCollector())==enabled,"dormant prepare created a collector");
  childCode={childStep,nullptr,nullptr,nullptr,&sites[1],taskCodeABI,0,0,0,0,taskCodeDeclaredTask};
  TaskCodeDescriptor code{mainStep,kinds.data(),nullptr,nullptr,&sites[0],taskCodeABI,2,0,0,0,taskCodeDeclaredTask};
  require(executeTaskApplication(code,{1000000,5000,2},{})==42,"resume/direct call changed source result");clean();
  code.step=trapStep;code.profileSite=&sites[3];bool trapped=false;
  try{executeTaskApplication(code,{1000000,5000,2},{});}catch(const Trap &error){trapped=error.code=="E_ITEM";}require(trapped,"profiling masked source trap");clean();
  {RequestScope request;TaskGroup group(1);auto task=group.spawn(channelOwner);(void)group.join(task);group.finish();}clean();
  {RequestScope request;TaskGroup group(1);auto gate=std::make_shared<Gate>();auto entered=gate->entered.get_future();group.spawnWithContext(externalFactory,&gate);require(entered.wait_for(std::chrono::seconds(2))==std::future_status::ready,"physical worker did not start");group.cancel();require(!gate->retired,"cancel skipped physical lifetime");gate->release.set_value();try{group.finish();}catch(const Trap &error){require(error.code=="E_CANCELLED","profile changed cancel failure");}require(gate->retired&&group.externalStats().tickets==0,"physical drain did not complete");}clean();
  // Independent allocator threads repeatedly reuse addresses, including frees
  // with no active logical source. The source/Data ledger remains exact.
  std::array<std::thread,4> workers;
  for(auto &worker:workers)worker=std::thread([]{for(size_t i=0;i<3000;++i){auto value=string("concurrent reused address");auto handle=makeHandle(Value(value));nex_release(handle);}});
  for(auto &worker:workers)worker.join();clean();
  if(enabled){auto snapshot=taskProfileCollector()->snapshot();require(snapshot.drops.incomplete==truncated,"unexpected collector completeness");require(snapshot.functions[0].calls==1&&snapshot.functions[0].completed==1,"root counted per resume");require(snapshot.functions[1].calls==1&&snapshot.functions[1].completed==1,"child counted per resume");require(snapshot.functions[2].calls==2&&snapshot.functions[2].completed==2,"pure helper routing count differs");require(snapshot.functions[3].calls==1&&snapshot.functions[3].aborted==1,"trapped retained frame did not abort once");require(snapshot.functions[4].calls==1&&snapshot.functions[4].aborted==1,"transient helper unwind failed");for(const auto &task:snapshot.tasks)require(task.terminal&&!task.activeInvocations,"terminal published before logical destruction");require(snapshot.functions[0].inclusiveCpuNs>=snapshot.functions[0].selfCpuNs,"inclusive CPU less than self");}
  if(overflow){int first=0,second=0;nex_profile_allocation(&first,std::numeric_limits<size_t>::max(),1);nex_profile_allocation(&second,1,1);nex_profile_free(&first);nex_profile_free(&second);}
}
uint64_t field(const std::string &text,const std::string &key){std::smatch match;require(std::regex_search(text,match,std::regex("\\\""+key+"\\\":([0-9]+)")),"missing raw numeric field");return std::stoull(match[1]);}
int64_t tracyEntry(int64_t,const char *const *){nex_task_profile_prepare(sites,std::size(sites));throw std::runtime_error("Tracy rejection allowed source entry");}
void parent(const char *self){
  char directory[]="/tmp/nex-task-profile-XXXXXX";require(::mkdtemp(directory),"mkdtemp failed");auto report=std::filesystem::path(directory)/"profile.json";
  auto run=[&](const char *mode){auto pid=::fork();require(pid>=0,"fork failed");if(!pid){::unsetenv("NEX_TRACY");::setenv("NEX_PROFILE_EVENTS",std::string(mode)=="truncated"?"0":"100000",1);if(std::string(mode)!="dormant")::setenv("NEX_PROFILE_OUTPUT",report.c_str(),1);else ::unsetenv("NEX_PROFILE_OUTPUT");::execl(self,self,mode,nullptr);::_exit(127);}int status=0;require(::waitpid(pid,&status,0)==pid&&WIFEXITED(status)&&WEXITSTATUS(status)==0,"runtime profile child failed");};
  run("tracy");require(!std::filesystem::exists(report),"rejected task Tracy initialized a synchronous collector while unwinding");run("dormant");run("profile");
  std::ifstream input(report);std::string raw((std::istreambuf_iterator<char>(input)),{});
  require(raw.find("\"schema\":\"nex.profile-runtime/2\"")!=std::string::npos,"task schema2 absent");require(raw.find("\"incomplete\":false")!=std::string::npos,"valid task report incomplete");
  for(const char *name:{"dropped_events","dropped_functions","dropped_frames","dropped_allocations","untracked_frees","invalid_transitions","clock_failures"})require(field(raw,name)==0,"valid runtime dropped profiling data");
  auto memory=raw.substr(raw.find("\"memory\":["));std::regex pool("\\\"allocations\\\":([0-9]+),\\\"frees\\\":([0-9]+),\\\"live\\\":([0-9]+),\\\"peak_live\\\":([0-9]+),\\\"live_shallow_bytes\\\":([0-9]+)");size_t pools=0;
  for(std::sregex_iterator it(memory.begin(),memory.end(),pool),end;it!=end;++it){++pools;require((*it)[1]==(*it)[2]&&(*it)[3]=="0"&&(*it)[5]=="0","atomic managed pool did not balance");}require(pools==2,"managed memory pools absent");
  run("truncated");{std::ifstream input(report);raw.assign(std::istreambuf_iterator<char>(input),{});}require(raw.find("\"aggregates\":true,\"timeline\":false,\"memory\":true,\"cpu\":true,\"elapsed\":true,\"lifetime\":true")!=std::string::npos,"event-only loss invalidated exact aggregates/clocks/memory");require(field(raw,"dropped_events")>0,"timeline cap did not report drops");
  run("overflow");{std::ifstream input(report);raw.assign(std::istreambuf_iterator<char>(input),{});}require(raw.find("\"incomplete\":true")!=std::string::npos&&raw.find("\"memory\":false")!=std::string::npos,"late memory overflow emitted a clean report");require(field(raw,"counter_overflows")>0&&field(raw,"serialization_overflows")>0,"memory counter/JSON overflow was not explicit");
  std::filesystem::remove_all(directory);
}
}
int main(int argc,char **argv){try{if(argc==1)parent(argv[0]);else if(std::string(argv[1])=="tracy"){::setenv("NEX_TRACY","1",1);bool rejected=false;try{nex_task_profile_prepare(sites,std::size(sites));}catch(const Trap &error){rejected=error.code=="E_TASK_PROFILE";}require(rejected&&!taskProfileCollector(),"task Tracy reached collector/worker startup");require(nex_application_run(reinterpret_cast<void*>(tracyEntry),0,nullptr)==70&&!taskProfileCollector(),"application-wrapper cleanup masked task Tracy rejection");}else exercise(std::string(argv[1])!="dormant",std::string(argv[1])=="truncated",std::string(argv[1])=="overflow");std::cout<<"task profile runtime PASS "<<checks<<" checks\n";return 0;}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
