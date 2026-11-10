#pragma once
#include "cuda_decimal_cache.h"
namespace nex::cuda_detail {
// Copyright 2020-2022 Junekey Jeon. Derived under BSL-1.0; see the complete
// notice in cuda_decimal_cache.h and runtime/third_party/dragonbox/LICENSE-Boost.
// Binary64 nearest-to-even specialization of the pinned Dragonbox implementation.
// The emitted cache contains its complete Boost notice. No host FP operation,
// locale, standard library, dynamic allocation or decimal parsing is used.
inline constexpr std::string_view decimalRuntime=R"nexdecimal(
__device__ inline NexDecimal128 nex_decimal_mul(unsigned long long x,unsigned long long y){
#if defined(__CUDA_ARCH__)
 unsigned long long high;asm("mul.hi.u64 %0, %1, %2;":"=l"(high):"l"(x),"l"(y));return {high,x*y};
#else
 unsigned long long a=x>>32U,b=static_cast<unsigned>(x),c=y>>32U,d=static_cast<unsigned>(y);
 auto ac=a*c,bc=b*c,ad=a*d,bd=static_cast<unsigned long long>(b)*d;
 auto middle=(bd>>32U)+static_cast<unsigned>(ad)+static_cast<unsigned>(bc);
 return {ac+(middle>>32U)+(ad>>32U)+(bc>>32U),(middle<<32U)+static_cast<unsigned>(bd)};
#endif
}
__device__ inline NexDecimal128 nex_decimal_upper(unsigned long long x,NexDecimal128 const &c){auto r=nex_decimal_mul(x,c.high);auto add=nex_decimal_mul(x,c.low).high;auto low=r.low+add;return {r.high+static_cast<unsigned long long>(low<r.low),low};}
__device__ inline NexDecimal128 nex_decimal_lower(unsigned long long x,NexDecimal128 const &c){auto r=nex_decimal_mul(x,c.low);return {r.high+x*c.high,r.low};}
struct NexDecimalParity {bool parity,integer;};
__device__ inline NexDecimalParity nex_decimal_parity(unsigned long long x,NexDecimal128 const &c,int beta){auto r=nex_decimal_lower(x,c);return {((r.high>>(64-beta))&1ULL)!=0,((r.high<<beta)|(r.low>>(64-beta)))==0};}
struct NexDecimal {unsigned long long significand;int exponent;};
__device__ inline NexDecimal nex_decimal_trim(NexDecimal const &input){auto r=input;while(r.significand%10ULL==0){r.significand/=10ULL;++r.exponent;}return r;}
__device__ inline NexDecimal nex_decimal_shorter(int exponent){
 int minus_k=(exponent*631305-261663)>>21;int beta=exponent+((-minus_k*1741647)>>19);auto c=nex_decimal_cache[-minus_k+292];
 auto left=(c.high-(c.high>>54U))>>(11-beta),right=(c.high+(c.high>>53U))>>(11-beta);
 if(exponent<2||exponent>3)++left;
 auto significand=right/10ULL;if(significand*10ULL>=left)return nex_decimal_trim({significand,minus_k+1});
 significand=((c.high>>(10-beta))+1ULL)/2ULL;
 if((significand&1ULL)&&exponent==-77)--significand;else if(significand<left)++significand;
 return nex_decimal_trim({significand,minus_k});
}
__device__ inline NexDecimal nex_decimal_normal(unsigned long long two_fc,int exponent,bool even){
 int minus_k=((exponent*315653)>>20)-2;int beta=exponent+((-minus_k*1741647)>>19);auto c=nex_decimal_cache[-minus_k+292];
 unsigned delta=static_cast<unsigned>(c.high>>(63-beta));auto z=nex_decimal_upper((two_fc|1ULL)<<beta,c);auto zi=z.high;bool z_integer=z.low==0;
 unsigned long long significand=zi/1000ULL;unsigned remainder=static_cast<unsigned>(zi-significand*1000ULL);
 if(remainder<delta){if(remainder==0&&z_integer&&!even){--significand;remainder=1000U;goto smaller;}}
 else if(remainder>delta)goto smaller;
 else{auto p=nex_decimal_parity(two_fc-1ULL,c,beta);if(!p.parity&&(!even||exponent<-2||exponent>86||!p.integer))goto smaller;}
 return nex_decimal_trim({significand,minus_k+3});
 smaller:
 significand*=10ULL;unsigned distance=remainder-delta/2U+50U;bool approximate_parity=((distance^50U)&1U)!=0;bool divisible=distance%100U==0;distance/=100U;significand+=distance;
 if(divisible){auto p=nex_decimal_parity(two_fc,c,beta);if(p.parity!=approximate_parity||(p.integer&&(significand&1ULL)))--significand;}
 return nex_decimal_trim({significand,minus_k+2});
}
__device__ inline NexDecimal nex_decimal(unsigned long long bits){
 auto fraction=bits&0xfffffffffffffULL;int exponent=static_cast<int>((bits>>52U)&2047ULL);
 if(exponent){exponent-=1075;if(!fraction)return nex_decimal_shorter(exponent);fraction|=0x10000000000000ULL;}else exponent=-1074;
 return nex_decimal_normal(fraction<<1U,exponent,(fraction&1ULL)==0);
}
template<class T> __device__ inline T nex_float_text(double value,unsigned capacity,NexState &s){
 if(s.code)return {};auto bits=nex_f_bits(value),magnitude=bits&0x7fffffffffffffffULL;if((magnitude>>52U)==2047ULL){s.code=7;return {};}
 NexDecimal decimal=magnitude?nex_decimal(magnitude):NexDecimal{0ULL,0};unsigned digits[24],n=0;auto significand=decimal.significand;
 do{digits[n++]=static_cast<unsigned>(significand%10ULL)+48U;significand/=10ULL;}while(significand);
 int exponent=decimal.exponent+static_cast<int>(n)-1;unsigned exp_digits[4],count=0,absolute=static_cast<unsigned>(exponent<0?-exponent:exponent);
 do{exp_digits[count++]=absolute%10U+48U;absolute/=10U;}while(absolute);
 bool negative=magnitude&&(bits&nex_sign);unsigned length=n+static_cast<unsigned>(n>1)+static_cast<unsigned>(negative)+1U+count+static_cast<unsigned>(exponent<0);
 if(length>capacity){s.code=18;return {};}T r{};r.w[0]=length;unsigned out=0;if(negative)nex_put_octet(r,out++,45U);nex_put_octet(r,out++,digits[--n]);if(n)nex_put_octet(r,out++,46U);while(n)nex_put_octet(r,out++,digits[--n]);nex_put_octet(r,out++,101U);if(exponent<0)nex_put_octet(r,out++,45U);while(count)nex_put_octet(r,out++,exp_digits[--count]);return r;
}
)nexdecimal";
}
