#pragma once
#include "nex_float.h"
#include <type_traits>

// Explicit IEEE value domains for migration support. Ordinary NEX f64 keeps
// finiteFloat's checked, zero-normalizing contract. No source type uses these
// domains yet. Raw-bit admission/inspection never evaluates a signaling NaN.
namespace nexrt::ieee {
enum class Relation { Equal, NotEqual, Less, LessEqual, Greater, GreaterEqual };

template<class Float, class UInt> class Binary {
  static_assert((std::is_same_v<Float,float> && std::is_same_v<UInt,uint32_t>) ||
                (std::is_same_v<Float,double> && std::is_same_v<UInt,uint64_t>));
  static_assert(sizeof(Float)==sizeof(UInt) && std::numeric_limits<Float>::is_iec559 &&
                std::numeric_limits<Float>::radix==2);
  UInt bits_;
  explicit constexpr Binary(UInt bits):bits_(bits){}
  Float native()const{return std::bit_cast<Float>(bits_);}
  static Binary result(Float value){return fromBits(std::bit_cast<UInt>(value)).canonicalized();}
public:
  using Storage=UInt;
  using Native=Float;
  static constexpr unsigned width=sizeof(UInt)*8;
  static constexpr unsigned fraction=std::numeric_limits<Float>::digits-1;
  static_assert((width==32 && fraction==23) || (width==64 && fraction==52));
  static constexpr UInt sign=UInt(1)<<(width-1);
  static constexpr UInt exponent=(~UInt(0) >> (fraction+1))<<fraction;
  static constexpr UInt fractionMask=(UInt(1)<<fraction)-1;
  static constexpr UInt canonicalNaN=exponent|(UInt(1)<<(fraction-1));
  static constexpr Binary fromBits(UInt bits){return Binary(bits);}
  constexpr UInt rawBits()const{return bits_;}
  constexpr bool negative()const{return (bits_&sign)!=0;}
  constexpr bool isNaN()const{return (bits_&exponent)==exponent && (bits_&fractionMask)!=0;}
  constexpr bool isInfinite()const{return (bits_&~sign)==exponent;}
  constexpr bool isZero()const{return (bits_&~sign)==0;}
  constexpr bool isSubnormal()const{return (bits_&exponent)==0 && !isZero();}
  constexpr UInt canonicalBits()const{return isNaN()?canonicalNaN:bits_;}
  constexpr Binary canonicalized()const{return fromBits(canonicalBits());}
  constexpr Binary negate()const{return fromBits(bits_^sign);}
  constexpr Binary absolute()const{return fromBits(bits_&~sign);}

  static Binary arithmetic(Binary left,Binary right,char operation){
    // Volatile operands/results enforce one destination-width rounding per
    // operation, also under optimization. They prohibit contraction and keep
    // conversions/status changes before the saved environment is restored.
    FloatEnvironment environment;
    volatile Float a=left.native(),b=right.native(),value=0;
    switch(operation){
    case '+':value=a+b;break;case '-':value=a-b;break;
    case '*':value=a*b;break;case '/':value=a/b;break;
    case '%':value=std::fmod(a,b);break;
    default:throw DataError("E_RUNTIME","unknown IEEE arithmetic operation");
    }
    return result(value);
  }
  static bool compare(Binary left,Binary right,Relation relation){
    if(left.isNaN() || right.isNaN())return relation==Relation::NotEqual;
    FloatEnvironment environment;
    volatile Float a=left.native(),b=right.native();
    switch(relation){
    case Relation::Equal:return a==b;case Relation::NotEqual:return a!=b;
    case Relation::Less:return a<b;case Relation::LessEqual:return a<=b;
    case Relation::Greater:return a>b;case Relation::GreaterEqual:return a>=b;
    }
    throw DataError("E_RUNTIME","unknown IEEE comparison");
  }
  // Java Float/Double.compare: -0 < +0, all NaNs equal and above +infinity.
  static int javaCompare(Binary left,Binary right){
    if(left.isNaN())return right.isNaN()?0:1;
    if(right.isNaN())return -1;
    if(left.isZero() && right.isZero())return int(right.negative())-int(left.negative());
    if(compare(left,right,Relation::Less))return -1;
    return compare(left,right,Relation::Greater)?1:0;
  }
  static Binary fromJavaInt(int32_t value){
    FloatEnvironment environment;volatile Float converted=static_cast<Float>(value);
    return result(converted);
  }
  static Binary fromJavaLong(int64_t value){
    // Convert directly to binary32: an intermediate double can double-round.
    FloatEnvironment environment;volatile Float converted=static_cast<Float>(value);
    return result(converted);
  }
  int32_t toJavaInt()const{
    if(isNaN())return 0;
    FloatEnvironment environment;volatile Float value=native();
    if(value<=-0x1p31)return std::numeric_limits<int32_t>::min();
    if(value>=0x1p31)return std::numeric_limits<int32_t>::max();
    volatile int32_t converted=static_cast<int32_t>(value);return converted;
  }
  int64_t toJavaLong()const{
    if(isNaN())return 0;
    FloatEnvironment environment;volatile Float value=native();
    if(value<=-0x1p63)return std::numeric_limits<int64_t>::min();
    if(value>=0x1p63)return std::numeric_limits<int64_t>::max();
    volatile int64_t converted=static_cast<int64_t>(value);return converted;
  }
  template<class To> To convert()const{
    if(isNaN())return To::fromBits(To::canonicalNaN);
    const auto outSign=negative()?To::sign:typename To::Storage(0);
    if(isInfinite())return To::fromBits(outSign|To::exponent);
    if constexpr(To::width==width)return To::fromBits(bits_);
    else if constexpr(width==64){
      // Integer nearest/even narrowing covers overflow and gradual underflow
      // without an out-of-range C++ floating conversion or caller FP effects.
      auto encodedExponent=unsigned((bits_&exponent)>>fraction);
      if(encodedExponent==0)return To::fromBits(outSign);
      int power=int(encodedExponent)-1023;
      if(power>127)return To::fromBits(outSign|To::exponent);
      if(power< -150)return To::fromBits(outSign);
      uint64_t significand=(bits_&fractionMask)|(UINT64_C(1)<<52);
      unsigned shift=29+unsigned(power< -126?-126-power:0);
      uint64_t rounded=significand>>shift;
      auto remainder=significand&((UINT64_C(1)<<shift)-1),half=UINT64_C(1)<<(shift-1);
      if(remainder>half || (remainder==half && (rounded&1)))++rounded;
      if(power< -126)return To::fromBits(outSign|uint32_t(rounded));
      if(rounded==(UINT64_C(1)<<24)){rounded>>=1;++power;}
      if(power>127)return To::fromBits(outSign|To::exponent);
      return To::fromBits(outSign|(uint32_t(power+127)<<23)|(uint32_t(rounded)&To::fractionMask));
    }else{
      // Exact widening, including source subnormals, also uses only bits.
      unsigned encodedExponent=unsigned((bits_&exponent)>>fraction);
      uint64_t significand=bits_&fractionMask;
      if(encodedExponent==0 && significand==0)return To::fromBits(outSign);
      int power=int(encodedExponent)-127;
      if(encodedExponent==0){
        power= -126;
        while((significand&(UINT64_C(1)<<23))==0){significand<<=1;--power;}
      }
      return To::fromBits(outSign|(uint64_t(power+1023)<<52)|((significand&fractionMask)<<29));
    }
  }
};
using Binary32=Binary<float,uint32_t>;
using Binary64=Binary<double,uint64_t>;
}
