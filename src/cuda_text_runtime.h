#pragma once
#include <string_view>
namespace nex::cuda_detail {
// Header-free CUDA C++20 helpers over canonical length-prefixed packed octets.
// Callers validate wire lengths/padding and apply capacity/bounds before writes.
inline constexpr std::string_view textRuntime=R"nextext(
template<class V> __device__ inline unsigned nex_octet(V const &v,unsigned i){return static_cast<unsigned>((nex_unsigned(v.w[1U+i/8U])>>((i%8U)*8U))&255ULL);}
template<class V> __device__ inline void nex_put_octet(V &v,unsigned i,unsigned b){const auto shift=(i%8U)*8U,slot=1U+i/8U;v.w[slot]=nex_bits((nex_unsigned(v.w[slot])&~(255ULL<<shift))|(static_cast<unsigned long long>(b)<<shift));}
template<class V> __device__ inline unsigned nex_utf8_error(V const &v){
 const auto size=static_cast<unsigned>(v.w[0]);
 for(unsigned i=0;i<size;){auto first=nex_octet(v,i);unsigned n=first<128U?1U:first>=194U&&first<=223U?2U:first>=224U&&first<=239U?3U:first>=240U&&first<=244U?4U:0U;
  if(!n||n>size-i)return 1U;unsigned code=first&(n==1?127U:n==2?31U:n==3?15U:7U);
  for(unsigned j=1;j<n;++j){auto c=nex_octet(v,i+j);if((c&192U)!=128U)return 1U;code=(code<<6U)|(c&63U);}
  if((n==2&&code<128U)||(n==3&&code<2048U)||(n==4&&code<65536U)||code>1114111U||(code>=55296U&&code<=57343U))return 2U;i+=n;
 }return 0U;
}
template<class V> __device__ inline long long nex_unicode_length(V const &v){long long n=0;for(unsigned i=0;i<static_cast<unsigned>(v.w[0]);++i)if((nex_octet(v,i)&192U)!=128U)++n;return n;}
template<class V> __device__ inline unsigned nex_unicode_offset(V const &v,unsigned index){unsigned n=0;for(unsigned i=0;i<static_cast<unsigned>(v.w[0]);++i)if((nex_octet(v,i)&192U)!=128U){if(n==index)return i;++n;}return static_cast<unsigned>(v.w[0]);}
template<class R,class V> __device__ inline R nex_octet_slice(V const &v,unsigned start,unsigned count){R r{};r.w[0]=count;for(unsigned i=0;i<count;++i)nex_put_octet(r,i,nex_octet(v,start+i));return r;}
template<class V> __device__ inline V nex_text_concat(V const &a,V const &b){V r=a;for(unsigned i=0;i<static_cast<unsigned>(b.w[0]);++i)nex_put_octet(r,static_cast<unsigned>(a.w[0])+i,nex_octet(b,i));r.w[0]=a.w[0]+b.w[0];return r;}
__device__ inline int nex_base64_digit(unsigned c){if(c>=65U&&c<=90U)return int(c-65U);if(c>=97U&&c<=122U)return int(c-97U+26U);if(c>=48U&&c<=57U)return int(c-48U+52U);if(c==43U)return 62;if(c==47U)return 63;return -1;}
__device__ inline unsigned nex_base64_char(unsigned n){return n<26U?n+65U:n<52U?n-26U+97U:n<62U?n-52U+48U:n==62U?43U:47U;}
template<class T> __device__ inline bool nex_base64_size(T const &text,unsigned &size){
 auto n=static_cast<unsigned>(text.w[0]);if(n%4U)return false;if(!n){size=0;return true;}
 unsigned padding=unsigned(nex_octet(text,n-1U)==61U)+unsigned(nex_octet(text,n-2U)==61U);size=n/4U*3U-padding;
 for(unsigned i=0;i<n;i+=4U){int a=nex_base64_digit(nex_octet(text,i)),b=nex_base64_digit(nex_octet(text,i+1));if(a<0||b<0)return false;auto c=nex_octet(text,i+2),d=nex_octet(text,i+3);bool last=i+4U==n;
  if(c==61U){if(!last||d!=61U||(b&15))return false;continue;}int cv=nex_base64_digit(c);if(cv<0)return false;
  if(d==61U){if(!last||(cv&3))return false;continue;}if(nex_base64_digit(d)<0)return false;
 }return true;
}
template<class B,class T> __device__ inline B nex_base64_decode(T const &text,unsigned size){B r{};r.w[0]=size;unsigned out=0;for(unsigned i=0;i<static_cast<unsigned>(text.w[0]);i+=4U){auto a=unsigned(nex_base64_digit(nex_octet(text,i))),b=unsigned(nex_base64_digit(nex_octet(text,i+1)));nex_put_octet(r,out++,((a<<2U)|(b>>4U))&255U);if(out<size){auto c=unsigned(nex_base64_digit(nex_octet(text,i+2)));nex_put_octet(r,out++,((b<<4U)|(c>>2U))&255U);if(out<size){auto d=unsigned(nex_base64_digit(nex_octet(text,i+3)));nex_put_octet(r,out++,((c<<6U)|d)&255U);}}}return r;}
template<class T,class B> __device__ inline T nex_base64_encode(B const &bytes){T r{};auto n=static_cast<unsigned>(bytes.w[0]);unsigned out=0;for(unsigned i=0;i<n;i+=3U){auto a=nex_octet(bytes,i),b=i+1U<n?nex_octet(bytes,i+1U):0U,c=i+2U<n?nex_octet(bytes,i+2U):0U;nex_put_octet(r,out++,nex_base64_char(a>>2U));nex_put_octet(r,out++,nex_base64_char(((a&3U)<<4U)|(b>>4U)));nex_put_octet(r,out++,i+1U<n?nex_base64_char(((b&15U)<<2U)|(c>>6U)):61U);nex_put_octet(r,out++,i+2U<n?nex_base64_char(c&63U):61U);}r.w[0]=out;return r;}
template<class T> __device__ inline T nex_integer_text(long long value,unsigned capacity,NexState &s){unsigned digits[20],count=0;auto magnitude=nex_magnitude(value);do{digits[count++]=unsigned(magnitude%10ULL)+48U;magnitude/=10ULL;}while(magnitude);unsigned size=count+unsigned(value<0);if(size>capacity){s.code=18;return {};}T r{};r.w[0]=size;unsigned i=0;if(value<0)nex_put_octet(r,i++,45U);while(count)nex_put_octet(r,i++,digits[--count]);return r;}
template<class T> __device__ inline T nex_boolean_text(bool value,unsigned capacity,NexState &s){unsigned size=value?4U:5U;if(size>capacity){s.code=18;return {};}T r{};r.w[0]=size;if(value){nex_put_octet(r,0,116);nex_put_octet(r,1,114);nex_put_octet(r,2,117);nex_put_octet(r,3,101);}else{nex_put_octet(r,0,102);nex_put_octet(r,1,97);nex_put_octet(r,2,108);nex_put_octet(r,3,115);nex_put_octet(r,4,101);}return r;}
)nextext";
}
