"""Fixed device values: actual emitted code, canonical wire data and NEX agreement."""
import hashlib
import itertools
import json
import os
from pathlib import Path
import struct
import subprocess
import sys
import unittest
import support as harness


def fword(x):
    return struct.unpack('<q', struct.pack('<d', x))[0]


def fixtures():
    return [
        ('record', '''pub struct Pair<T>{value:T;valid:bool;}
pub fn transform(p:Pair<f64>)->Pair<i64>{let saved:Pair<f64>=p;var changed:Pair<f64>=p;changed=Pair<f64>(0.0,false);return Pair<i64>(unwrap(as_i64(saved.value))+1,saved.valid);}
test fn oracle()->unit{assert(transform(Pair<f64>(41.75,true))==Pair<i64>(42,true));assert(transform(Pair<f64>(-1.75,false))==Pair<i64>(0,false));}''',
         lambda ids: [([[fword(41.75),1]],[42,1],0), ([[fword(-1.75),0]],[0,0],0), ([[fword(1e100),1]],[0,0],ids.fatal('E_RANGE','f64 value is outside i64 range')), ([[0x7ff8000000000001,2]],[0,0],7), ([[fword(1.0),2]],[0,0],6)]),
        ('enum', '''pub enum Item{Pair(n:i64,flag:bool);Empty;}
pub fn transform(v:Item)->result<Item>{return match v{Item::Pair(n,true) if n>=0=>ok(Item::Pair(n+1,false)),Item::Pair(_,_)=>err<Item>("NEG","bad 🌍"),Item::Empty()=>ok(Item::Empty())};}
test fn oracle()->unit{assert(transform(Item::Pair(41,true))==ok(Item::Pair(42,false)));assert(error_message(transform(Item::Pair(-1,false)))=="bad 🌍");assert(transform(Item::Empty())==ok(Item::Empty()));}''',
         lambda ids: [([[0,41,1]],[1,0,42,0],0), ([[0,-1,0]],[0,ids('NEG'),ids('bad 🌍'),0],0), ([[1,0,0]],[1,1,0,0],0), ([[1,9,0]],[0]*4,6), ([[2,0,0]],[0]*4,6), ([[0,41,2]],[0]*4,6)]),
        ('propagate', '''pub fn transform(v:result<i64>)->result<bool>{if !is_ok(v){assert(error_code(v)=="E_USER");assert(error_message(v)=="source error");}let n:i64=v?;return ok(n==42);}
test fn oracle()->unit{assert(transform(ok(42))==ok(true));assert(transform(ok(0))==ok(false));assert(transform(err<i64>("E_USER","source error"))==err<bool>("E_USER","source error"));}''',
         lambda ids: [([[1,42,0]],[1,1,0],0), ([[1,0,0]],[1,0,0],0), ([[0,ids('E_USER'),ids('source error')]],[0,ids('E_USER'),ids('source error')],0), ([[1,42,5]],[0]*3,6), ([[2,0,0]],[0]*3,6)]),
        ('convert', '''pub fn transform(x:f64)->result<i64>{return as_i64(x);}
test fn oracle()->unit{assert(transform(-1.75)==ok(-1));assert(transform(1.75)==ok(1));assert(transform(-9223372036854775808.0)==ok(-9223372036854775808));assert(error_code(transform(9223372036854775808.0))=="E_RANGE");}''',
         lambda ids: [([[fword(x)]],[1,n,0],0)for x,n in [(-1.75,-1),(1.75,1),(-0.0,0),(5e-324,0),(-9223372036854775808.0,-(1<<63)),(9223372036854774784.0,(1<<63)-1024)]] + [([[fword(x)]],[0,ids('E_RANGE'),ids('f64 value is outside i64 range')],0)for x in [9223372036854775808.0,-9223372036854777856.0,1e100]] + [([[0x7ff0000000000000]],[0]*3,7)]),
        ('text', '''pub fn transform(code:str)->i64{let r:result<i64>=err(code,"x🌍");return match r{err("α",message) if len(message)==2=>42,err(_,_)=>len(error_code(r)),ok(n)=>n};}
test fn oracle()->unit{assert(transform("α")==42);assert(transform("x🌍")==2);assert(transform("")==0);}''',
         lambda ids: [([[ids('α')]],[42],0), ([[ids('x🌍')]],[2],0), ([[0]],[0],0), ([[999]],[0],6)]),
        ('fatal', '''fn bad()->result<i64>{return err<i64>("E_USER","bad");}
pub fn transform(x:bool)->i64{if x{return unwrap(bad());}return match ok(42){ok(n) if false=>1/0,ok(n)=>n,err(_,_)=>0};}
test fn oracle()->unit{assert(transform(false)==42);}''',
         lambda ids: [([[1]],[0],ids.fatal('E_USER','bad')), ([[0]],[42],0), ([[2]],[0],6)]),
        ('unit', '''pub fn transform(x:bool)->unit{let r:result<i64>=ok(1);assert(is_ok(r));assert(unwrap(r)==1);assert(x);}
test fn oracle()->unit{transform(true);}''' ,
         lambda ids: [([[1]],[0],0), ([[0]],[0],3)]),
        ('empty', '''pub struct Empty{}
pub fn transform(x:bool)->result<Empty>{let a:Empty=Empty();let b:Empty=a;assert(a==b);return ok(b);}
test fn oracle()->unit{assert(transform(true)==ok(Empty()));}''',
         lambda ids: [([[1]],[1,0,0],0), ([[0]],[1,0,0],0)])]


