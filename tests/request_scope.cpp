#include "nex_host.h"
#include <cassert>
#include <thread>
#include <vector>
extern "C" nexrt::Handle *nex_5_scope_6_handle(nexrt::Handle*);

void request(int64_t mode,const char *expected){
  bool trapped=false;
  {
    nexrt::RequestScope scope(30,10000);
    auto input=std::make_shared<nexrt::Data>(nexrt::Data::Record);input->text="scope::Input";
    input->names={"mode","text"};input->values={nexrt::Value(mode),nexrt::Value(nexrt::string("owned input"))};
    auto parameter=nexrt::makeHandle(nexrt::Value(input));
    try{
      auto result=nex_5_scope_6_handle(parameter);
      assert(expected==nullptr);
      auto value=nexrt::readHandle(result);assert(nexrt::isSuccess(value));assert(nexrt::unwrap(value).object->text=="owned input:0");
      nex_release(result);nex_release(parameter);
    }catch(const nexrt::Trap &error){assert(expected&&error.code==expected);trapped=true;}
    assert(trapped==(expected!=nullptr));
    // On traps, the scope owns parameters and every temporary the generated code left behind.
  }
}
int main(){
  request(0,nullptr);request(1,"E_LIMIT");request(2,"E_OVERFLOW");request(3,"E_ASSERT");request(4,"E_RESULT");
  {
    nexrt::RequestScope scope;scope.cancel();bool caught=false;
    try{nex_poll(7);}catch(const nexrt::Trap &error){caught=error.code=="E_CANCELLED"&&error.line==7;}assert(caught);
  }
  {
    nexrt::RequestScope scope(100,0);bool caught=false;
    try{nex_poll(8);}catch(const nexrt::Trap &error){caught=error.code=="E_TIMEOUT"&&error.line==8;}assert(caught);
  }
  std::vector<std::thread> threads;
  for(int i=0;i<8;++i)threads.emplace_back([]{for(int n=0;n<30;++n){request(0,nullptr);request(3,"E_ASSERT");}});
  for(auto &thread:threads)thread.join();
  nex_runtime_finish();assert(nexrt::liveObjects==0);
}
