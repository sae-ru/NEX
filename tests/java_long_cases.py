"""Fixed Java long semantic vectors and an independent unbounded-integer model."""
import json

MINIMUM = -(1 << 63)
MAXIMUM = (1 << 63) - 1


def cases():
    rows = []
    numbers = [MINIMUM, -1, 0, 1, MAXIMUM]
    for operation in (1, 2, 3, 5, 6, 7, 8, 9, 19):
        rows.extend([operation, a, b] for a in numbers for b in numbers)
    unary = [MINIMUM, MINIMUM+1, -(1 << 48)-1, -4294967297,
             -2147483649, -2147483648, -65537, -32769, -129, -1, 0,
             127, 128, 255, 256, 32767, 32768, 65535, 65536,
             2147483647, 4294967295, MAXIMUM]
    for operation in (0, 4, 10, 14, 15, 16, 17, 18):
        rows.extend([operation, value, 0] for value in unary)
    distances = [MINIMUM, -129, -65, -64, -63, -33, -32, -1,
                 0, 1, 16, 31, 32, 33, 63, 64, MAXIMUM]
    patterns = [MINIMUM, -4294967297, -1, 0, 1, 0x123456789ABCDEF0, MAXIMUM]
    for operation in (11, 12, 13):
        rows.extend([operation, value, amount] for value in patterns for amount in distances)
    # Fixed partial-product/carry boundaries, beyond MIN/MAX/zero products.
    pairs = [(65535, 65535), (65536, 65536), (4294967295, 4294967295),
             (4294967297, 4294967297), ((1 << 48)-1, (1 << 48)+1),
             (0x123456789ABCDEF, 0xFEDCBA987654321),
             (MAXIMUM-1, 4294967295), ((1 << 62)+1, 65537)]
    for left, right in pairs:
        rows.extend([3, a*left, b*right] for a in (-1, 1) for b in (-1, 1))
    return rows


def signed(value, bits=64):
    value %= 1 << bits
    return value - (1 << bits) if value >= (1 << (bits-1)) else value


def mathematical(case):
    operation, a, b = case
    if operation == 0: value = a
    elif operation == 1: value = a+b
    elif operation == 2: value = a-b
    elif operation == 3: value = a*b
    elif operation == 4: value = -a
    elif operation in (5, 6):
        if b == 0: return 'arithmetic'
        quotient = abs(a)//abs(b)
        if (a < 0) != (b < 0): quotient = -quotient
        value = quotient if operation == 5 else a-quotient*b
    elif operation == 7: value = a & b
    elif operation == 8: value = a | b
    elif operation == 9: value = a ^ b
    elif operation == 10: value = ~a
    elif operation == 11: value = a << (b & 63)
    elif operation == 12: value = a >> (b & 63)
    elif operation == 13: value = (a % (1 << 64)) >> (b & 63)
    elif operation == 14: value = signed(a, 32)
    elif operation == 15: value = signed(a, 8)
    elif operation == 16: value = signed(a, 16)
    elif operation == 17: value = a % (1 << 16)
    elif operation == 18: value = signed(a, 32)
    elif operation == 19: value = (a > b) - (a < b)
    else: raise AssertionError(case)
    return str(signed(value))


def source(expected):
    vectors = ','.join('Case('+','.join(map(str, row))+','+json.dumps(value)+')'
                       for row, value in zip(cases(), expected, strict=True))
    return '''module java_long_cases;
import "std/java_long.nex" as longs;
import "std/java_int.nex" as ints;
struct Case {operation:i64;left:i64;right:i64;expected:str;}
fn apply(case:Case)->str!{throw}{
 let a:longs::Int64=longs::from_i64(case.left);let b:longs::Int64=longs::from_i64(case.right);
 var value:longs::Int64=a;
 if case.operation==1 {value=longs::add(a,b);}
 if case.operation==2 {value=longs::subtract(a,b);}
 if case.operation==3 {value=longs::multiply(a,b);}
 if case.operation==4 {value=longs::negate(a);}
 if case.operation==5 {value=longs::divide(a,b);}
 if case.operation==6 {value=longs::remainder(a,b);}
 if case.operation==7 {value=longs::bit_and(a,b);}
 if case.operation==8 {value=longs::bit_or(a,b);}
 if case.operation==9 {value=longs::bit_xor(a,b);}
 if case.operation==10 {value=longs::bit_not(a);}
 if case.operation==11 {value=longs::shift_left(a,case.right);}
 if case.operation==12 {value=longs::shift_right(a,case.right);}
 if case.operation==13 {value=longs::unsigned_shift_right(a,case.right);}
 if case.operation==14 {return str(ints::to_i64(longs::narrow_int(a)));}
 if case.operation==15 {return str(ints::to_i64(longs::narrow_byte(a)));}
 if case.operation==16 {return str(ints::to_i64(longs::narrow_short(a)));}
 if case.operation==17 {return str(ints::to_i64(longs::narrow_char(a)));}
 if case.operation==18 {value=longs::from_int(ints::from_i64(case.left));}
 if case.operation==19 {return str(longs::compare(a,b));}
 return str(longs::to_i64(value));
}
fn checked_overflow()->i64{return 9223372036854775807+1;}
fn main()->unit!{io,throw}{
 let cases:list<Case>=['''+vectors+'''];var index:i64=0;var finalized:i64=0;
 while index<len(cases){
  let current:Case=cases[index];var observed:str="unexecuted";
  try {observed=apply(current);}
  catch(error:longs::ArithmeticError){
   assert((current.operation==5 && error.operation=="divide") || (current.operation==6 && error.operation=="remainder"));observed="arithmetic";
  }
  finally {finalized=finalized+1;}
  assert(observed==current.expected);index=index+1;
 }
 assert(finalized==len(cases));print("java-long-oracle-ok");
}
'''
