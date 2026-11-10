"""CUDA str values: exact binary64 conversion and bounded aggregate rendering."""
import json
import os
from pathlib import Path
import subprocess
import sys
import cuda_values as fixed
from cuda_text import pack

CAP=256
T=lambda text:pack(text,CAP)
B=lambda data:pack(data,16)
Z=[0]*33

def quote(text):
    return '"'+''.join('\\'+c if c in '"\\'else'\\u%04x'%ord(c)if ord(c)<32 else c for c in text)+'"'

def R(payload):return [1,*payload,*([0]*(66-len(payload)))]
def F(code,message):return [0,*T(code),*T(message)]


def fixtures():
    return [
      ('float', '''pub fn transform(x:f64)->str{return str(x);}
test fn oracle()->unit{assert(transform(-0.0)=="0e0");assert(transform(5e-324)=="5e-324");assert(transform(2.2250738585072014e-308)=="2.2250738585072014e-308");assert(transform(1.7976931348623157e308)=="1.7976931348623157e308");assert(transform(1.25)=="1.25e0");}''',
       lambda ids:[([[fixed.fword(x)]],T(text),0)for x,text in [(0.0,'0e0'),(-0.0,'0e0'),(1.25,'1.25e0'),(-1.75,'-1.75e0'),(5e-324,'5e-324'),(2.2250738585072014e-308,'2.2250738585072014e-308'),(1.7976931348623157e308,'1.7976931348623157e308'),(1e20,'1e20'),(1e-7,'1e-7')]]+[([[n]],Z,7)for n in [0x7ff0000000000000,0x7ff0000000000001,0xfff8000000000000]]),
      ('identity', 'pub fn transform(s:str)->str{return str(s);}\ntest fn oracle()->unit{assert(transform("α\\u0000\\"\\\\")=="α\\u0000\\"\\\\");}',
       lambda ids:[([T(x)],T(x),0)for x in ['','🌍\0"\\','x'*256]]),
      ('list', '''pub fn transform(xs:list<str>)->str{return str(xs);}
test fn oracle()->unit{assert(transform(["α","a\\u0000b"])=="[\\\"α\\\",\\\"a\\\\u0000b\\\"]");assert(transform([])=="[]");}''',
       lambda ids:[([[len(xs),*[w for x in xs for w in T(x)],*([0]*(33*(4-len(xs))))]],T('['+','.join(map(quote,xs))+']'),0)for xs in [[],['α','\0"\\\n🌍'],['x'*252]]]+[([[1,*T(x),*([0]*99)]],Z,18)for x in ['x'*253,'\0'*44]]),
      ('integers', '''pub fn transform(xs:list<i64>)->str{return str(xs);}
test fn oracle()->unit{assert(transform([-9223372036854775808,9223372036854775807])=="[-9223372036854775808,9223372036854775807]");}''',
       lambda ids:[([[2,-(1<<63),(1<<63)-1,0,0]],T('[-9223372036854775808,9223372036854775807]'),0)]),
      ('bytes', '''pub fn transform(b:bytes)->str{return str(b);}
test fn oracle()->unit{assert(transform(unwrap(bytes([0,255,128,65])))=="\\\"AP+AQQ==\\\"");}''',
       lambda ids:[([B(b'\0\xff\x80A')],T('"AP+AQQ=="'),0),([B(b'')],T('""'),0)]),
      ('result', '''pub fn transform(r:result<f64>)->str{return str(r);}
test fn oracle()->unit{assert(transform(ok(1.25))=="{\\\"ok\\\":1.25e0}");assert(transform(err<f64>("X","a\\u0000b"))=="{\\\"error\\\":{\\\"code\\\":\\\"X\\\",\\\"message\\\":\\\"a\\\\u0000b\\\"}}");}''',
       lambda ids:[([R([fixed.fword(1.25)])],T('{"ok":1.25e0}'),0),([F('X','a\0b')],T('{"error":{"code":"X","message":"a\\u0000b"}}'),0),([F('','')],T('{"error":{"code":"","message":""}}'),0)]),
      ('record', '''pub struct Packet<T>{name:str;value:T;data:bytes;flag:bool;}
pub fn transform(p:Packet<f64>)->str{return str(p);}
test fn oracle()->unit{assert(transform(Packet<f64>("🌍",1.25,unwrap(bytes([0,255])),true))=="{\\\"name\\\":\\\"🌍\\\",\\\"value\\\":1.25e0,\\\"data\\\":\\\"AP8=\\\",\\\"flag\\\":true}");}''',
       lambda ids:[([[*T('🌍'),fixed.fword(1.25),*B(b'\0\xff'),1]],T('{"name":"🌍","value":1.25e0,"data":"AP8=","flag":true}'),0)]),
      ('enum', '''pub enum Item{Pair(n:f64,label:str);Empty;}
pub fn transform(v:Item)->str{return str(v);}
test fn oracle()->unit{assert(transform(Item::Pair(1.25,"α"))=="{\\\"case\\\":\\\"Pair\\\",\\\"fields\\\":{\\\"n\\\":1.25e0,\\\"label\\\":\\\"α\\\"}}");assert(transform(Item::Empty())=="{\\\"case\\\":\\\"Empty\\\",\\\"fields\\\":{}}");}''',
       lambda ids:[([[0,fixed.fword(1.25),*T('α')]],T('{"case":"Pair","fields":{"n":1.25e0,"label":"α"}}'),0),([[1,*([0]*34)]],T('{"case":"Empty","fields":{}}'),0),([[2,*([0]*34)]],Z,6)]),
      ('empty', '''pub struct Empty{}
pub fn transform(v:Empty)->str{return str(v);}
test fn oracle()->unit{assert(transform(Empty())=="{}");}''',
       lambda ids:[([[0]],T('{}'),0)]),
      ('nested', '''pub fn transform(xs:list<result<f64>>)->str{return str(xs);}
test fn oracle()->unit{assert(transform([ok(1.25),err<f64>("X","α")])=="[{\\\"ok\\\":1.25e0},{\\\"error\\\":{\\\"code\\\":\\\"X\\\",\\\"message\\\":\\\"α\\\"}}]");}''',
       lambda ids:[([[2,*R([fixed.fword(1.25)]),*F('X','α'),*([0]*134)]],T('[{"ok":1.25e0},{"error":{"code":"X","message":"α"}}]'),0)]),
      ('order', '''pub struct Pair{text:str;n:i64;}
pub fn transform(s:str,fail:bool)->str{if fail{return str(Pair(s,1/0));}return "safe";}
test fn oracle()->unit{assert(transform("",false)=="safe");}''',
       lambda ids:[([T('x'*256),[1]],Z,2),([T('x'*256),[0]],T('safe'),0)])]


