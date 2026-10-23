// Trusted test driver: ordinary startup-linked generated DSOs, no dlopen/unload.
#include "nex_task_frame.h"
#include <chrono>
#include <condition_variable>
#include <filesystem>
#include <future>
#include <iostream>
#include <iomanip>
#include <mutex>
#include <sstream>
#include <thread>
#include <dlfcn.h>
#ifdef __APPLE__
#include <mach-o/dyld.h>
#else
#include <link.h>
#endif
using namespace nexrt;
extern "C" const TaskCodeDescriptor *nex_13_shared_middle_4_work__task_code_address();
extern "C" const TaskCodeDescriptor *nex_11_shared_leaf_4_work__task_code_address();
namespace {
std::atomic<unsigned> checks{0};void require(bool value,const char *message){++checks;if(!value)throw std::runtime_error(message);}
template<class F>void until(F test){auto end=std::chrono::steady_clock::now()+std::chrono::seconds(5);while(!test()){require(std::chrono::steady_clock::now()<end,"controlled fixture synchronization timed out");std::this_thread::yield();}}
std::string modulePath(const void *p){Dl_info info{};if(!p||!dladdr(p,&info)||!info.dli_fname)return {};return std::filesystem::weakly_canonical(info.dli_fname).string();}
std::string module(const void *p){return std::filesystem::path(modulePath(p)).filename().string();}
std::string address(const void *p){std::ostringstream out;out<<std::hex<<reinterpret_cast<uintptr_t>(p);return out.str();}
unsigned runtimeMappings(){
 unsigned count=0;
#ifdef __APPLE__
 for(uint32_t i=0;i<_dyld_image_count();++i)if(std::filesystem::path(_dyld_get_image_name(i)).filename().string().starts_with("libnex_runtime_"))++count;
#else
 dl_iterate_phdr([](dl_phdr_info *info,size_t,void *p){if(info->dlpi_name&&std::filesystem::path(info->dlpi_name).filename().string().starts_with("libnex_runtime_"))++*static_cast<unsigned*>(p);return 0;},&count);
#endif
 return count;
}
struct Gate {
 std::mutex mutex;std::condition_variable changed;bool released=false;
 std::atomic<unsigned> entered{0},retired{0},destroyed{0};
 void wait(){std::unique_lock lock(mutex);++entered;changed.notify_all();changed.wait(lock,[&]{return released;});}
 void release(){std::lock_guard lock(mutex);released=true;changed.notify_all();}
};
struct Operation final:TaskExternalOperation {
 std::shared_ptr<Gate> gate;unsigned failure;
 Operation(std::shared_ptr<Gate> g,unsigned f):gate(std::move(g)),failure(f){}
 ~Operation(){++gate->destroyed;}
 TaskExternalResult run(const TaskExternalControl &control)override{
  struct Finally{Gate &gate;~Finally(){++gate.retired;}}finally{*gate};gate->wait();
  if(failure==2)throw std::bad_alloc();
  if(failure==1){TaskExternalResult raw;raw.errorCode="E_LIMIT";raw.errorMessage="controlled late raw limit";return raw;}
  control.checkpoint();return {};
 }
};
TaskGroup *group=nullptr;std::shared_ptr<Gate> gate;const TaskCodeDescriptor *middle=nullptr,*leaf=nullptr;
std::atomic<bool> admitted{false},leafReturned{false},middleReturned{false},otherProgress{false},leafSite{false},middleSite{false};unsigned injectedFailure=0;
void observe(const NativeTaskFrame &frame,int64_t transition){
 if(frame.pendingRequest&&frame.pendingRequest->location.site){auto from=module(frame.pendingRequest->location.site);if(from==module(reinterpret_cast<const void*>(leaf->step)))leafSite=true;if(from==module(reinterpret_cast<const void*>(middle->step)))middleSite=true;}
 if(frame.step==leaf->step&&transition==3&&frame.pendingRequest&&frame.pendingRequest->operation==TaskRequestKind::Yield&&!admitted.exchange(true))
   (void)group->submitExternal(std::make_shared<Operation>(gate,injectedFailure),8);
 if(frame.step==leaf->step&&transition==0)leafReturned=true;
 if(frame.step==middle->step&&transition==0)middleReturned=true;
}
TaskBody source(TaskGroup &owner,Value,Value){return executeTaskFrame(owner,NativeTaskFrame(*middle,{},Value{}),observe);}
TaskBody other(TaskGroup &,Value,Value){otherProgress=true;co_return Value(int64_t(77));}
template<class F>std::string errorCode(F action){try{auto value=action();require(value.tag==Value::Integer&&value.scalar==42,"generated DSO result differed");return {};}catch(const Trap &e){return e.code;}catch(const DataError &e){return e.code;}catch(const std::bad_alloc &){return "E_MEMORY";}}
void scenario(unsigned which){
 gate=std::make_shared<Gate>();admitted=false;leafReturned=false;middleReturned=false;otherProgress=false;injectedFailure=which==2?1:which==3?2:0;
 {
  RequestScope request(1000000,5000);TaskGroup owner(1,32,{1,4,64,16},true);group=&owner;std::future<bool> monitor;std::atomic<bool> joinStarted{false};std::mutex joinedMutex;std::condition_variable joinedChanged;bool joinReturned=false;
  try{
   auto root=owner.spawn(source);until([]{return gate->entered==1&&leafReturned.load();});
   require(gate->retired==0&&gate->destroyed==0,"operation retired before physical gate");
   auto stats=owner.externalStats();require(stats.running==1&&stats.tickets==1&&stats.reservedBytes==8,"inflight quota or ticket released early");
   require(!middleReturned,"parent source crossed child physical fence");
   auto sibling=owner.spawn(other);require(owner.join(sibling).scalar==77&&otherProgress,"held IO blocked the single task executor");
   if(which==3)owner.failFileRead(std::make_exception_ptr(Trap("E_TIMEOUT","first selected controlled fatal",0)));
   else if(which)require(owner.cancel(root),"root cancellation was not accepted");
   require(!middleReturned&&owner.externalStats().tickets==1&&gate->retired==0,"cancellation released source owner before physical retirement");
   monitor=std::async(std::launch::async,[&]{
     until([&]{return joinStarted.load();});std::unique_lock lock(joinedMutex);
     const bool early=joinedChanged.wait_for(lock,std::chrono::milliseconds(20),[&]{return joinReturned;});
     lock.unlock();gate->release();return early;
   });
   // join must stay on its captured coordinator thread. Only the raw physical
   // barrier monitor runs elsewhere; it has no TaskGroup/source authority.
   joinStarted=true;auto code=errorCode([&]{return owner.join(root);});
   {std::lock_guard lock(joinedMutex);joinReturned=true;}joinedChanged.notify_all();
   require(!monitor.get(),"join crossed a physically held completion");
   auto expected=which==0?"":which==1?"E_CANCELLED":which==2?"E_LIMIT":"E_TIMEOUT";
   require(code==expected,("wrong physical completion priority: "+code).c_str());
   try{owner.finish();}catch(const Trap &e){require(which&&e.code==expected,"finish changed first fatal");}catch(const DataError &e){require(which&&e.code==expected,"finish changed raw fatal");}
   require(gate->retired==1&&gate->destroyed==1,"raw operation finally/destructor did not retire");
   stats=owner.externalStats();require(stats.tickets==0&&stats.reservedBytes==0&&stats.running==0,"physical completion quota survived drain");
  }catch(...){gate->release();if(monitor.valid()){joinStarted=true;monitor.wait();}throw;}
 }
 group=nullptr;gate.reset();require(!inRequestScope()&&liveObjects==0,"owned source ledger survived mapped DSO drain");nex_runtime_finish();
}
}
int main(int argc,char **argv){try{
 require(argc==4,"expected middle/leaf/runtime image basenames");middle=nex_13_shared_middle_4_work__task_code_address();leaf=nex_11_shared_leaf_4_work__task_code_address();
 require(middle&&leaf&&middle->abi==taskCodeABI&&leaf->abi==taskCodeABI,"actual generated ABI3 accessors unavailable");
 require(module(reinterpret_cast<const void*>(middle->step))==argv[1]&&module(reinterpret_cast<const void*>(leaf->step))==argv[2],"descriptor points outside the pinned provider image");
 auto *runtime=dlsym(RTLD_DEFAULT,"nex_release");require(runtime&&modulePath(runtime)==std::filesystem::weakly_canonical(argv[3]).string(),"runtime bridge maps to the wrong image");require(runtime==reinterpret_cast<void*>(&nex_release),"driver/runtime bridge identity differs");require(runtimeMappings()==1,"process loaded more than one NEX runtime mapping");
 for(unsigned i=0;i<4;++i)scenario(i);
 require(leafSite&&middleSite,"generated suspended source sites were not mapped to both providers");
 std::cout<<"{\"ok\":true,\"cases\":4,\"checks\":"<<checks.load()<<",\"execution_abi\":3,\"runtime_mappings\":"<<runtimeMappings()<<",\"physical_barrier_cases\":4,\"single_task_worker_progress\":true,\"first_fatal_retained\":true,\"provider_site_lifetime\":true,\"live_objects\":"<<liveObjects.load()<<",\"runtime_bridge_address\":\""<<address(runtime)<<"\",\"runtime_image_path\":"<<std::quoted(modulePath(runtime))<<",\"registry_address\":\""<<address(&liveObjects)<<"\",\"source_regular_file_retirement_claim\":false,\"arbitrary_host_source_bridge\":false}\n";return 0;
 }catch(const std::exception &e){std::cerr<<"shared provider lifetime: "<<e.what()<<'\n';return 1;}}
