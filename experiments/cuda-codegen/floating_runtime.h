#pragma once
#include <string_view>
namespace nex::cuda_experiment {
inline constexpr std::string_view floatingRuntime=R"nexfloat(
// Finite binary64 extension. GPU operations name the rounding mode explicitly.
static_assert(sizeof(double)==8);
#if !defined(__CUDA_ARCH__)
#include <bit>
#include <cfenv>
#pragma STDC FENV_ACCESS ON
struct NexFloatEnvironment {
  std::fenv_t saved;bool active=false;
  explicit NexFloatEnvironment(NexState &s) {
    if(std::fegetenv(&saved)){if(!s.code)s.code=8;return;}
    if(std::fesetenv(FE_DFL_ENV)){std::fesetenv(&saved);if(!s.code)s.code=8;return;}
    active=true;
  }
  ~NexFloatEnvironment(){if(active)std::fesetenv(&saved);}
  NexFloatEnvironment(const NexFloatEnvironment&)=delete;
};
#endif
__device__ inline unsigned long long nex_f_bits(double value) {
#if defined(__CUDA_ARCH__)
  unsigned long long bits;asm("mov.b64 %0, %1;" : "=l"(bits) : "d"(value));return bits;
#else
  return std::bit_cast<unsigned long long>(value);
#endif
}
__device__ inline double nex_f_raw(unsigned long long bits) {
#if defined(__CUDA_ARCH__)
  double value;asm("mov.b64 %0, %1;" : "=d"(value) : "l"(bits));return value;
#else
  return std::bit_cast<double>(bits);
#endif
}
__device__ inline double nex_f_value(unsigned long long bits,NexState &s) {
  const auto magnitude=bits&0x7fffffffffffffffULL;
  if((magnitude&0x7ff0000000000000ULL)==0x7ff0000000000000ULL){if(!s.code)s.code=7;return 0.0;}
  return nex_f_raw(magnitude?bits:0ULL);
}
__device__ inline double nex_f_finite(double value,NexState &s){return nex_f_value(nex_f_bits(value),s);}
__device__ inline double nex_f_neg(double value,NexState &s){return nex_f_value(nex_f_bits(value)^nex_sign,s);}
__device__ inline unsigned long long nex_f_order(double value) {
  auto bits=nex_f_bits(value);return bits&nex_sign?~bits:bits^nex_sign;
}
__device__ inline bool nex_f_compare(double a,double b,unsigned int operation) {
  const auto x=nex_f_order(a),y=nex_f_order(b);
  switch(operation){case 0:return x==y;case 1:return x!=y;case 2:return x<y;case 3:return x<=y;case 4:return x>y;default:return x>=y;}
}
__device__ inline double nex_f_add(double a,double b,NexState &s) {
#if defined(__CUDA_ARCH__)
  double value;asm volatile("add.rn.f64 %0, %1, %2;" : "=d"(value) : "d"(a),"d"(b));
#else
  NexFloatEnvironment environment(s);if(s.code)return 0.0;volatile double value=a+b;
#endif
  return nex_f_finite(value,s);
}
__device__ inline double nex_f_sub(double a,double b,NexState &s) {
#if defined(__CUDA_ARCH__)
  double value;asm volatile("sub.rn.f64 %0, %1, %2;" : "=d"(value) : "d"(a),"d"(b));
#else
  NexFloatEnvironment environment(s);if(s.code)return 0.0;volatile double value=a-b;
#endif
  return nex_f_finite(value,s);
}
__device__ inline double nex_f_mul(double a,double b,NexState &s) {
#if defined(__CUDA_ARCH__)
  double value;asm volatile("mul.rn.f64 %0, %1, %2;" : "=d"(value) : "d"(a),"d"(b));
#else
  NexFloatEnvironment environment(s);if(s.code)return 0.0;volatile double value=a*b;
#endif
  return nex_f_finite(value,s);
}
__device__ inline double nex_f_div(double a,double b,NexState &s) {
  if(!(nex_f_bits(b)&0x7fffffffffffffffULL)){if(!s.code)s.code=2;return 0.0;}
#if defined(__CUDA_ARCH__)
  double value;asm volatile("div.rn.f64 %0, %1, %2;" : "=d"(value) : "d"(a),"d"(b));
#else
  NexFloatEnvironment environment(s);if(s.code)return 0.0;volatile double value=a/b;
#endif
  return nex_f_finite(value,s);
}
__device__ inline double nex_f_from_integer(long long a,NexState &s) {
#if defined(__CUDA_ARCH__)
  double value;asm volatile("cvt.rn.f64.s64 %0, %1;" : "=d"(value) : "l"(a));
#else
  NexFloatEnvironment environment(s);if(s.code)return 0.0;volatile double value=static_cast<double>(a);
#endif
  return nex_f_finite(value,s);
}
__device__ inline double nex_f_mod(double a,double b,NexState &s) {
  // Reduce exact binary significands. No quotient rounding, host fmod or libdevice.
  const auto sign=nex_f_bits(a)&nex_sign;
  const auto x=nex_f_bits(a)&0x7fffffffffffffffULL,y=nex_f_bits(b)&0x7fffffffffffffffULL;
  if(!y){if(!s.code)s.code=2;return 0.0;}
  if(x<y)return a;if(x==y)return 0.0;
  long long ex=static_cast<long long>(x>>52)-1023,ey=static_cast<long long>(y>>52)-1023;
  auto mx=x&0xfffffffffffffULL,my=y&0xfffffffffffffULL;
  if(x>>52)mx|=0x10000000000000ULL;
  else {ex=-1022;while(!(mx&0x10000000000000ULL)){mx<<=1;--ex;}}
  if(y>>52)my|=0x10000000000000ULL;
  else {ey=-1022;while(!(my&0x10000000000000ULL)){my<<=1;--ey;}}
  while(ex>ey){if(mx>=my)mx-=my;if(!mx)return 0.0;mx<<=1;--ex;}
  if(mx>=my)mx-=my;if(!mx)return 0.0;
  while(!(mx&0x10000000000000ULL)){mx<<=1;--ey;}
  unsigned long long bits;
  if(ey>=-1022)bits=(static_cast<unsigned long long>(ey+1023)<<52)|(mx&0xfffffffffffffULL);
  else bits=mx>>static_cast<unsigned int>(-1022-ey);
  return nex_f_value(sign|bits,s);
}
)nexfloat";
}
