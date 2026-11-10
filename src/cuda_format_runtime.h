#pragma once
#include <string_view>
namespace nex::cuda_detail {
inline constexpr std::string_view formatRuntime=R"nexformat(
template<class T> __device__ inline void nex_repr_char(T &out,unsigned c,unsigned capacity,NexState &s){if(s.code)return;if(static_cast<unsigned>(out.w[0])>=capacity){s.code=18;return;}nex_put_octet(out,static_cast<unsigned>(out.w[0]),c);++out.w[0];}
template<class T> __device__ inline void nex_repr_literal(T &out,char const *text,unsigned size,unsigned capacity,NexState &s){for(unsigned i=0;i<size&&!s.code;++i)nex_repr_char(out,static_cast<unsigned char>(text[i]),capacity,s);}
template<class T> __device__ inline void nex_repr_append(T &out,T const &value,unsigned capacity,NexState &s){for(unsigned i=0;i<static_cast<unsigned>(value.w[0])&&!s.code;++i)nex_repr_char(out,nex_octet(value,i),capacity,s);}
__device__ inline unsigned nex_repr_hex(unsigned n){return n<10U?48U+n:97U+n-10U;}
template<class T> __device__ inline void nex_repr_quoted(T &out,T const &value,unsigned capacity,NexState &s){
 nex_repr_char(out,34U,capacity,s);for(unsigned i=0;i<static_cast<unsigned>(value.w[0])&&!s.code;++i){auto c=nex_octet(value,i);if(c==34U||c==92U){nex_repr_char(out,92U,capacity,s);nex_repr_char(out,c,capacity,s);}else if(c<32U){nex_repr_literal(out,"\\u00",4U,capacity,s);nex_repr_char(out,nex_repr_hex(c>>4U),capacity,s);nex_repr_char(out,nex_repr_hex(c&15U),capacity,s);}else nex_repr_char(out,c,capacity,s);}nex_repr_char(out,34U,capacity,s);
}
template<class T,class B> __device__ inline void nex_repr_bytes(T &out,B const &bytes,unsigned capacity,NexState &s){
 nex_repr_char(out,34U,capacity,s);unsigned n=static_cast<unsigned>(bytes.w[0]);for(unsigned i=0;i<n&&!s.code;i+=3U){auto a=nex_octet(bytes,i),b=i+1U<n?nex_octet(bytes,i+1U):0U,c=i+2U<n?nex_octet(bytes,i+2U):0U;nex_repr_char(out,nex_base64_char(a>>2U),capacity,s);nex_repr_char(out,nex_base64_char(((a&3U)<<4U)|(b>>4U)),capacity,s);nex_repr_char(out,i+1U<n?nex_base64_char(((b&15U)<<2U)|(c>>6U)):61U,capacity,s);nex_repr_char(out,i+2U<n?nex_base64_char(c&63U):61U,capacity,s);}nex_repr_char(out,34U,capacity,s);
}
)nexformat";
}
