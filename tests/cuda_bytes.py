"""Packed immutable CUDA bytes, source trap order and canonical wire boundaries."""
import base64
import json
import os
import subprocess
import sys
import unittest
import cuda_values as fixed

CAPACITY=13
WIDTH=1+(CAPACITY+7)//8


def packed(values):
    data=bytes(values);assert len(data)<=CAPACITY
    data+=bytes((WIDTH-1)*8-len(data))
    return [len(values),*[int.from_bytes(data[i:i+8],'little',signed=True)for i in range(0,len(data),8)]]


def ints(values):
    assert len(values)<=16
    return [len(values),*values,*([0]*(16-len(values)))]


def fixtures():
    B=packed;zero=[0]*WIDTH
    return [
      ('identity', '''pub fn transform(b:bytes)->bytes{return b;}
test fn oracle()->unit{assert(transform(unwrap(bytes([0,255,128,65])))==unwrap(bytes([0,255,128,65])));}''',
       lambda ids: [([B([])],B([]),0),([B(range(13))],B(range(13)),0),([B([255]*13)],B([255]*13),0),([[-1,0,0]],zero,6),([[14,0,0]],zero,6),([[0,1,0]],zero,6),([[1,256,0]],zero,6),([[8,0,1]],zero,6),([[13,0,1<<40]],zero,6)]),
      ('ops', '''pub fn transform(b:bytes)->bytes{let saved:bytes=b;var c:bytes=b;c=set(c,0,255);let out:bytes=push(slice(c,0,len(c)),128)+unwrap(bytes([7]));assert(saved==b);return out;}
test fn oracle()->unit{let b:bytes=unwrap(bytes([1,2]));assert(transform(b)==unwrap(bytes([255,2,128,7])));assert(b[0]==1);}''',
       lambda ids: [([B([1,2])],B([255,2,128,7]),0),([B(range(11))],B([255,*range(1,11),128,7]),0),([B(range(12))],zero,14),([B(range(13))],zero,14),([B([])],zero,11)]),
      ('slice', '''pub fn transform(b:bytes,start:i64,count:i64)->bytes{return slice(b,start,count);}
test fn oracle()->unit{assert(transform(unwrap(bytes([0,255,128])),1,2)==unwrap(bytes([255,128])));assert(len(transform(unwrap(bytes([1])),1,0))==0);}''',
       lambda ids: [([B(range(13)),[7],[6]],B(range(7,13)),0),([B(range(13)),[13],[0]],B([]),0),([B([]),[0],[0]],B([]),0),([B([1]),[-1],[0]],zero,12),([B([1]),[0],[-1]],zero,12),([B([1]),[2],[0]],zero,12),([B([1]),[1],[1]],zero,12),([B([1]),[0],[9223372036854775807]],zero,12),([B([1]),[-9223372036854775808],[0]],zero,12)]),
      ('index', '''pub fn transform(b:bytes,i:i64)->i64{return b[i];}
test fn oracle()->unit{assert(transform(unwrap(bytes([0,255,128])),1)==255);}''',
       lambda ids: [([B(range(13)),[8]],[8],0),([B([255]),[0]],[255],0),([B([1]),[-1]],[0],11),([B([1]),[9223372036854775807]],[0],11),([B([]),[0]],[0],11)]),
      ('set_order', '''pub fn transform(b:bytes,i:i64,v:i64,d:i64)->bytes{return set(b,i,v/d);}
test fn oracle()->unit{assert(transform(unwrap(bytes([1,2])),1,255,1)==unwrap(bytes([1,255])));}''',
       lambda ids: [([B([1]),[0],[255],[1]],B([255]),0),([B([1]),[-1],[256],[1]],zero,11),([B([1]),[-1],[256],[0]],zero,2),([B([1]),[0],[256],[1]],zero,13),([B([1]),[0],[-1],[1]],zero,13),([B([1]),[0],[-9223372036854775808],[-1]],zero,1)]),
      ('push_order', '''pub fn transform(b:bytes,v:i64,d:i64)->bytes{return push(b,v/d);}
test fn oracle()->unit{assert(transform(unwrap(bytes([])),255,1)==unwrap(bytes([255])));}''',
       lambda ids: [([B(range(13)),[256],[0]],zero,2),([B(range(13)),[256],[1]],zero,13),([B(range(13)),[255],[1]],zero,14),([B(range(12)),[255],[1]],B([*range(12),255]),0)]),
      ('construct', '''pub fn transform(xs:list<i64>)->result<bytes>{return bytes(xs);}
test fn oracle()->unit{assert(transform([0,255,128])==ok(unwrap(bytes([0,255,128]))));assert(error_code(transform([256]))=="E_RANGE");assert(error_message(transform([-1]))=="byte value must be between 0 and 255");}''',
       lambda ids: [([ints([0,255,128])],[1,*B([0,255,128])],0),([ints([])],[1,*B([])],0),([ints([256])],[0,ids('E_RANGE'),ids('byte value must be between 0 and 255'),0],0),([ints([*range(13),-1])],[0,ids('E_RANGE'),ids('byte value must be between 0 and 255'),0],0),([ints(range(14))],[0]*4,14)]),
      ('propagate', '''pub fn transform(xs:list<i64>)->result<i64>{let b:bytes=bytes(xs)?;return ok(len(b));}
test fn oracle()->unit{assert(transform([0,255])==ok(2));assert(error_code(transform([-1]))=="E_RANGE");}''',
       lambda ids: [([ints([0,255])],[1,2,0],0),([ints([-1])],[0,ids('E_RANGE'),ids('byte value must be between 0 and 255')],0)]),
      ('snapshots', '''pub fn transform(b:bytes)->bytes{var a:bytes=b;let saved:bytes=a;a=set(a,0,7);assert(a!=saved);assert(saved==b);return saved;}
test fn oracle()->unit{assert(transform(unwrap(bytes([1,2])))==unwrap(bytes([1,2])));}''',
       lambda ids: [([B([1,2])],B([1,2]),0),([B([255]*13)],B([255]*13),0)]),
      ('nested', '''pub struct Frame{tag:bool;data:bytes;}
pub fn transform(f:result<Frame>)->result<Frame>{assert(len("E_USER")==6);assert(len("bad")==3);return match f{ok(Frame(true,b)) if len(b)>0=>ok(Frame(false,set(b,0,255))),ok(Frame(_,b))=>ok(Frame(true,b)),err(c,m)=>err<Frame>(c,m)};}
test fn oracle()->unit{assert(transform(ok(Frame(true,unwrap(bytes([1])))))==ok(Frame(false,unwrap(bytes([255])))));assert(transform(err<Frame>("E_USER","bad"))==err<Frame>("E_USER","bad"));}''',
       lambda ids: [([[1,1,*B([1])]],[1,0,*B([255])],0),([[1,0,*B([])]],[1,1,*B([])],0),([[0,ids('E_USER'),ids('bad'),0,0]],[0,ids('E_USER'),ids('bad'),0,0],0),([[1,2,*B([1])]],[0]*5,6),([[1,1,0,0,1]],[0]*5,6)]),
      ('concat', '''pub fn transform(a:bytes,b:bytes)->bytes{return a+b;}
test fn oracle()->unit{assert(transform(unwrap(bytes([1,2,3])),unwrap(bytes([255,128])))==unwrap(bytes([1,2,3,255,128])));}''',
       lambda ids: [([B(range(7)),B([255]*6)],B([*range(7),*([255]*6)]),0),([B(range(8)),B(range(5))],B([*range(8),*range(5)]),0),([B(range(13)),B([1])],zero,14),([B([]),B(range(13))],B(range(13)),0)]),
      ('utf8', '''pub fn transform(s:str)->bytes{assert(len("α🌍")==2);assert(len("abcdefghijklmno")==15);return utf8_bytes(s);}
test fn oracle()->unit{assert(transform("α🌍")==unwrap(bytes([206,177,240,159,140,141])));}''',
       lambda ids: [([[ids('α🌍')]],B('α🌍'.encode()),0),([[0]],B([]),0),([[ids('abcdefghijklmno')]],zero,14),([[999]],zero,6)]),
      ('base64', '''pub fn transform(s:str)->result<bytes>{assert(len("AP+AQQ==")==8);assert(len("Zh==")==4);assert(len("AAAAAAAAAAAAAAAAAAA=")==20);return decode_base64(s);}
test fn oracle()->unit{assert(transform("AP+AQQ==")==ok(unwrap(bytes([0,255,128,65]))));assert(error_code(transform("Zh=="))=="E_BASE64");assert(error_message(transform("Zh=="))=="invalid canonical base64");}''',
       lambda ids: [([[ids('AP+AQQ==')]],[1,*B([0,255,128,65])],0),([[0]],[1,*B([])],0),([[ids('Zh==')]],[0,ids('E_BASE64'),ids('invalid canonical base64'),0],0),([[ids('AAAAAAAAAAAAAAAAAAA=')]],[0]*4,14),([[999]],[0]*4,6)])]


