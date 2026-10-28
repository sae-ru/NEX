#include "nex_host.h"
#include <atomic>
#include <cstdio>
#include <exception>
#include <limits>
#include <thread>
#include <vector>
extern "C" {
int64_t nex_neg(int64_t,int64_t);
int64_t nex_neg_at(int64_t,int64_t,const nexrt::NativeSite*);
int64_t nex_div_at(int64_t,int64_t,int64_t,const nexrt::NativeSite*);
void nex_assert_at(int64_t,int64_t,const nexrt::NativeSite*);
void nex_poll_at(int64_t,const nexrt::NativeSite*);
nexrt::Handle *nex_string_new_at(const char*,int64_t,int64_t,const nexrt::NativeSite*);
}
namespace {
void require(bool condition){if(!condition)throw std::runtime_error("native site runtime invariant failed");}
const char *zero="0000000000000000000000000000000000000000000000000000000000000000";
const char *key="3333333333333333333333333333333333333333333333333333333333333333";
const nexrt::NativeFunctionSite function{zero,zero,zero};
const nexrt::NativeSite inner{&function,key,"inner",1,2},outer{&function,zero,"outer",0,3};
std::string expectedInner;
}
int main(int argc,char**){
  if(argc>1){nexrt::RequestScope scope;try{nexrt::runtimeFail("E_\xff","bad\xff\nmessage",nexrt::SourceLocation{7,&inner});}catch(const nexrt::LocatedTrap &trap){nexrt::printNativeTrap(trap.code.c_str(),trap.what(),trap.line,trap.source);}return 0;}
  unsigned cases=0;
  {
    nexrt::RequestScope scope;
    try{nex_neg(std::numeric_limits<int64_t>::min(),11);require(false);}
    catch(const nexrt::Trap &trap){require(trap.code=="E_OVERFLOW"&&trap.line==11&&!dynamic_cast<const nexrt::LocatedTrap*>(&trap));}
  }++cases;
  {
    nexrt::RequestScope scope;
    try{nex_neg_at(std::numeric_limits<int64_t>::min(),12,&inner);require(false);}
    catch(const nexrt::LocatedTrap &trap){expectedInner=trap.source;require(trap.code=="E_OVERFLOW"&&trap.line==12&&trap.source.find("\"kind\":\"inner\"")!=std::string::npos&&trap.source.find(key)!=std::string::npos);}
  }++cases;
  {
    nexrt::RequestScope scope;
    try{nexrt::hostOperation(nexrt::SourceLocation{99,&outer},[]{nex_assert_at(0,13,&inner);});require(false);}
    catch(const nexrt::LocatedTrap &trap){require(trap.code=="E_ASSERT"&&trap.line==13&&trap.source==expectedInner);}
  }++cases;
  {
    nexrt::RequestScope scope(1);nex_poll_at(14,&outer);
    try{nex_poll_at(15,&inner);require(false);}
    catch(const nexrt::LocatedTrap &trap){require(trap.code=="E_LIMIT"&&trap.line==15&&trap.source==expectedInner);}
  }++cases;
  {
    nexrt::RequestScope scope;scope.setCancellation([]{return true;});
    try{nex_poll_at(16,&inner);require(false);}
    catch(const nexrt::LocatedTrap &trap){require(trap.code=="E_CANCELLED"&&trap.line==16&&trap.source==expectedInner);}
  }++cases;
  auto objects=nexrt::liveObjects.load();
  {
    nexrt::RequestScope scope;
    (void)nex_string_new_at("owned",5,17,&outer);
    try{nex_assert_at(0,18,&inner);require(false);}catch(const nexrt::LocatedTrap&){}
  }
  require(nexrt::liveObjects.load()==objects);++cases;
  std::exception_ptr retained;
  {
    nexrt::RequestScope scope;std::string text=key;auto source=inner;source.site=text.c_str();
    try{nex_assert_at(0,19,&source);}catch(const nexrt::LocatedTrap&){retained=std::current_exception();}
    text.assign(10000,'x');
  }
  require(bool(retained));try{std::rethrow_exception(retained);}catch(const nexrt::LocatedTrap &trap){require(trap.source==expectedInner&&trap.line==19);}
  retained=nullptr;++cases;
  std::atomic<unsigned> passed{0};std::vector<std::thread> threads;
  for(int worker=0;worker<8;++worker)threads.emplace_back([&,worker]{
    try{for(int iteration=0;iteration<50;++iteration){nexrt::RequestScope scope;auto text=std::string(64,char('0'+worker));auto source=inner;source.site=text.c_str();
      try{nex_div_at(1,0,100+worker,&source);require(false);}
      catch(const nexrt::LocatedTrap &trap){require(trap.source.find(text)!=std::string::npos&&trap.line==100+worker&&trap.code=="E_DIV_ZERO");}
    }++passed;}catch(...){}
  });
  for(auto &thread:threads)thread.join();require(passed==8);require(nexrt::liveObjects.load()==objects);++cases;
  std::printf("{\"ok\":true,\"cases\":%u}\n",cases);
}
