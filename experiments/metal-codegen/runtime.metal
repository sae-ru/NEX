#include <metal_stdlib>
using namespace metal;

// All potentially overflowing arithmetic uses unsigned bits. The generated
// functions never rely on Metal's undefined signed-overflow behavior.
struct NexState { uint code; uint remaining; };
constant ulong nex_sign = 0x8000000000000000UL;
constant ulong nex_max = 0x7fffffffffffffffUL;
inline long nex_bits(ulong x) { return as_type<long>(x); }
inline ulong nex_unsigned(long x) { return as_type<ulong>(x); }
inline bool nex_tick(thread NexState &s) {
  if (s.code) return false;
  if (!s.remaining) { s.code = 4; return false; }
  --s.remaining;
  return true;
}
inline long nex_add(long a, long b, thread NexState &s) {
  ulong x=nex_unsigned(a), y=nex_unsigned(b), z=x+y;
  if (((x^z)&(y^z)&nex_sign)!=0) { s.code=1; return 0; }
  return nex_bits(z);
}
inline long nex_sub(long a, long b, thread NexState &s) {
  ulong x=nex_unsigned(a), y=nex_unsigned(b), z=x-y;
  if (((x^y)&(x^z)&nex_sign)!=0) { s.code=1; return 0; }
  return nex_bits(z);
}
inline long nex_neg(long a, thread NexState &s) {
  ulong x=nex_unsigned(a);
  if (x==nex_sign) { s.code=1; return 0; }
  return nex_bits(0UL-x);
}
inline ulong nex_magnitude(long x) {
  ulong bits=nex_unsigned(x);
  return x<0 ? 0UL-bits : bits;
}
inline long nex_mul(long a, long b, thread NexState &s) {
  bool negative=(a<0)!=(b<0);
  ulong x=nex_magnitude(a), y=nex_magnitude(b);
  ulong limit=negative ? nex_sign : nex_max;
  if (x && y>limit/x) { s.code=1; return 0; }
  ulong product=x*y;
  return nex_bits(negative ? 0UL-product : product);
}
inline long nex_div(long a, long b, thread NexState &s) {
  if (!b) { s.code=2; return 0; }
  if (nex_unsigned(a)==nex_sign && b==-1L) { s.code=1; return 0; }
  ulong value=nex_magnitude(a)/nex_magnitude(b);
  return nex_bits((a<0)!=(b<0) ? 0UL-value : value);
}
inline long nex_mod(long a, long b, thread NexState &s) {
  if (!b) { s.code=2; return 0; }
  // In NEX MIN % -1 is zero; MIN / -1 is overflow.
  ulong value=nex_magnitude(a)%nex_magnitude(b);
  return nex_bits(a<0 ? 0UL-value : value);
}