class IDs:
    def __init__(self, values):
        self.values = values
    def __call__(self, value):
        return self.values.index(value)
    def fatal(self, code, message):
        return 0x80000000 | self(code)<<10 | self(message)


class CudaValues(harness.ToolchainCase):
    def test_values_wire_execution_and_existing_source_backends(self):
        self.source('module oracle;fn main()->unit{}')
        imports, definitions, runs, expected = [], [], [], []
        cpp = ['#include <iostream>\n#include <bit>\n#include <cfenv>\n#define __device__\n#define __global__\n']
        for i, (name, body, vectors) in enumerate(fixtures()):
            source = self.root / (name+'.nex')
            source.write_text('module case'+str(i)+';'+body+'\nfn main()->unit{}\n', encoding='utf-8')
            imports.append('import "./'+name+'.nex" as c'+str(i)+';')
            self.cli('check', source)
            for layout in ['rows','columns']:
                shader = self.root / (name+'-'+layout+'.cu')
                r = self.cli('emit', source, '--kind', 'cuda', '--entry', 'transform', '--input-layout', layout, '-o', shader)
                self.assertEqual(r['schema'], 'nex.cuda-emission/2')
                abi = r['value_abi'];rows=vectors(IDs(abi['text_pool']));widths=abi['parameter_words'];width=abi['result_words'];count=len(rows)
                self.assertEqual(abi['schema'],'nex.cuda-values/1')
                self.assertTrue(abi['inactive_words_zero'])
                self.assertEqual(r['shader_sha256'],hashlib.sha256(shader.read_bytes()).hexdigest())
                self.assertTrue(all([len(x)for x in row[0]]==widths and len(row[1])==width for row in rows))
                words=[w for row in rows for column in row[0] for w in column] if layout=='rows' else [w for p in range(len(widths)) for row in rows for w in row[0][p]]
                ns='v'+str(len(expected));cpp.append('#define nex_generated_cuda_map host_kernel_'+ns+'\nnamespace '+ns+'{struct Index{unsigned x;};Index blockIdx,blockDim,threadIdx;\n#include '+json.dumps(str(shader))+'\n}\n#undef nex_generated_cuda_map\n')
                literals=','.join(ns+'::nex_bits(0x%016xULL)'%(w%(1<<64))for w in words)or'0LL'
                out_count=(count+3)*width
                pointers=['input']if layout=='rows'else['input+'+str(count*sum(widths[:p]))for p in range(len(widths))]
                call=','.join([*pointers,'output','errors',str(count)+'U','65536U'])
                code='{long long input[]={'+literals+'};long long original[]={'+literals+'};long long output['+str(out_count)+'];unsigned errors['+str(count+3)+'];'
                code+='for(unsigned i=0;i<'+str(out_count)+'U;++i)output[i]=123456789LL;for(unsigned i=0;i<'+str(count+3)+'U;++i)errors[i]=98765U;'
                code+=ns+'::blockDim.x=128;for(unsigned lane=0;lane<'+str(count+256)+'U;++lane){'+ns+'::blockIdx.x=lane/128;'+ns+'::threadIdx.x=lane%128;'+ns+'::host_kernel_'+ns+'('+call+');}'
                code+='for(unsigned i=0;i<'+str(max(1,len(words)))+'U;++i)if(input[i]!=original[i])return 22;'
                code+=('std::cout<<",";'if expected else'')+'std::cout<<'+json.dumps('{"values":[')+';'
                code+='for(unsigned i=0;i<'+str(out_count)+'U;++i){if(i)std::cout<<",";std::cout<<output[i];}std::cout<<'+json.dumps('],"errors":[')+';'
                code+='for(unsigned i=0;i<'+str(count+3)+'U;++i){if(i)std::cout<<",";std::cout<<errors[i];}std::cout<<'+json.dumps(']}')+';}\n'
                runs.append(code);expected.append({'values':[x for row in rows for x in row[1]]+[123456789]*(3*width),'errors':[row[2]for row in rows]+[98765]*3})
        cpp.append('int main(){std::cout<<"[";'+''.join(runs)+'std::cout<<"]\\n";}\n')
        path=self.root/'host.cpp';path.write_text(''.join(cpp));exe=self.root/('host.exe'if os.name=='nt'else'host')
        doctor=self.cli('doctor');flags=['-std=c++20','-O1']
        if os.name=='nt':flags+=['--target='+doctor['host'],'--sysroot='+doctor['native_sysroot']]
        else:flags+=['-fsanitize=undefined','-fno-sanitize-recover=all']
        result=subprocess.run([doctor['native_compiler'],*flags,str(path),'-o',str(exe)],capture_output=True,text=True,timeout=90)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        result=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20)
        self.assertEqual(result.returncode,0,result.stdout+result.stderr)
        self.assertEqual(json.loads(result.stdout),expected)
        self.file.write_text('module oracle;'+''.join(imports)+'fn main()->unit{}')
        for args in [('test','--interpreter-only'),('test','--profile','release'),('test','--target','web')]:
            result=self.cli(*args,timeout=180)
            self.assertEqual(len(result['tests']),len(fixtures()))

    def test_public_preparation_and_limits(self):
        self.source('''module gpu;pub struct Pair{n:i64;b:bool;}
fn transform(p:Pair)->result<Pair>{return ok(p);}fn main()->unit{}''')
        self.cli('check')
        out=self.root/'prepared'
        cmd=[sys.executable,'-B',str(harness.REPO/'experiments/owned-cuda-codegen/prepare.py'),'--compiler',harness.NEX,'--resources',str(harness.REPO),'--source-project',str(self.root),'--symbol','transform','--source-only','--output',str(out)]
        p=subprocess.run(cmd,capture_output=True,text=True,timeout=90)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        r=json.loads((out/'preparation/report.json').read_bytes())
        self.assertEqual(r['value_abi']['parameter_words'],[2]);self.assertEqual(r['value_abi']['result_words'],3)
        self.assertEqual(r['maximum_batch_lanes'],32768//3);self.assertEqual(len(r['signature_sha256']),11)
        text=(out/'preparation/inputs/generated_kernel.h').read_text()
        self.assertIn('#define GENERATED_ARGUMENT_WORDS {2}',text);self.assertIn('#define GENERATED_OUTPUT_WORDS 3',text)
        status_source=self.root/'status.cpp'
        status_source.write_text('#include '+json.dumps(str(out/'preparation/inputs/module.cpp'))+'\nint main(){if(std::string(laneError(0x80000000u))!="E_RESULT"||laneMessage(0x80000000u,0)!=": ")return 1;for(auto c:{0x40000000u,0x80100000u,0x80000400u,0xffffffffu}){bool bad=false;try{(void)laneError(c);}catch(const Error&e){bad=e.code=="E_DEVICE_ABI";}if(!bad)return 2;}return 0;}\n')
        doctor=self.cli('doctor');exe=self.root/('status.exe'if os.name=='nt'else'status')
        flags=['-std=c++20','-O1','-Wall','-Wextra','-Werror','-I'+str(harness.REPO/'runtime'),'-I'+str(out/'preparation/inputs')]
        if os.name=='nt':flags+=['--target='+doctor['host'],'--sysroot='+doctor['native_sysroot']]
        elif sys.platform!='darwin':flags+=['-ldl']
        p=subprocess.run([doctor['native_compiler'],*flags,str(status_source),'-o',str(exe)],capture_output=True,text=True,timeout=90)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        p=subprocess.run([str(exe)],capture_output=True,text=True,timeout=20);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        # Width, recursive value and text bounds are compiler errors, not a
        # silent representation change or a fallback to host execution.
        too_wide='pub struct Wide{'+''.join('field_'+str(i)+':i64;'for i in range(65))+'}'
        for body,code in [(too_wide+'fn transform(v:Wide)->Wide{return v;}','E_GPU_LIMIT'),('fn transform(v:str)->str{return v+"x";}','E_GPU_UNSUPPORTED'),('fn transform(v:bool)->str{return "A\\u0000B";}','E_GPU_LIMIT')]:
            self.source('module rejected;'+body+'fn main()->unit{}');self.cli('check')
            r=self.cli('emit','--kind','cuda','--entry','transform',ok=False);self.assertEqual(r['code'],code)


if __name__=='__main__':
    unittest.main(argv=[__file__,'-v'])
