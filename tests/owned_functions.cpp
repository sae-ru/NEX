#include "nex_host.h"
#include "nex_parallel.h"
#include "nex_files.h"
#include <array>
#include <atomic>
#include <barrier>
#include <cstdio>
#include <cstdlib>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <new>
#include <random>
#include <thread>

extern "C" nexrt::Handle *nex_string_new(const char*,int64_t,int64_t);
extern "C" void nex_assert(int64_t,int64_t);
namespace {
using namespace nexrt;
void require(bool value,const char *message){if(!value){std::fprintf(stderr,"owned function probe: %s\n",message);std::abort();}}
enum class Fault {None,Profile,Registration};
thread_local bool failNextNew=false;
thread_local Fault fault=Fault::None;
std::mutex allocationMutex;
struct Slot {const void *pointer=nullptr;int pool=0;};
std::array<Slot,2048> slots;
size_t allocated[2]{},freed[2]{};
template<class F> void error(const char *code,F action){bool caught=false;try{action();}catch(const Trap &failure){require(failure.code==code,"wrong checked error");caught=true;}require(caught,"checked error missing");}
Handle *text(const std::string &value){return nex_string_new(value.data(),int64_t(value.size()),1);}
void empty(){
  require(!inRequestScope(),"request survived scope");require(!failNextNew&&fault==Fault::None,"unconsumed allocation fault");
  require(liveObjects==0,"managed object survived scope");
  {std::lock_guard lock(allocationMutex);for(auto &slot:slots)require(!slot.pointer,"profiled value survived scope");}
  nex_runtime_finish();
}
int64_t nestedReturn(int64_t,const char *const *){
  auto *caller=text("caller");auto outer=nex_owned_enter();(void)text("partial argument");
  auto partial=std::make_shared<Data>(Data::List);partial->values.emplace_back(string("partial constructor"));
  (void)makeHandle(Value(std::move(partial)));
  auto inner=nex_owned_enter();(void)text("inner temporary");auto *result=text("Я🧠:returned");
  nex_owned_leave(inner,result);require(readHandle(result).object->text=="Я🧠:returned","inner return lost its data");
  nex_owned_leave(outer,result);require(readHandle(caller).object->text=="caller","callee deleted caller value");
  require(readHandle(result).object->text=="Я🧠:returned","outer return lost its data");
  nex_release(caller);nex_release(result);return 37;
}
int64_t checkedFailure(int64_t,const char *const *){
  (void)text("caller");(void)nex_owned_enter();(void)text("outer");(void)nex_owned_enter();(void)text("inner");nex_assert(0,71);return 0;
}
int64_t missingLeave(int64_t,const char *const *){(void)nex_owned_enter();return 0;}
int64_t callerLeak(int64_t,const char *const *){(void)text("caller leak");auto token=nex_owned_enter();(void)text("callee temporary");nex_owned_leave(token,nullptr);return 0;}
int64_t nestedRequest(int64_t,const char *const *){
  auto token=nex_owned_enter();auto *parent=text("parent");
  {
    RequestScope request;error("E_CONTEXT",[&]{nex_owned_leave(token,nullptr);});
    auto child=nex_owned_enter();auto *kept=text("request-owned result");nex_owned_leave(child,kept);
    require(readHandle(kept).object->text=="request-owned result","request return was not retained");
    (void)nex_owned_enter();(void)text("request temporary");
  }
  require(readHandle(parent).object->text=="parent","request cleanup deleted enclosing function");
  nex_owned_leave(token,parent);nex_release(parent);return 37;
}
struct Fixture {
  std::filesystem::path root;
  Fixture(){for(int attempt=0;attempt<64;++attempt){auto path=std::filesystem::temp_directory_path()/("nex-owned-functions-"+std::to_string(std::random_device{}()));if(std::filesystem::create_directory(path)){root=std::move(path);break;}}require(!root.empty(),"temporary directory missing");std::ofstream(root/"input")<<"content";}
  ~Fixture(){std::error_code ignored;std::filesystem::remove_all(root,ignored);}
};
Value worker(const Value &item,const Value &environment){
  auto token=nex_owned_enter();(void)text("worker temporary");
  if(environment.scalar&&item.scalar==0)throw Trap("E_WORKER","expected worker failure",72);
  auto *result=text("worker:"+std::to_string(item.scalar));nex_owned_leave(token,result);
  auto value=readHandle(result);nex_release(result);return value;
}
}
void *operator new(size_t size){if(failNextNew){failNextNew=false;throw std::bad_alloc();}if(auto *p=std::malloc(size?size:1))return p;throw std::bad_alloc();}
void operator delete(void *p)noexcept{std::free(p);}
void operator delete(void *p,size_t)noexcept{std::free(p);}
extern "C" void nex_profile_enter(const char*,const char*,int64_t,const char*){}
extern "C" void nex_profile_leave(){}
extern "C" void nex_profile_unwind(){}
extern "C" void nex_profile_allocation(const void *p,size_t,int pool){
  if(pool==0&&fault==Fault::Profile){fault=Fault::None;throw std::bad_alloc();}
  std::lock_guard lock(allocationMutex);auto found=slots.end();for(auto i=slots.begin();i!=slots.end();++i)if(!i->pointer){found=i;break;}
  require(found!=slots.end()&&pool>=0&&pool<2,"allocation accounting limit");*found={p,pool};++allocated[pool];
  if(pool==0&&fault==Fault::Registration){fault=Fault::None;failNextNew=true;}
}
extern "C" void nex_profile_free(const void *p){std::lock_guard lock(allocationMutex);for(auto &slot:slots)if(slot.pointer==p){++freed[slot.pool];slot.pointer=nullptr;return;}require(false,"free without completed allocation");}
int main(int argc,char **){
  if(argc>1){(void)nex_owned_enter();return 99;}
  unsigned cases=0;auto run=[&](const auto &body){body();empty();++cases;};
  // First entry must allocate a frame; failed entry leaves caller ownership intact.
  run([]{RequestScope scope;auto *caller=text("caller");failNextNew=true;error("E_MEMORY",[]{(void)nex_owned_enter();});require(readHandle(caller).object->text=="caller","failed entry deleted caller");scope.poll();});
  run([]{require(nex_application_run(reinterpret_cast<void*>(nestedReturn),0,nullptr)==37,"application return changed");});
  run([]{RequestScope scope;auto *parent=text("parent");auto token=nex_owned_enter();(void)text("discarded");nex_owned_leave(token,parent);require(readHandle(parent).object->text=="parent","borrowed keep was deleted");nex_release(parent);});
  run([]{RequestScope scope;auto token=nex_owned_enter();auto *first=text("first"),*middle=text("middle"),*last=text("last");nex_release(middle);nex_release(first);nex_owned_leave(token,last);require(readHandle(last).object->text=="last","intrusive unlink damaged kept value");nex_release(last);});
  run([]{RequestScope scope;auto outer=nex_owned_enter(),inner=nex_owned_enter();(void)text("owned");error("E_CONTEXT",[&]{nex_owned_leave(outer,nullptr);});nex_owned_leave(inner,nullptr);nex_owned_leave(outer,nullptr);auto fresh=nex_owned_enter();require(fresh!=outer&&fresh!=inner,"scope identity was reused");error("E_CONTEXT",[&]{nex_owned_leave(inner,nullptr);});nex_owned_leave(fresh,nullptr);});
  run([]{RequestScope scope;const char *zero="0000000000000000000000000000000000000000000000000000000000000000";const char *one="1111111111111111111111111111111111111111111111111111111111111111";NativeFunctionSite fn{zero,zero,zero};NativeSite site{&fn,one,"function_scope",1,2};auto token=nex_owned_enter_at(&site);bool caught=false;try{nex_owned_leave_at(token+1,nullptr,&site);}catch(const LocatedTrap &failure){require(failure.code=="E_CONTEXT"&&failure.source.find(one)!=std::string::npos,"scope failure lost its source location");caught=true;}require(caught,"located scope failure missing");nex_owned_leave_at(token,nullptr,&site);});
  run([]{require(nex_application_run(reinterpret_cast<void*>(nestedRequest),0,nullptr)==37,"request/function boundary changed");});
  run([]{RequestScope scope;auto token=nex_owned_enter();auto *parent=text("parent");auto nested=nex_owned_enter();auto *failure=makeHandle(nexrt::failure("E_USER","Я🧠:message"));(void)text("partial call argument");nex_owned_leave(nested,failure);require(!isSuccess(readHandle(failure))&&readHandle(failure).object->text=="E_USER","error data changed");nex_owned_leave(token,failure);require(readHandle(failure).object->values[0].object->text=="Я🧠:message","error text changed");(void)parent;nex_release(failure);});
  for(auto selected:{Fault::Profile,Fault::Registration})run([&]{RequestScope scope;auto token=nex_owned_enter();auto *parent=text("parent");fault=selected;error("E_MEMORY",[]{(void)text("failed allocation");});require(readHandle(parent).object->text=="parent","allocation failure changed existing data");nex_owned_leave(token,nullptr);});
  run([]{require(nex_application_run(reinterpret_cast<void*>(checkedFailure),0,nullptr)==70,"checked failure exit changed");require(nex_application_run(reinterpret_cast<void*>(nestedReturn),0,nullptr)==37,"function state survived checked failure");});
  run([]{try{RequestScope request;(void)nex_owned_enter();(void)text("host exception");throw std::runtime_error("host");}catch(const std::runtime_error&){};});
  run([]{require(nex_application_run(reinterpret_cast<void*>(missingLeave),0,nullptr)==70,"unbalanced normal scope was silently accepted");});
  run([]{require(nex_application_run(reinterpret_cast<void*>(callerLeak),0,nullptr)==70,"function cleanup hid a caller leak");});
  run([]{RequestScope scope;std::array<int64_t,4096> tokens;for(auto &token:tokens)token=nex_owned_enter();error("E_LIMIT",[]{(void)nex_owned_enter();});for(auto i=tokens.rbegin();i!=tokens.rend();++i)nex_owned_leave(*i,nullptr);scope.poll();});
  run([]{{RequestScope scope;for(int i=0;i<32;++i){(void)nex_owned_enter();(void)text("unwind");}failNextNew=true;}require(failNextNew,"unwind allocated memory");failNextNew=false;});
  run([]{Fixture fixture;TextFiles files(fixture.root.string(),false);auto domain=files.resourceScope(1);RequestScope scope;auto token=nex_owned_enter();(void)makeHandle(Value(fileValue(files.openIn(domain,"input",FileMode::Read))));require(domain.used()==1,"file quota not occupied");nex_owned_leave(token,nullptr);require(domain.used()==0,"discarded file resource survived return");token=nex_owned_enter();auto *kept=makeHandle(Value(fileValue(files.openIn(domain,"input",FileMode::Read))));nex_owned_leave(token,kept);require(domain.used()==1&&fileResource(readHandle(kept).object).isOpen(),"returned file resource was closed");token=nex_owned_enter();(void)makeHandle(readHandle(kept));nex_owned_leave(token,nullptr);require(domain.used()==1,"dropping a file alias closed its parent");nex_release(kept);require(domain.used()==0,"returned file resource leaked");});
  run([]{RequestScope scope;auto values=std::make_shared<Data>(Data::List);for(int i=0;i<8;++i)values->values.emplace_back(i);error("E_WORKER",[&]{(void)parallelValues(Value(values),Value(1),2,worker);});auto output=parallelValues(Value(values),Value(0),2,worker);require(output.object->values.size()==8&&output.object->values[7].object->text=="worker:7","worker request cleanup left stale function ownership");scope.poll();});
  run([]{RequestScope scope;auto token=nex_owned_enter();auto *parent=text("parent");std::barrier barrier(5);std::atomic<unsigned> passed{0};std::array<std::thread,4> workers;for(auto &thread:workers)thread=std::thread([&]{RequestScope request;auto own=nex_owned_enter();(void)text("thread");barrier.arrive_and_wait();error("E_CONTEXT",[&]{nex_owned_leave(token,nullptr);});nex_owned_leave(own,nullptr);++passed;});barrier.arrive_and_wait();for(auto &thread:workers)thread.join();require(passed==4&&readHandle(parent).object->text=="parent","thread scope tokens crossed ownership");nex_owned_leave(token,nullptr);});
  require(allocated[0]==freed[0]&&allocated[1]==freed[1],"managed pool totals differ");
  std::printf("{\"ok\":true,\"cases\":%u,\"handle_allocations\":%zu,\"object_allocations\":%zu,\"live_handles\":0,\"live_objects\":0}\n",cases,allocated[0],allocated[1]);
}