class CudaBytes(fixed.CudaValues):
    cases=staticmethod(fixtures)
    emission_schema='nex.cuda-emission/4'
    value_schema='nex.cuda-values/3'
    emit_args=('--byte-capacity',str(CAPACITY),'--list-capacity','16')

    def test_public_preparation_and_limits(self):
        self.source('module gpu;fn transform(b:bytes)->bytes{return b;}fn main()->unit{}');self.cli('check')
        self.assertEqual(self.cli('describe')['gpu_codegen']['cuda'],json.loads((fixed.harness.REPO/'llm/language-pack.json').read_text())['gpu_codegen']['cuda'])
        self.assertEqual(self.cli('emit','--kind','cuda','--entry','transform')['value_abi']['parameter_words'],[33])
        for capacity,width in [(1,2),(8,2),(9,3),(32760,4096)]:
            abi=self.cli('emit','--kind','cuda','--entry','transform','--byte-capacity',str(capacity))['value_abi'];self.assertEqual(abi['result_words'],width);self.assertEqual(abi['byte_capacity'],capacity)
        for value in ['0','32761','-1','1.5','999999999999999999','']:
            self.assertEqual(self.cli('emit','--kind','cuda','--entry','transform','--byte-capacity',value,ok=False)['code'],'E_OPTION')
        self.assertEqual(self.cli('emit','--kind','metal','--entry','transform','--byte-capacity','4',ok=False)['code'],'E_OPTION')
        out=self.root/'prepared'
        p=subprocess.run([sys.executable,'-B',str(fixed.harness.REPO/'experiments/owned-cuda-codegen/prepare.py'),'--compiler',fixed.harness.NEX,'--resources',str(fixed.harness.REPO),'--source-project',str(self.root),'--symbol','transform','--source-only','--byte-capacity','13','--output',str(out)],capture_output=True,text=True,timeout=90)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        r=json.loads((out/'preparation/report.json').read_bytes());self.assertEqual(r['value_abi']['parameter_words'],[3]);self.assertEqual(r['maximum_batch_lanes'],32768//3)
        header=(out/'preparation/inputs/generated_kernel.h').read_text();self.assertIn('#define GENERATED_BYTE_VALUES 1',header);self.assertIn('#define GENERATED_LIST_VALUES 0',header)
        status=self.root/'status.cpp';status.write_text('#include '+json.dumps(str(out/'preparation/inputs/module.cpp'))+'\nint main(){if(std::string(laneError(11))!="E_BOUNDS"||laneMessage(11,0)!="byte index is outside buffer bounds"||std::string(laneError(12))!="E_BOUNDS"||laneMessage(12,0)!="slice is outside byte buffer bounds"||std::string(laneError(13))!="E_RANGE"||laneMessage(13,0)!="byte value must be between 0 and 255"||std::string(laneError(14))!="E_LIMIT"||laneMessage(14,0)!="device bytes exceed declared capacity")return 1;for(auto c:{7u,8u,9u,10u,15u,0xffffffffu}){bool bad=false;try{(void)laneError(c);}catch(const Error&e){bad=e.code=="E_DEVICE_ABI";}if(!bad)return 2;}return 0;}\n')
        doctor=self.cli('doctor');exe=self.root/('status.exe'if os.name=='nt'else'status');flags=['-std=c++20','-O1','-Wall','-Wextra','-Werror','-I'+str(fixed.harness.REPO/'runtime'),'-I'+str(out/'preparation/inputs')]
        if os.name=='nt':flags+=['--target='+doctor['host'],'--sysroot='+doctor['native_sysroot']]
        elif sys.platform!='darwin':flags+=['-ldl']
        p=subprocess.run([doctor['native_compiler'],*flags,str(status),'-o',str(exe)],capture_output=True,text=True,timeout=90);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        p=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        self.source('module gpu;fn transform(b:bytes)->result<bytes>{return ok(b);}fn main()->unit{}');self.cli('check')
        self.assertEqual(self.cli('emit','--kind','cuda','--entry','transform','--byte-capacity','32760',ok=False)['code'],'E_GPU_LIMIT')
        for body in ['fn transform(b:bytes)->result<str>{return decode_utf8(b);}','fn transform(b:bytes)->str{return encode_base64(b);}']:
            self.source('module gpu;'+body+'fn main()->unit{}');self.cli('check');self.assertEqual(self.cli('emit','--kind','cuda','--entry','transform',ok=False)['code'],'E_GPU_UNSUPPORTED')


if __name__=='__main__':
    unittest.main(argv=[__file__,'-v'])
