#include "nex_host.h"
#include "nex_json.h"
#include "third_party/json.hpp"
#include <iostream>
#include <thread>
#include <vector>
#if defined(__x86_64__) || defined(__i386__)
#include <xmmintrin.h>
#endif

using JSON=nlohmann::ordered_json;
using nexrt::Value;
extern "C" {
double nex_f64_add(double,double,int64_t);
double nex_f64_sub(double,double,int64_t);
double nex_f64_mul(double,double,int64_t);
double nex_f64_div(double,double,int64_t);
double nex_f64_mod(double,double,int64_t);
double nex_as_f64(int64_t,int64_t);
nexrt::Handle *nex_as_i64(double,int64_t);
void nex_list_append_i64(nexrt::Handle*,int64_t,int64_t);
void nex_record_init_i64(nexrt::Handle*,int64_t,int64_t,int64_t);
nexrt::Handle *nex_ok_i64(int64_t,int64_t);
}
void require(bool condition,const char *message){if(!condition)throw std::runtime_error(message);}
double fromHex(const std::string &text){
  uint64_t bits=0;auto result=std::from_chars(text.data(),text.data()+text.size(),bits,16);
  require(result.ec==std::errc()&&result.ptr==text.data()+text.size()&&text.size()==16,"bad probe bits");
  return std::bit_cast<double>(bits);
}
std::string bits(double value){
  char buffer[16];auto result=std::to_chars(buffer,buffer+sizeof(buffer),std::bit_cast<uint64_t>(value),16);
  return std::string(16-(result.ptr-buffer),'0')+std::string(buffer,result.ptr);
}
const std::string schema=R"({"schema":"nex.wire/2","root":"f64","records":{},"enums":{}})";
JSON observed(double value){
  auto stored=Value::floating(value);auto wire=nexrt::encodeJSON(stored);
  auto decoded=nexrt::decodeJSON(wire,schema);require(nexrt::isSuccess(decoded),"f64 JSON roundtrip failed");
  auto original=nexrt::unwrap(decoded);require(original.tag==Value::Floating,"wire lost floating tag");
  return JSON{{"ok",true},{"bits",bits(stored.floating())},{"display",nexrt::representation(stored)},
              {"wire",wire},{"json_bits",bits(original.floating())}};
}
JSON command(const JSON &request){
  try{
    auto operation=request.at(0).get<std::string>();
    if(operation=="decode"){
      auto value=nexrt::decodeJSON(request.at(1).get<std::string>(),schema);
      if(!nexrt::isSuccess(value))return JSON{{"ok",false},{"code",value.object->text}};
      return observed(nexrt::unwrap(value).floating());
    }
    if(operation=="from_integer")return observed(nex_as_f64(std::stoll(request.at(1).get<std::string>()),17));
    auto left=fromHex(request.at(1).get<std::string>());
    if(operation=="to_integer"){
      auto handle=nex_as_i64(left,17);auto value=nexrt::readHandle(handle);nex_release(handle);
      if(!nexrt::isSuccess(value))return JSON{{"ok",false},{"code",value.object->text}};
      return JSON{{"ok",true},{"integer",std::to_string(nexrt::unwrap(value).scalar)}};
    }
    if(operation=="value")return observed(left);
    auto right=fromHex(request.at(2).get<std::string>());
    double value=operation=="add"?nex_f64_add(left,right,17):operation=="sub"?nex_f64_sub(left,right,17):
      operation=="mul"?nex_f64_mul(left,right,17):operation=="div"?nex_f64_div(left,right,17):nex_f64_mod(left,right,17);
    return observed(value);
  }catch(const nexrt::Trap &error){return JSON{{"ok",false},{"code",error.code}};}
  catch(const nexrt::DataError &error){return JSON{{"ok",false},{"code",error.code}};}
}
void environmentCheck(int rounding){
  require(std::fesetround(rounding)==0,"cannot select test rounding");
  std::feclearexcept(FE_ALL_EXCEPT);std::feraiseexcept(FE_INVALID);
  auto checkEnvironment=[&]{require(std::fegetround()==rounding,"runtime changed caller rounding");require(std::fetestexcept(FE_ALL_EXCEPT)==FE_INVALID,"runtime changed caller flags");};
  volatile double one=1.0,half=0x1p-53;
  require(nex_f64_add(one,half,17)==1.0,"tie rounding depends on caller environment");checkEnvironment();
  require(nex_as_f64(9007199254740993LL,17)==9007199254740992.0,"integer conversion rounding depends on caller");checkEnvironment();
  // Exercise the inline helper as well as the public owned-value wrapper:
  // optimized GCC must not defer the inexact conversion until after fesetenv.
  volatile double fractional=1.9;int64_t direct=0;
  require(nexrt::floatToInteger(fractional,direct)&&direct==1,"direct float conversion ignored truncation");checkEnvironment();
  auto integer=nex_as_i64(1.9,17);require(nexrt::unwrap(nexrt::readHandle(integer)).scalar==1,"float conversion ignored truncation");nex_release(integer);checkEnvironment();
  require(nexrt::formatFloat(one)=="1e0","format depends on caller environment");checkEnvironment();
  auto decoded=nexrt::decodeJSON("9007199254740993",schema);
  require(nexrt::isSuccess(decoded)&&nexrt::unwrap(decoded).floating()==9007199254740992.0,"JSON rounding depends on caller");checkEnvironment();
  bool trapped=false;try{nex_f64_div(1.0,0.0,17);}catch(const nexrt::Trap &error){trapped=error.code=="E_DIV_ZERO"&&error.line==17;}
  require(trapped,"floating zero division did not trap");checkEnvironment();
}
void selfCheck(){
  {
    nexrt::RequestScope scope;
    for(int rounding:{FE_TONEAREST,FE_DOWNWARD,FE_UPWARD,FE_TOWARDZERO})environmentCheck(rounding);
    std::fesetenv(FE_DFL_ENV);
    std::feraiseexcept(FE_DIVBYZERO);
    bool rejected=false;try{nexrt::finiteFloat(std::bit_cast<double>(UINT64_C(0x7ff0000000000001)));}catch(const nexrt::DataError &error){rejected=error.code=="E_FLOAT";}
    require(rejected&&std::fetestexcept(FE_ALL_EXCEPT)==FE_DIVBYZERO,"signaling NaN validation changed caller flags");
    std::fesetenv(FE_DFL_ENV);
#if defined(__aarch64__) || defined(__x86_64__) || defined(__i386__)
    std::fenv_t original;require(std::fegetenv(&original)==0,"cannot capture environment");
    try{
#if defined(__aarch64__)
      uint64_t control;asm volatile("mrs %0, fpcr":"=r"(control));control|=UINT64_C(1)<<24;
      asm volatile("msr fpcr, %0"::"r"(control));
#else
      auto control=_mm_getcsr()|0x8040U;_mm_setcsr(control);
#endif
      auto tiny=std::bit_cast<double>(UINT64_C(1));
      require(nexrt::Value::floating(tiny).scalar==1,"caller FTZ corrupted scalar validation");
      require(bits(nex_f64_mul(tiny,1.0,17))=="0000000000000001","caller FTZ corrupted arithmetic");
      require(nexrt::formatFloat(tiny)=="5e-324","caller FTZ corrupted formatting");
      require(nexrt::unwrap(nexrt::decodeJSON("5e-324",schema)).scalar==1,"caller FTZ corrupted JSON parsing");
#if defined(__aarch64__)
      uint64_t after;asm volatile("mrs %0, fpcr":"=r"(after));require(after==control,"runtime changed caller FPCR");
#else
      require(_mm_getcsr()==control,"runtime changed caller MXCSR");
#endif
    }catch(...){std::fesetenv(&original);throw;}
    std::fesetenv(&original);
#endif
    require(bits(nexrt::floatArithmetic(-0.0,1.0,'*'))=="0000000000000000","zero was not normalized");
    require(nexrt::floatArithmetic(0x1p-1022,2.0,'/')==0x0.8p-1022,"subnormal was flushed");
    require(nexrt::floatArithmetic(0x0.0000000000001p-1022,2.0,'/')==0.0,"underflow tie did not round to zero");
    auto list=std::make_shared<nexrt::Data>(nexrt::Data::List);auto handle=nexrt::makeHandle(Value(list));
    nex_list_append_i64(handle,nexrt::floatBits(1.25),2);nex_release(handle);
    require(list->values[0].tag==Value::Floating&&list->values[0].floating()==1.25,"aggregate storage lost floating tag");
    auto alias=list;auto copied=std::make_shared<nexrt::Data>(*list);copied->values[0]=Value::floating(2.5);
    require(alias->values[0].floating()==1.25,"floating aggregate mutation escaped copied value");
    auto result=nex_ok_i64(nexrt::floatBits(1.25),2);auto payload=nexrt::unwrap(nexrt::readHandle(result));nex_release(result);
    require(payload.tag==Value::Floating&&payload.floating()==1.25,"result storage lost floating tag");
    auto record=std::make_shared<nexrt::Data>(nexrt::Data::Record);record->names={"value"};record->values.resize(1);
    handle=nexrt::makeHandle(Value(record));nex_record_init_i64(handle,0,nexrt::floatBits(1.25),2);nex_release(handle);
    require(record->values[0].tag==Value::Floating,"record storage lost floating tag");
    require(nexrt::equal(Value::floating(-0.0),Value::floating(0.0)),"normalized zero equality failed");
    require(!nexrt::equal(Value::floating(1.0),Value(1)),"integer and float were conflated");
    // A request must reclaim handles left live when generated code traps.
    handle=nexrt::makeHandle(Value(nexrt::string("owned before floating trap")));
    bool trapped=false;try{nex_f64_mul(0x1.fffffffffffffp1023,2.0,19);}catch(const nexrt::Trap &error){trapped=error.code=="E_FLOAT"&&error.line==19;}
    require(trapped,"floating overflow did not carry its source line");(void)handle;
  }
  nex_runtime_finish();
  std::vector<std::thread> threads;
  for(int mode:{FE_DOWNWARD,FE_UPWARD,FE_TOWARDZERO})threads.emplace_back([mode]{nexrt::RequestScope scope;for(int i=0;i<50;++i)environmentCheck(mode);std::fesetenv(FE_DFL_ENV);});
  for(auto &thread:threads)thread.join();nex_runtime_finish();
}
int main(int argc,char**){
  try{
    if(argc>1){selfCheck();std::cout<<"{\"ok\":true}\n";return 0;}
    std::string input;while(std::getline(std::cin,input)){
      JSON output;{nexrt::RequestScope scope;output=command(JSON::parse(input));}
      nex_runtime_finish();std::cout<<output.dump()<<'\n';
    }
  }catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}
}
