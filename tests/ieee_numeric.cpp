#include "nex_ieee.h"
#include "third_party/json.hpp"
#include <charconv>
#include <iostream>
#include <thread>
#include <vector>
#if defined(__x86_64__) || defined(__i386__)
#include <xmmintrin.h>
#endif
using JSON=nlohmann::ordered_json;
using namespace nexrt::ieee;
namespace {
void require(bool condition,const char *message){if(!condition)throw std::runtime_error(message);}
template<class B>B read(const std::string &text){
  typename B::Storage bits=0;auto parsed=std::from_chars(text.data(),text.data()+text.size(),bits,16);
  require(text.size()==B::width/4 && parsed.ec==std::errc() && parsed.ptr==text.data()+text.size(),"invalid IEEE bits");
  return B::fromBits(bits);
}
template<class U>std::string hex(U bits){
  char buffer[sizeof(U)*2];auto out=std::to_chars(buffer,buffer+sizeof(buffer),bits,16);
  require(out.ec==std::errc(),"cannot format IEEE bits");
  return std::string(sizeof(buffer)-(out.ptr-buffer),'0')+std::string(buffer,out.ptr);
}
template<class B>std::string observe(const JSON &request){
  const auto op=request.at(1).get<std::string>(),text=request.at(2).get<std::string>();
  if(op=="from_int")return hex(B::fromJavaInt(int32_t(std::stol(text))).rawBits());
  if(op=="from_long")return hex(B::fromJavaLong(std::stoll(text)).rawBits());
  auto a=read<B>(text);
  if(op=="raw")return hex(a.rawBits());
  if(op=="canonical")return hex(a.canonicalBits());
  if(op=="neg")return hex(a.negate().canonicalBits());
  if(op=="neg_raw")return hex(a.negate().rawBits());
  if(op=="abs_raw")return hex(a.absolute().rawBits());
  if(op=="classify")return a.isNaN()?"nan":a.isInfinite()?"infinity":a.isZero()?"zero":a.isSubnormal()?"subnormal":"normal";
  if(op=="to_int")return std::to_string(a.toJavaInt());
  if(op=="to_long")return std::to_string(a.toJavaLong());
  if(op=="convert"){
    if constexpr(B::width==32)return hex(a.template convert<Binary64>().rawBits());
    else return hex(a.template convert<Binary32>().rawBits());
  }
  auto b=read<B>(request.at(3).get<std::string>());
  if(op=="compare")return std::to_string(B::javaCompare(a,b));
  for(auto [name,relation]:{std::pair{"eq",Relation::Equal},{"ne",Relation::NotEqual},{"lt",Relation::Less},
      {"le",Relation::LessEqual},{"gt",Relation::Greater},{"ge",Relation::GreaterEqual}})
    if(op==name)return B::compare(a,b,relation)?"true":"false";
  for(auto [name,operation]:{std::pair{"add",'+'},{"sub",'-'},{"mul",'*'},{"div",'/'},{"rem",'%'}})
    if(op==name)return hex(B::arithmetic(a,b,operation).rawBits());
  throw std::runtime_error("unknown IEEE probe operation");
}
template<class B>void environment(int mode){
  require(std::fesetround(mode)==0,"cannot set caller rounding");
  std::feclearexcept(FE_ALL_EXCEPT);std::feraiseexcept(FE_INVALID);
  auto check=[&]{require(std::fegetround()==mode,"IEEE changed caller rounding");
    require(std::fetestexcept(FE_ALL_EXCEPT)==FE_INVALID,"IEEE changed caller flags");};
  auto one=B::fromJavaInt(1),zero=B::fromBits(0),negativeZero=B::fromBits(B::sign);
  check();
  auto half=B::fromBits(typename B::Storage(B::width==32?0x33800000ULL:0x3ca0000000000000ULL));
  require(B::arithmetic(one,half,'+').rawBits()==one.rawBits(),"IEEE tie depended on caller rounding");check();
  require(B::arithmetic(one,zero,'/').isInfinite(),"IEEE division by zero did not produce infinity");check();
  require(B::arithmetic(zero,negativeZero,'/').rawBits()==B::canonicalNaN,"IEEE invalid result was not canonical NaN");check();
  require(B::arithmetic(negativeZero,one,'*').rawBits()==B::sign,"IEEE lost negative zero");check();
  auto signaling=B::fromBits(B::exponent|1);
  require(signaling.isNaN() && signaling.rawBits()==(B::exponent|1),"raw signaling NaN changed");check();
  require(!B::compare(signaling,one,Relation::Equal) && B::compare(signaling,one,Relation::NotEqual),"NaN comparison differs");check();
  require(signaling.toJavaInt()==0 && signaling.toJavaLong()==0,"NaN integer conversion differs");check();
  require(B::javaCompare(negativeZero,zero)==-1 && B::javaCompare(signaling,one)==1,"Java total comparison differs");check();
  require(B::fromJavaLong(9007199254740993LL).toJavaLong()==9007199254740992LL,"integer tie conversion differs");check();
  require(one.toJavaInt()==1 && one.toJavaLong()==1,"finite integer conversion differs");check();
  require(B::fromBits(B::exponent).toJavaLong()==INT64_MAX && B::fromBits(B::exponent|B::sign).toJavaLong()==INT64_MIN,"infinite integer saturation differs");check();
  auto tiny=B::fromBits(1);
  require(B::arithmetic(tiny,one,'*').rawBits()==1,"IEEE subnormal flushed");check();
  require(B::arithmetic(B::fromBits(B::sign|1),B::fromJavaInt(2),'/').rawBits()==B::sign,"IEEE negative underflow tie lost sign");check();
  if constexpr(B::width==32){
    auto converted=one.template convert<Binary64>();require(converted.rawBits()==0x3ff0000000000000ULL,"IEEE widening differs");
    require(tiny.template convert<Binary64>().rawBits()==0x36a0000000000000ULL,"IEEE subnormal widening differs");
  }else {
    auto converted=one.template convert<Binary32>();require(converted.rawBits()==0x3f800000,"IEEE narrowing differs");
    require(B::fromBits(0x47effffff0000000ULL).template convert<Binary32>().rawBits()==0x7f800000,"IEEE overflow tie differs");
    require(B::fromBits(0x47efffffe0000001ULL).template convert<Binary32>().rawBits()==0x7f7fffff,"IEEE near-overflow rounding differs");
    require(B::fromBits(0x3690000000000000ULL).template convert<Binary32>().rawBits()==0,"IEEE subnormal tie differs");
  }
  check();
}
void selfCheck(){
  std::fenv_t saved;require(std::fegetenv(&saved)==0,"cannot capture caller environment");
  try{
    for(int mode:{FE_TONEAREST,FE_DOWNWARD,FE_UPWARD,FE_TOWARDZERO}){environment<Binary32>(mode);environment<Binary64>(mode);}
    std::fesetenv(FE_DFL_ENV);
    require(Binary32::fromJavaLong((INT64_C(1)<<54)+(INT64_C(1)<<30)+1).rawBits()==0x5a800001,"long-to-float double-rounded");
    auto a=Binary64::fromBits(0x3ff0000002000000ULL),b=Binary64::fromBits(0x3feffffffc000000ULL);
    auto product=Binary64::arithmetic(a,b,'*');
    require(Binary64::arithmetic(product,Binary64::fromJavaInt(-1),'+').rawBits()==0,"IEEE operations contracted");
#if defined(__aarch64__) || defined(__x86_64__) || defined(__i386__)
    std::fesetenv(FE_DFL_ENV);
#if defined(__aarch64__)
    uint64_t control;asm volatile("mrs %0, fpcr":"=r"(control));control|=UINT64_C(1)<<24;
    asm volatile("msr fpcr, %0"::"r"(control));
#else
    auto control=_mm_getcsr()|0x8040U;_mm_setcsr(control);
#endif
    require(Binary32::arithmetic(Binary32::fromBits(1),Binary32::fromJavaInt(1),'*').rawBits()==1,"caller FTZ corrupted binary32");
    require(Binary64::arithmetic(Binary64::fromBits(1),Binary64::fromJavaInt(1),'*').rawBits()==1,"caller FTZ corrupted binary64");
#if defined(__aarch64__)
    uint64_t after;asm volatile("mrs %0, fpcr":"=r"(after));require(after==control,"IEEE changed caller FPCR");
#else
    require(_mm_getcsr()==control,"IEEE changed caller MXCSR");
#endif
#endif
  }catch(...){std::fesetenv(&saved);throw;}
  std::fesetenv(&saved);
  std::vector<std::exception_ptr> errors(3);std::vector<std::thread> threads;
  for(size_t i=0;i<errors.size();++i)threads.emplace_back([&,i]{try{
    for(int j=0;j<30;++j){environment<Binary32>(FE_DOWNWARD);environment<Binary64>(FE_UPWARD);}
  }catch(...){errors[i]=std::current_exception();}});
  for(auto &thread:threads)thread.join();for(auto error:errors)if(error)std::rethrow_exception(error);
}
}
int main(int argc,char **argv){try{
  if(argc==2 && std::string(argv[1])=="--self-test"){selfCheck();std::cout<<"{\"ok\":true}\n";return 0;}
  std::string line;while(std::getline(std::cin,line)){
    auto input=JSON::parse(line);auto width=input.at(0).get<int>();
    require(width==32 || width==64,"unknown IEEE width");
    std::cout<<(width==32?observe<Binary32>(input):observe<Binary64>(input))<<'\n';
  }
}catch(const std::exception &error){std::cerr<<error.what()<<'\n';return 1;}}
