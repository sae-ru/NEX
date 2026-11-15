"""Explicit Java int domain: real JDK golden cases and independent backend checks."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import unittest
import support as h
import standard_library as helpers

FIXTURE=h.REPO/'tests/fixtures/java-int32'


def cases():
    result=[];numbers=[-2147483648,-1,0,1,2147483647]
    for operation in (1,2,3,5,6,7,8,9):
        result.extend([operation,a,b] for a in numbers for b in numbers)
    for operation in (0,4,10,14,15,16):
        result.extend([operation,a,0] for a in [-9223372036854775808,-4294967297,-2147483648,
            -65537,-32769,-129,-1,0,127,128,255,256,32767,32768,65535,65536,2147483647,4294967295,9223372036854775807])
    for operation in (11,12,13):
        result.extend([operation,a,b] for a in numbers for b in [-9223372036854775808,-65,-33,-32,-1,0,1,16,31,32,33,63,64,9223372036854775807])
    return result


def mathematical(case):
    operation,raw_a,raw_b=case
    def signed(value,bits=32):
        reduced=value%(1<<bits)
        return reduced-(1<<bits) if reduced>=(1<<(bits-1)) else reduced
    a=signed(raw_a);b=signed(raw_b)
    if operation==0:return str(a)
    if operation==1:return str(signed(a+b))
    if operation==2:return str(signed(a-b))
    if operation==3:return str(signed(a*b))
    if operation==4:return str(signed(-a))
    if operation in (5,6):
        if b==0:return 'arithmetic'
        quotient=abs(a)//abs(b)
        if (a<0)!=(b<0):quotient=-quotient
        return str(signed(quotient if operation==5 else a-quotient*b))
    if operation==7:return str(signed(a&b))
    if operation==8:return str(signed(a|b))
    if operation==9:return str(signed(a^b))
    if operation==10:return str(signed(~a))
    if operation==11:return str(signed(a<<(raw_b&31)))
    if operation==12:return str(a>>(raw_b&31))
    if operation==13:return str(signed((a&0xffffffff)>>(raw_b&31)))
    if operation==14:return str(signed(a,8))
    if operation==15:return str(signed(a,16))
    if operation==16:return str(a&0xffff)
    raise AssertionError(case)


def source(expected):
    rows=','.join('Case('+','.join(map(str,case))+','+json.dumps(output)+')' for case,output in zip(cases(),expected,strict=True))
    return '''module java_cases;
import "std/java_int.nex" as ints;
struct Case {operation:i64;left:i64;right:i64;expected:str;}
fn apply(case:Case)->str!{throw}{
 let a:ints::Int32=ints::from_i64(case.left);let b:ints::Int32=ints::from_i64(case.right);
 var value:ints::Int32=a;
 if case.operation==1 {value=ints::add(a,b);}
 if case.operation==2 {value=ints::subtract(a,b);}
 if case.operation==3 {value=ints::multiply(a,b);}
 if case.operation==4 {value=ints::negate(a);}
 if case.operation==5 {value=ints::divide(a,b);}
 if case.operation==6 {value=ints::remainder(a,b);}
 if case.operation==7 {value=ints::bit_and(a,b);}
 if case.operation==8 {value=ints::bit_or(a,b);}
 if case.operation==9 {value=ints::bit_xor(a,b);}
 if case.operation==10 {value=ints::bit_not(a);}
 if case.operation==11 {value=ints::shift_left(a,case.right);}
 if case.operation==12 {value=ints::shift_right(a,case.right);}
 if case.operation==13 {value=ints::unsigned_shift_right(a,case.right);}
 if case.operation==14 {value=ints::narrow_byte(a);}
 if case.operation==15 {value=ints::narrow_short(a);}
 if case.operation==16 {value=ints::narrow_char(a);}
 return str(ints::to_i64(value));
}
fn checked_overflow()->i64{return 9223372036854775807+1;}
fn main()->unit!{io,throw}{
 let cases:list<Case>=['''+rows+'''];var index:i64=0;var finalized:i64=0;
 while index<len(cases){
  let current:Case=cases[index];var observed:str="unexecuted";
  try {observed=apply(current);}
  catch(error:ints::ArithmeticError){
   assert((current.operation==5 && error.operation=="divide") || (current.operation==6 && error.operation=="remainder"));
   observed="arithmetic";
  }
  finally {finalized=finalized+1;}
  assert(observed==current.expected);index=index+1;
 }
 assert(finalized==len(cases));print("java-int-oracle-ok");
}
'''


class JavaInt(h.ToolchainCase):
    run_child=helpers.StandardLibrary.run_child
    strict_ts=helpers.StandardLibrary.strict_ts
    typescript=helpers.StandardLibrary.typescript

    def test_JDK_golden_and_independent_mathematical_oracle(self):
        fixture=json.loads((FIXTURE/'oracle.json').read_text())
        self.assertEqual(fixture['oracle_source_sha256'],hashlib.sha256((FIXTURE/'Oracle.java').read_bytes()).hexdigest())
        self.assertEqual(fixture['inputs'],cases())
        self.assertEqual(fixture['outputs'],list(map(mathematical,cases())))
        selected=os.environ.get('NEX_JAVA_HOME')
        if selected:
            tools=Path(selected)/'bin';suffix='.exe' if os.name=='nt' else ''
            javac=tools/('javac'+suffix);java=tools/('java'+suffix)
            self.run_child([javac,'-d',self.root,FIXTURE/'Oracle.java'])
            raw=''.join(' '.join(map(str,row))+'\n' for row in cases())
            live=subprocess.run([str(java),'-cp',str(self.root),'Oracle'],input=raw,capture_output=True,text=True,timeout=60)
            self.assertEqual(live.returncode,0,live.stderr)
            self.assertEqual(live.stdout.splitlines(),fixture['outputs'])
            print(json.dumps({'live_JDK':True,'cases':len(cases()),'version':self.run_child([java,'--version'])}))

    def test_latest_language_backend_agreement_and_checked_arithmetic(self):
        fixture=json.loads((FIXTURE/'oracle.json').read_text())
        (self.root/'nex.json').write_text('{"schema":"nex.project/1","language":"0.29","entry":"main.nex"}\n')
        compiler_pin=hashlib.sha256(Path(h.NEX).read_bytes()).hexdigest()
        self.source(source(fixture['outputs']));checked=self.cli('check')
        reference=self.cli('eval','--steps','10000000',timeout=180)
        self.assertEqual(reference['stdout'],'java-int-oracle-ok\n');native={}
        for profile in ('debug','release'):
            native[profile]=self.cli('run','--profile',profile,timeout=240)
            self.assertEqual(native[profile]['stdout'],'java-int-oracle-ok\n')
        typescript=self.typescript();self.assertEqual(typescript,'java-int-oracle-ok\n')
        self.assertEqual(self.cli('eval','--entry','checked_overflow',ok=False)['code'],'E_OVERFLOW')
        for profile in ('debug','release'):
            self.assertIn('E_OVERFLOW',self.cli('run','--entry','checked_overflow','--profile',profile,ok=False,timeout=240)['stderr'])
        self.assertEqual(self.typescript('checked_overflow',failure='E_OVERFLOW'),'E_OVERFLOW')
        self.assertEqual(hashlib.sha256(Path(h.NEX).read_bytes()).hexdigest(),compiler_pin)
        print(json.dumps({'schema':'nex.java-int32-agreement/1','ok':True,'compiler_sha256':compiler_pin,
            'revision':checked['revision'],'program_sha256':hashlib.sha256(self.file.read_bytes()).hexdigest(),
            'cases':len(cases()),'oracle_sha256':hashlib.sha256((FIXTURE/'oracle.json').read_bytes()).hexdigest(),
            'reference':reference,'native':native,'strict_executed_typescript':True,'checked_NEX_overflow_preserved':True}))

    def test_distinct_type_and_throw_effect(self):
        for body,code in [('let x:ints::Int32=ints::add(1,ints::from_i64(2));','E_TYPE'),
                          ('ints::divide(ints::from_i64(1),ints::from_i64(0));','E_EFFECT')]:
            with self.subTest(body=body):
                self.source('module bad;import "std/java_int.nex" as ints;fn main()->unit{'+body+'}')
                self.assertEqual(self.cli('check',ok=False)['code'],code)


if __name__=='__main__':unittest.main()