class CudaFormat(fixed.CudaValues):
    cases=staticmethod(fixtures)
    emission_schema='nex.cuda-emission/5'
    value_schema='nex.cuda-values/4'
    emit_args=('--text-capacity','256','--byte-capacity','16','--list-capacity','4')

    # The inherited preparation test has unrelated fixed-value ABI expectations.
    def test_public_preparation_and_limits(self):
        subprocess.run([sys.executable,'-B',fixed.harness.REPO/'tools/update_cuda_decimal_cache.py','--check'],check=True)
        self.source('module gpu;fn transform(x:f64)->str{return str(x);}fn main()->unit{}')
        self.assertEqual(self.cli('describe')['gpu_codegen']['cuda'],json.loads((fixed.harness.REPO/'llm/language-pack.json').read_text())['gpu_codegen']['cuda'])
        shader=self.root/'format.cu';self.cli('emit','--kind','cuda','--entry','transform','--text-capacity','3','-o',shader)
        doctor=self.cli('doctor');source=self.root/'format-probe.cpp';binary=self.root/('format-probe.exe'if os.name=='nt'else'format-probe')
        source.write_text('''#include <bit>
#include <cfenv>
#include <iostream>
#include "nex_float.h"
#define __device__
#define __global__
namespace device {struct Index{unsigned x;};Index blockIdx,blockDim,threadIdx;
#include '''+json.dumps(str(shader))+'''
}
int main(){using namespace device;unsigned long long state=0xa7d9043f17ULL;unsigned count=0;
auto check=[&](unsigned long long bits){if(((bits>>52)&2047)==2047)return;double value=std::bit_cast<double>(bits);NexState s{0,100,nullptr};auto text=nex_float_text<NexValue_0>(value,3,s);auto expected=nexrt::formatFloat(value);if(expected.size()>3){if(s.code!=18)throw std::runtime_error("small capacity mismatch");}else if(s.code||text.w[0]!=static_cast<long long>(expected.size()))throw std::runtime_error("small capacity false rejection");
struct Wide{long long w[5];};s={0,100,nullptr};auto full=nex_float_text<Wide>(value,32,s);std::string actual;for(unsigned i=0;i<full.w[0];++i)actual+=char(nex_octet(full,i));if(s.code||actual!=expected){std::cerr<<std::hex<<bits<<" "<<actual<<" "<<expected<<"\\n";throw std::runtime_error("binary64 decimal mismatch");}++count;};
for(int mode:{FE_TONEAREST,FE_DOWNWARD,FE_UPWARD,FE_TOWARDZERO}){if(std::fesetround(mode))return 2;for(unsigned exponent=0;exponent<2047;++exponent)for(unsigned long long fraction:{0ULL,1ULL,2ULL,0x7ffffffffffffULL,0xffffffffffffeULL,0xfffffffffffffULL})for(unsigned long long sign:{0ULL,0x8000000000000000ULL})check(sign|(static_cast<unsigned long long>(exponent)<<52)|fraction);for(unsigned i=0;i<25000;++i){state^=state<<13;state^=state>>7;state^=state<<17;check(state);}}
std::cout<<"{\\"ok\\":true,\\"comparisons\\":"<<count<<"}\\n";}
''')
        flags=['-std=c++20','-O1','-I'+str(fixed.harness.REPO/'runtime')]
        if os.name=='nt':flags+=['--target='+doctor['host'],'--sysroot='+doctor['native_sysroot']]
        else:flags+=['-fsanitize=undefined','-fno-sanitize-recover=all']
        child=subprocess.run([doctor['native_compiler'],*flags,source,'-o',binary],capture_output=True,text=True,timeout=90);self.assertEqual(child.returncode,0,child.stdout+child.stderr)
        child=subprocess.run([binary],capture_output=True,text=True,timeout=60);self.assertEqual(child.returncode,0,child.stdout+child.stderr)
        self.assertGreater(json.loads(child.stdout)['comparisons'],190000)
        print(child.stdout.strip())


if __name__=='__main__':fixed.unittest.main(argv=[__file__,'-v'])
