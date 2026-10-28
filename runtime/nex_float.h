#pragma once
#include <bit>
#include <cfenv>
#include <charconv>
#include <cmath>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>
#include "nex_error.h"
#include "third_party/dragonbox/dragonbox.h"

// Finite binary64 substrate. Keep arithmetic out of ambient rounding modes.
#pragma STDC FENV_ACCESS ON
namespace nexrt {
static_assert(sizeof(double)==8 && std::numeric_limits<double>::is_iec559 &&
              std::numeric_limits<double>::digits==53);
class FloatEnvironment {
  std::fenv_t saved;
public:
  FloatEnvironment() {
    if(std::fegetenv(&saved))
      throw DataError("E_FLOAT_ENV","cannot select the binary64 floating environment");
    if(std::fesetenv(FE_DFL_ENV)){
      std::fesetenv(&saved);
      throw DataError("E_FLOAT_ENV","cannot select the binary64 floating environment");
    }
  }
  ~FloatEnvironment(){std::fesetenv(&saved);}
  FloatEnvironment(const FloatEnvironment&)=delete;
  FloatEnvironment &operator=(const FloatEnvironment&)=delete;
};
inline double finiteFloat(double value) {
  auto magnitude=std::bit_cast<uint64_t>(value)&UINT64_C(0x7fffffffffffffff);
  if((magnitude&UINT64_C(0x7ff0000000000000))==UINT64_C(0x7ff0000000000000))
    throw DataError("E_FLOAT","non-finite f64 result");
  // Bit validation does not quiet signaling NaNs, change host status flags,
  // or mistake a subnormal for zero under a caller's flush-to-zero mode.
  return magnitude==0?0.0:value;
}
inline int64_t floatBits(double value){return std::bit_cast<int64_t>(finiteFloat(value));}
inline double floatValue(int64_t bits){return finiteFloat(std::bit_cast<double>(bits));}
inline double negateFloat(double value){return floatValue(floatBits(value)^std::numeric_limits<int64_t>::min());}
inline bool compareFloat(double left,double right,int64_t operation){
  FloatEnvironment environment;left=finiteFloat(left);right=finiteFloat(right);
  switch(operation){case 0:return left==right;case 1:return left!=right;case 2:return left<right;
    case 3:return left<=right;case 4:return left>right;case 5:return left>=right;}
  throw DataError("E_RUNTIME","unknown floating comparison");
}
inline double floatArithmetic(double left,double right,char operation) {
  FloatEnvironment environment;
  left=finiteFloat(left);right=finiteFloat(right);
  if((operation=='/'||operation=='%')&&right==0)
    throw DataError("E_DIV_ZERO","division by zero");
  volatile double result=0;
  switch(operation){
  case '+':result=left+right;break;case '-':result=left-right;break;
  case '*':result=left*right;break;case '/':result=left/right;break;
  case '%':result=std::fmod(left,right);break;
  default:throw DataError("E_RUNTIME","unknown floating operation");
  }
  return finiteFloat(result);
}
inline double integerToFloat(int64_t value){
  FloatEnvironment environment;volatile double result=static_cast<double>(value);return finiteFloat(result);
}
inline bool floatToInteger(double value,int64_t &result){
  FloatEnvironment environment;
  value=finiteFloat(value);
  // The exclusive upper bound is exactly representable; double(INT64_MAX)
  // rounds up to it and therefore cannot be used as an inclusive bound.
  if(value < -0x1p63 || value >= 0x1p63)return false;
  result=static_cast<int64_t>(value);return true;
}
inline std::string formatFloat(double value){
  FloatEnvironment environment;
  value=finiteFloat(value);if(std::bit_cast<uint64_t>(value)==0)return "0e0";
  auto decimal=jkj::dragonbox::to_decimal(value,
    jkj::dragonbox::policy::decimal_to_binary_rounding::nearest_to_even,
    jkj::dragonbox::policy::binary_to_decimal_rounding::to_even);
  char buffer[24];auto converted=std::to_chars(buffer,buffer+sizeof(buffer),decimal.significand);
  if(converted.ec!=std::errc())throw DataError("E_FLOAT","cannot format f64");
  std::string digits(buffer,converted.ptr),text=decimal.is_negative?"-":"";
  text+=digits.front();if(digits.size()>1)text+='.'+digits.substr(1);
  return text+'e'+std::to_string(decimal.exponent+int(digits.size())-1);
}
}
