"""Dynamic UTF-8 GPU values, codecs and exact per-lane Result packets."""
import base64
import json
import os
import subprocess
import sys
import unittest
import cuda_values as fixed


def pack(data,capacity):
    if isinstance(data,str):data=data.encode('utf-8')
    data=bytes(data);assert len(data)<=capacity
    padding=((capacity+7)//8)*8-len(data);raw=data+bytes(padding)
    return [len(data),*[int.from_bytes(raw[i:i+8],'little',signed=True)for i in range(0,len(raw),8)]]


def T(text):return pack(text,64)
def B(data):return pack(data,80)
def R(payload):return [1,*payload,*([0]*(18-len(payload)))]
def F(code,message):return [0,*T(code),*T(message)]


def fixtures():
    zero=[0]*9
    return [
      ('rotate', '''pub fn transform(s:str)->str{let saved:str=s;var a:str=s;a=slice(a,1,len(a)-1)+s[0];assert(s==saved);return a;}
test fn oracle()->unit{assert(transform("A🌍é")=="🌍éA");assert(transform("A\\u0000🌍")=="\\u0000🌍A");}''',
       lambda ids: [([T('A🌍é')],T('🌍éA'),0),([T('A\0🌍')],T('\0🌍A'),0),([T('Ж😀组合')],T('😀组合Ж'),0),([T('')],zero,17),([T(b'\xc0\x80')],zero,6),([T(b'\xed\xa0\x80')],zero,6),([T(b'\xf4\x90\x80\x80')],zero,6),([T(b'\xf0\x9f')],zero,6),([[65,*([0]*8)]],zero,6),([[0,1,*([0]*7)]],zero,6)]),
      ('index', '''pub fn transform(s:str,i:i64)->str{return s[i];}
test fn oracle()->unit{assert(transform("é🌍",1)=="́");assert(transform("é🌍",2)=="🌍");}''',
       lambda ids: [([T('é🌍'),[1]],T('́'),0),([T('é🌍'),[2]],T('🌍'),0),([T('\0'),[0]],T('\0'),0),([T('a'),[-1]],zero,16),([T('a'),[9223372036854775807]],zero,16),([T(''),[0]],zero,16)]),
      ('concat', '''pub fn transform(a:str,b:str)->str{return a+b;}
test fn oracle()->unit{assert(transform("α","🌍")=="α🌍");}''',
       lambda ids: [([T('A'*64),T('')],T('A'*64),0),([T('A'*64),T('B')],zero,18),([T('\0'),T('🌍')],T('\0🌍'),0)]),
      ('slice', '''pub fn transform(s:str,start:i64,count:i64)->str{return slice(s,start,count);}
test fn oracle()->unit{assert(transform("α🌍é",1,2)=="🌍e");assert(transform("a",1,0)=="");}''',
       lambda ids: [([T('α🌍é'),[1],[2]],T('🌍e'),0),([T('α🌍'),[2],[0]],T(''),0),([T('α🌍'),[3],[0]],zero,17),([T('α🌍'),[1],[-1]],zero,17),([T('α🌍'),[0],[9223372036854775807]],zero,17)]),
      ('utf8_decode', '''pub fn transform(data:bytes)->result<str>{return decode_utf8(data);}
test fn oracle()->unit{assert(transform(unwrap(bytes([206,177,0])))==ok("α\\u0000"));assert(error_message(transform(unwrap(bytes([237,160,128]))))=="invalid Unicode scalar");assert(error_message(transform(unwrap(bytes([255]))))=="invalid UTF-8 string");assert(error_message(transform(unwrap(bytes([224,128,128]))))=="invalid Unicode scalar");assert(error_message(transform(unwrap(bytes([244,144,128,128]))))=="invalid Unicode scalar");assert(error_message(transform(unwrap(bytes([192,128]))))=="invalid UTF-8 string");assert(error_message(transform(unwrap(bytes([240,159]))))=="invalid UTF-8 string");assert(error_message(transform(unwrap(bytes([226,40,161]))))=="invalid UTF-8 string");assert(transform(unwrap(bytes([239,187,191])))==ok("\\ufeff"));}''',
       lambda ids: [([B('α\0🌍'.encode())],R(T('α\0🌍')),0),([B(b'\xef\xbb\xbf')],R(T('\ufeff')),0),([B(b'\xff')],F('E_UTF8','invalid UTF-8 string'),0),([B(b'\xed\xa0\x80')],F('E_UTF8','invalid Unicode scalar'),0),([B(b'\xe0\x80\x80')],F('E_UTF8','invalid Unicode scalar'),0),([B(b'a'*65)],[0]*19,18),([B(b'\xff'+b'a'*64)],F('E_UTF8','invalid UTF-8 string'),0)]),
      ('encode', '''pub fn transform(data:bytes)->str{return encode_base64(data);}
test fn oracle()->unit{assert(transform(unwrap(bytes([0,255,128,65])))=="AP+AQQ==");}''',
       lambda ids: [([B(b'\0\xff\x80A')],T('AP+AQQ=='),0),([B(b'')],T(''),0),([B(bytes(range(48)))],T(base64.b64encode(bytes(range(48))).decode()),0),([B(bytes(range(49)))],zero,18)]),
      ('decode', '''pub fn transform(text:str)->result<bytes>{return decode_base64(text);}
test fn oracle()->unit{assert(transform("AP+AQQ==")==ok(unwrap(bytes([0,255,128,65]))));assert(error_code(transform("Zh=="))=="E_BASE64");}''',
       lambda ids: [([T('Zm9v')],R(B(b'foo')),0),([T('AP+AQQ==')],R(B(b'\0\xff\x80A')),0),([T('')],R(B(b'')),0)]+[([T(s)],F('E_BASE64','invalid canonical base64'),0)for s in ['Zh==','Zm9=','Zg=','Zg==\n','====','_w==','α','\0']]),
      ('propagate', '''pub fn transform(value:result<str>)->result<bytes>{assert(error_code(ok(1))=="");assert(error_message(ok(1))=="");let text:str=value?;return ok(utf8_bytes(text));}
test fn oracle()->unit{assert(transform(ok("α🌍"))==ok(unwrap(bytes([206,177,240,159,140,141]))));assert(transform(err<str>("CUSTOM","arbitrary"))==err<bytes>("CUSTOM","arbitrary"));}''',
       lambda ids: [([R(T('α🌍'))],R(B('α🌍'.encode())),0),([F('CUSTOM','arbitrary 🌍')],F('CUSTOM','arbitrary 🌍'),0),([F('X\0Y','M\0🌍')],F('X\0Y','M\0🌍'),0)]),
      ('unwrap', '''pub fn transform(code:str,message:str,fail:bool)->i64{if fail{return unwrap(err<i64>(code+"!",message+"🌍"));}return 42;}
test fn oracle()->unit{assert(transform("custom","failure",false)==42);}''',
       lambda ids: [([T('custom'),T('failure'),[0]],[42],0),([T('custom'),T('failure'),[1]],[0],15,[*T('custom!'),*T('failure🌍')]),([T('X\0Y'),T('M\0'),[1]],[0],15,[*T('X\0Y!'),*T('M\0🌍')])]),
      ('format', '''pub fn transform(n:i64,flag:bool)->str{return str(n)+":"+str(flag);}
test fn oracle()->unit{assert(transform(-9223372036854775808,true)=="-9223372036854775808:true");assert(transform(9223372036854775807,false)=="9223372036854775807:false");}''',
       lambda ids: [([[n],[int(flag)]],T(str(n)+':'+str(flag).lower()),0)for n,flag in [(0,True),(-1,False),(-(1<<63),True),((1<<63)-1,False)]]),
      ('nested', '''pub fn transform(xs:list<str>)->str{return match xs{["α",s] if len(s)>0=>s+"!",[_,_] if false=>""[99],[]=>"empty",_=>"other"};}
test fn oracle()->unit{assert(transform(["α","🌍"])=="🌍!");assert(transform([])=="empty");assert(transform(["x"])=="other");}''',
       lambda ids: [([[2,*T('α'),*T('arbitrary'),*([0]*18)]],T('arbitrary!'),0),([[0,*([0]*36)]],T('empty'),0),([[1,*T('x'),*([0]*27)]],T('other'),0)]),
      ('convert', '''pub fn transform(x:f64)->result<i64>{return as_i64(x);}
test fn oracle()->unit{assert(transform(-1.75)==ok(-1));assert(error_code(transform(9223372036854775808.0))=="E_RANGE");}''',
       lambda ids: [([[fixed.fword(-1.75)]],R([-1]),0),([[fixed.fword(9223372036854775808.0)]],F('E_RANGE','f64 value is outside i64 range'),0),([[0x7ff0000000000000]],[0]*19,7)])]


class CudaText(fixed.CudaValues):
    cases=staticmethod(fixtures)
    emission_schema='nex.cuda-emission/5'
    value_schema='nex.cuda-values/4'
    emit_args=('--text-capacity','64','--byte-capacity','80','--list-capacity','4')

    def test_public_preparation_and_limits(self):
        self.source('module gpu;fn transform(code:str,message:str)->i64{return unwrap(err<i64>(code,message));}fn main()->unit{}');self.cli('check')
        self.assertEqual(self.cli('describe')['gpu_codegen']['cuda'],json.loads((fixed.harness.REPO/'llm/language-pack.json').read_text())['gpu_codegen']['cuda'])
        out=self.root/'prepared';cmd=[sys.executable,'-B',str(fixed.harness.REPO/'experiments/owned-cuda-codegen/prepare.py'),'--compiler',fixed.harness.NEX,'--resources',str(fixed.harness.REPO),'--source-project',str(self.root),'--symbol','transform','--source-only','--text-capacity','64','--output',str(out)]
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=90);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        r=json.loads((out/'preparation/report.json').read_bytes());self.assertEqual(r['value_abi']['parameter_words'],[9,9]);self.assertEqual(r['value_abi']['diagnostic_words'],18);self.assertEqual(r['maximum_batch_lanes'],32768//18)
        status=self.root/'status.cpp';words=T('X\0Y')+T('M\0🌍');literal=','.join('static_cast<long long>(0x%016xULL)'%(w%(1<<64))for w in words)
        status.write_text('#include '+json.dumps(str(out/'preparation/inputs/module.cpp'))+'\nint main(){std::vector<long long> p={'+literal+'};auto text=resultDiagnostic(p);if(text!=std::string("X\\0Y: M\\0",7)+"🌍")return 1;if(std::string(laneError(15))!="E_RESULT"||std::string(laneError(16))!="E_BOUNDS"||std::string(laneError(18))!="E_LIMIT")return 2;for(int bad=0;bad<3;++bad){auto q=p;if(bad==0)q[0]=-1;else if(bad==1)q[1]|=1LL<<40;else q[1]=255;bool rejected=false;try{(void)resultDiagnostic(q);}catch(const Error&e){rejected=e.code=="E_DEVICE_ABI";}if(!rejected)return 3;}return 0;}\n')
        doctor=self.cli('doctor');exe=self.root/('status.exe'if os.name=='nt'else'status');flags=['-std=c++20','-O1','-Wall','-Wextra','-Werror','-I'+str(fixed.harness.REPO/'runtime'),'-I'+str(out/'preparation/inputs')]
        if os.name=='nt':flags+=['--target='+doctor['host'],'--sysroot='+doctor['native_sysroot']]
        elif sys.platform!='darwin':flags+=['-ldl']
        p=subprocess.run([doctor['native_compiler'],*flags,str(status),'-o',str(exe)],capture_output=True,text=True,timeout=90);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        p=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        for value in ['0','32761','-1','1.5','999999999999999999','']:
            self.assertEqual(self.cli('emit','--kind','cuda','--entry','transform','--text-capacity',value,ok=False)['code'],'E_OPTION')
        self.assertEqual(self.cli('emit','--kind','metal','--entry','transform','--text-capacity','4',ok=False)['code'],'E_OPTION')
        self.source('module gpu;fn transform(s:str)->str{return s;}fn main()->unit{}');self.cli('check')
        self.assertEqual(self.cli('emit','--kind','cuda','--entry','transform','--text-capacity','32760')['value_abi']['result_words'],4096)
        self.source('module gpu;fn transform(s:str)->result<str>{return ok(s);}fn main()->unit{}');self.cli('check')
        self.assertEqual(self.cli('emit','--kind','cuda','--entry','transform','--text-capacity','32760',ok=False)['code'],'E_GPU_LIMIT')
        self.source('module gpu;fn transform(s:str)->i64{return unwrap(err<i64>(s+"!","failure🌍"));}fn main()->i64{return transform("custom");}')
        for args in [('eval',),('run','--profile','debug'),('run','--profile','release')]:
            r=self.cli(*args,ok=False,timeout=180)
            if args[0]=='eval':self.assertEqual(r['code'],'E_RESULT');self.assertEqual(r['message'],'custom!: failure🌍')
            else:self.assertEqual(r['exit_code'],70);self.assertIn('E_RESULT',r['stderr']);self.assertIn('custom!: failure🌍',r['stderr'])


if __name__=='__main__':
    unittest.main(argv=[__file__,'-v'])
