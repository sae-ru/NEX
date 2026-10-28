#include "nex_host.h"
#include <array>
#include <atomic>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <new>

namespace {
std::atomic<bool> failNextNew{false};
enum class Fault {None,Profile,RequestRegistration};
Fault fault=Fault::None;
struct Slot {const void *pointer=nullptr;int pool=0;};
std::array<Slot,128> slots;
unsigned untracked=0;
void require(bool condition,const char *message){if(!condition){std::fprintf(stderr,"ownership probe: %s\n",message);std::abort();}}
void empty(){
  require(!failNextNew.exchange(false),"allocation fault was not consumed");
  require(fault==Fault::None,"profile fault was not consumed");
  require(untracked==0,"free without a completed allocation");
  for(const auto &slot:slots)require(!slot.pointer,"owned value survived the boundary");
  nex_runtime_finish();
}
}
// Deterministic fault injection at the request registry's next allocation.
void *operator new(std::size_t size){
  if(failNextNew.exchange(false))throw std::bad_alloc();
  if(auto *p=std::malloc(size?size:1))return p;
  throw std::bad_alloc();
}
void operator delete(void *p)noexcept{std::free(p);}
void operator delete(void *p,std::size_t)noexcept{std::free(p);}
extern "C" void nex_profile_enter(const char*,const char*,int64_t,const char*){}
extern "C" void nex_profile_leave(){}
extern "C" void nex_profile_unwind(){}
extern "C" void nex_profile_allocation(const void *pointer,std::size_t,int pool){
  if(pool==0&&fault==Fault::Profile){fault=Fault::None;throw std::bad_alloc();}
  auto available=slots.end();for(auto i=slots.begin();i!=slots.end();++i)if(!i->pointer){available=i;break;}
  require(available!=slots.end(),"fixture allocation limit");*available={pointer,pool};
  if(pool==0&&fault==Fault::RequestRegistration){fault=Fault::None;failNextNew=true;}
}
extern "C" void nex_profile_free(const void *pointer){
  for(auto &slot:slots)if(slot.pointer==pointer){slot.pointer=nullptr;return;}
  ++untracked;
}
extern "C" nexrt::Handle *nex_string_new(const char*,int64_t,int64_t);
extern "C" void nex_assert(int64_t,int64_t);
namespace {
int64_t failApplication(int64_t,const char *const *){
  (void)nex_string_new("caller",6,1);
  fault=Fault::Profile;
  (void)nex_string_new("failed",6,2);
  require(false,"profile allocation did not fail");return 0;
}
int64_t unwindTemporary(int64_t,const char *const *){
  (void)nex_string_new("caller",6,1);
  auto temporary=nexrt::string("C++ temporary");
  nex_assert(0,2);return 0;
}
int64_t leakedReturn(int64_t,const char *const *){(void)nex_string_new("leaked",6,1);return 37;}
int64_t normalReturn(int64_t,const char *const *){auto *value=nex_string_new("normal",6,1);nex_release(value);return 37;}
void requestFailure(Fault selected){
  {
    nexrt::RequestScope scope;
    (void)nex_string_new("caller",6,1);
    fault=selected;bool caught=false;
    try{(void)nex_string_new("failed",6,2);}
    catch(const nexrt::Trap &e){require(e.code=="E_MEMORY","wrong request failure");caught=true;}
    require(caught,"request allocation did not fail");
  }
  empty();
}
}
int main(int argc,char **argv){
  // A single case can be compiled against a historical runtime as an ASan
  // negative control, independently of the rest of this fixture.
  if(argc==2&&std::strcmp(argv[1],"app-profile")==0){
    require(nex_application_run(reinterpret_cast<void*>(failApplication),0,nullptr)==70,"wrong application failure");empty();return 0;
  }
  require(nex_application_run(reinterpret_cast<void*>(normalReturn),0,nullptr)==37,"normal result changed");empty();
  require(nex_application_run(reinterpret_cast<void*>(failApplication),0,nullptr)==70,"wrong application failure");empty();
  require(nex_application_run(reinterpret_cast<void*>(unwindTemporary),0,nullptr)==70,"host temporary did not unwind");empty();
  require(nex_application_run(reinterpret_cast<void*>(leakedReturn),0,nullptr)==70,"normal leak was silently accepted");empty();
  requestFailure(Fault::Profile);requestFailure(Fault::RequestRegistration);
  require(nex_application_run(reinterpret_cast<void*>(normalReturn),0,nullptr)==37,"ownership context was not restored");empty();
  return 0;
}
