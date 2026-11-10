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
int main(int argc,char **argv){
  if(argc>1&&std::string(argv[1])=="--direct-text")nexrt::runtimeFailText("E_RESULT",std::string("a\0b",3),{7,&inner});
  if(argc>1&&std::string(argv[1])=="--text-records"){
    auto source=nexrt::copyNativeSourceRecord(&inner);
    for(const auto &text:std::vector<std::string>{std::string("a\0b",3),"",std::string(4096,'x'),std::string(4095,'x')+"🌍",std::string(4097,'x'),std::string("a\0",2)+char(0xff)+"b"})
      nexrt::printNativeTrapText(std::string("E_A\0B",5),text,7,source,"request");
    nexrt::printNativeTrap("E_LEGACY","legacy",7,source);return 0;
  }
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
  // Preserve the frozen polymorphic host layouts and callable C-string APIs.
  struct OldTrap:std::runtime_error {std::string code;int64_t line;OldTrap():std::runtime_error("old"),code("E_OLD"),line(1){}};
  struct OldLocated:OldTrap {std::string source;};
  static_assert(sizeof(nexrt::Trap)==sizeof(OldTrap)&&alignof(nexrt::Trap)==alignof(OldTrap));
  static_assert(sizeof(nexrt::LocatedTrap)==sizeof(OldLocated)&&alignof(nexrt::LocatedTrap)==alignof(OldLocated));
  auto offset=[](const auto &object,const auto &member){return reinterpret_cast<const char*>(&member)-reinterpret_cast<const char*>(&object);};
  OldTrap old;nexrt::Trap current("E_OLD","old",1);OldLocated oldLocated;nexrt::LocatedTrap currentLocated(current,"source");
  require(offset(old,old.code)==offset(current,current.code)&&offset(old,old.line)==offset(current,current.line)&&offset(oldLocated,oldLocated.source)==offset(currentLocated,currentLocated.source));
  using LegacyFail=void(*)(const char*,const char*,int64_t);LegacyFail legacyFail=nexrt::runtimeFail;
  auto legacyPrint=&nexrt::printNativeTrap;require(legacyFail&&legacyPrint);++cases;
  const std::string complete=std::string("prefix\0",7)+"suffix🌍";
  {
    nexrt::RequestScope scope;
    try{nexrt::hostOperation(nexrt::SourceLocation{41},[&]{throw nexrt::DataError("E_TEXT",complete);});require(false);}
    catch(const nexrt::Trap &trap){require(nexrt::trapMessage(trap)==complete&&!dynamic_cast<const nexrt::LocatedTrap*>(&trap));}
  }++cases;
  {
    nexrt::RequestScope scope;
    try{nexrt::hostOperation({43,&outer},[&]{nexrt::hostOperation({42,&inner},[&]{throw nexrt::DataError("E_TEXT",complete);});});require(false);}
    catch(const nexrt::LocatedTrap &trap){require(nexrt::trapMessage(trap)==complete&&trap.source==expectedInner&&trap.line==42);}
  }++cases;
  {
    nexrt::RequestScope scope;
    try{nexrt::hostOperation({45,&outer},[&]{nexrt::hostOperation({44},[&]{throw nexrt::DataError("E_TEXT",complete);});});require(false);}
    catch(const nexrt::LocatedTrap &trap){require(nexrt::trapMessage(trap)==complete&&trap.source.find("outer")!=std::string::npos&&trap.line==44);}
  }++cases;
  require(nexrt::liveObjects.load()==objects);
  std::printf("{\"ok\":true,\"cases\":%u}\n",cases);
}
