"""Real C API/source ownership and typed CUDA outcomes; explicit CPU fixture."""
import hashlib
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import unittest
import support as h
from host_fixture import run_native

HELPERS='''
fn column(mode:i64,count:i64)->bytes{var out:bytes=unwrap(bytes([]));var i:i64=0;while i<count{out=out+unwrap(bytes([mode,0,0,0,0,0,0,0]));i=i+1;}return out;}
fn long_code()->str{var out:str="";var i:i64=0;while i<50{out=out+"源";i=i+1;}return out;}
fn long_message()->str{var out:str="";var i:i64=0;while i<500{out=out+"msg🌍";i=i+1;}return out;}
'''


class CudaOutcomes(h.ToolchainCase):
    def test_typed_dispatch_ownership_and_fatal_source_semantics(self):
        self.source('module kernel;fn transform(x:f64,y:f64)->f64{if x<0.0{return unwrap(err<f64>("CUSTOM","runtime message: 🌍"));}return x+y;}fn main()->unit{}')
        project=self.root/'prepared'
        p=run_native([sys.executable,'-B',h.REPO/'experiments/owned-cuda-codegen/prepare.py','--compiler',h.NEX,'--resources',h.REPO,'--source-project',self.root,'--symbol','transform','--source-only','--text-capacity','4096','--output',project],capture_output=True,text=True,timeout=90)
        self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        prepared=json.loads((project/'preparation/report.json').read_bytes());self.assertEqual(len(prepared['signature_sha256']),11);self.assertTrue(prepared['all_f64_interface'])
        inputs=project/'preparation/inputs';bundle=project/'bundle';bundle.mkdir();doctor=self.cli('doctor')
        binary=bundle/('module.dll'if os.name=='nt'else'module.so')
        flags=['-std=c++20','-O1','-shared','-fPIC','-fvisibility=hidden','-pthread','-Wall','-Wextra','-Werror','-I'+str(h.REPO/'runtime'),'-I'+str(inputs)]
        if os.name=='nt':flags+=['--target='+doctor['host'],'--sysroot='+doctor['native_sysroot']]
        elif sys.platform!='darwin':flags+=['-ldl']
        p=run_native([doctor['native_compiler'],*flags,h.REPO/'tests/cuda_outcome_fixture.cpp','-o',binary],capture_output=True,text=True,timeout=90);self.assertEqual(p.returncode,0,p.stdout+p.stderr)
        (bundle/'NOTICE').write_bytes((h.REPO/'LICENSE').read_bytes()+b'\n'+(h.REPO/'runtime/third_party/JSON-LICENSE.MIT').read_bytes())
        sha=lambda path:hashlib.sha256(Path(path).read_bytes()).hexdigest()
        machine={'aarch64':'arm64','arm64':'arm64','AMD64':'x86_64','x86_64':'x86_64'}[platform.machine()]
        manifest={'schema':'nex.foreign-bundle/1','platform':{'Darwin':'macos','Linux':'linux','Windows':'windows'}[platform.system()]+'-'+machine,'entry':binary.name,'files':[{'path':name,'sha256':sha(bundle/name)}for name in [binary.name,'NOTICE']],'exports':prepared['signature_sha256'],'notices':['NOTICE']}
        (bundle/'manifest.json').write_text(json.dumps(manifest)+'\n');pin=sha(bundle/'manifest.json')
        foreign=project/'foreign.json';foreign.write_text(json.dumps({'schema':'nex.foreign-host/1','module_limit':1,'resource_limit':64,'resource_bytes':16777216,'libraries':{'gpu':{'directory':'./bundle','manifest_sha256':pin,'exports':list(prepared['signature_sha256'])}}})+'\n')
        prefix=(project/'main.nex').read_text().split('server fn main()->unit',1)[0].replace('0'*64,pin)+HELPERS
        good='''
 let session:d::Session=unwrap(make_context());let zero:bytes=column(0,1);
 assert(unwrap(decode_f64s(unwrap(try_apply(session,[zero,zero],1,64))))==[42.0]);
 let short:result<bytes>=try_apply(session,[column(1,1),zero],1,64);assert(error_code(short)=="E_RESULT");assert(error_message(short)=="CUSTOM: runtime message: 🌍");
 let nul:result<bytes>=try_apply(session,[column(2,1),zero],1,64);assert(error_message(nul)=="source\\u0000code: before\\u0000after🌍");
 let large:result<bytes>=try_apply(session,[column(3,1),zero],1,64);assert(error_message(large)==long_code()+": "+long_message());assert(len(utf8_bytes(error_message(large)))>2048);
 assert(error_code(try_apply(session,[column(4,1),zero],1,64))=="E_GPU_INPUT");
 assert(error_code(try_apply(session,[zero,column(8,1)],1,64))=="E_GPU_INPUT");
 let n:i64=kernel_batch_lanes()+1;let multi:result<bytes>=try_apply(session,[column(6,n),column(0,n)],n,64);assert(error_message(multi)=="CUSTOM: runtime message: 🌍");
 assert(error_message(short)=="CUSTOM: runtime message: 🌍");assert(error_message(nul)=="source\\u0000code: before\\u0000after🌍");
 assert(unwrap(try_apply_f64(session,[[0.0],[0.0]],1,64))==[42.0]);assert(error_code(try_apply_f64(session,[[5e-324],[0.0]],1,64))=="E_RESULT");
 assert(apply_f64(session,[[0.0],[0.0]],1,64)==[42.0]);assert(resource_close(session));print(42);
'''
        cases=[('managed',good,None,None)]
        for name,mode,code,message in [('short',1,'"CUSTOM"','"runtime message: 🌍"'),('nul',2,'"source\\u0000code"','"before\\u0000after🌍"'),('long',3,'long_code()','long_message()')]:
            body='let session:d::Session=unwrap(make_context());print("before");try{apply(session,[column('+str(mode)+',1),column(0,1)],1,64);}catch(c,m){print("caught");}finally{print("finally");}print("after");'
            baseline='print("before");let failed:bytes=unwrap(err<bytes>('+code+','+message+'));print(len(failed));'
            cases.append((name,body,'E_RESULT',baseline))
        cases.append(('f64-fault','let session:d::Session=unwrap(make_context());print("before");try{apply_f64(session,[[5e-324],[0.0]],1,64);}catch(c,m){print("caught");}finally{print("finally");}','E_RESULT','print("before");let failed:bytes=unwrap(err<bytes>("CUSTOM","runtime message: 🌍"));print(len(failed));'))
        cases.append(('host-fault','let session:d::Session=unwrap(make_context());print("before");try{apply(session,[column(4,1),column(0,1)],1,64);}catch(c,m){print("caught");}finally{print("finally");}','E_GPU_INPUT',None))
        for name,body,error,baseline in cases:
            if baseline:
                (project/'main.nex').write_text(prefix+'server fn main()->unit !{task,ffi,io,throw}{'+baseline+'}')
                expected=self.cli('eval','--foreign',foreign,'--task-workers','1',cwd=project,ok=False,timeout=180)
                self.assertEqual(expected['code'],'E_RESULT')
            (project/'main.nex').write_text(prefix+'server fn main()->unit !{task,ffi,io,throw}{'+body+'}')
            self.cli('check',cwd=project)
            for backend,args in [('reference',('eval',)),('debug',('run','--profile','debug')),('release',('run','--profile','release'))]:
                event_path=self.root/(name+'-'+backend+'.jsonl')
                value=self.cli(*args,'--foreign',foreign,'--task-workers','1','--task-steps','16000000','--task-timeout-ms','60000',cwd=project,env={'NEX_CUDA_OUTCOME_EVENTS':str(event_path)},ok=error is None,timeout=180)
                self.assertEqual(value['stdout'],'42\n'if error is None else'before\n')
                if error:
                    if backend=='reference':
                        self.assertEqual(value['code'],error)
                        if baseline:self.assertEqual(value['message'],expected['message'])
                    else:
                        self.assertEqual(value['exit_code'],70);self.assertIn(error,value['stderr'])
                        if baseline:self.assertIn(expected['message'],value['stderr'])
                        self.assertNotIn('E_FFI_',value['stderr'])
                rows=[json.loads(line)for line in event_path.read_text().splitlines()]
                created=[row['id']for row in rows if row['event']=='create'];destroyed=[row['id']for row in rows if row['event']=='destroy']
                self.assertEqual(sorted(created),sorted(destroyed));self.assertEqual(len(destroyed),len(set(destroyed)))
                self.assertTrue(rows);self.assertFalse(any(row['actual_GPU']for row in rows))
                self.assertEqual(any(row['event']=='host_fatal'for row in rows),name=='host-fault')
                if name!='host-fault':self.assertTrue(any(row['event']=='fault_published'for row in rows))
                for published,row in enumerate(rows):
                    if row['event']=='fault_published':
                        settled=max(i for i in range(published)if rows[i]['event']=='settled')
                        identity=rows[settled]['id']
                        destroyed=next(i for i in range(settled+1,published)if rows[i]['event']=='destroy'and rows[i]['id']==identity)
                        self.assertLess(settled,destroyed);self.assertLess(destroyed,published)
                self.assertEqual([row['kind']for row in rows if row['event']=='destroy'][-1],0)


if __name__=='__main__':unittest.main(argv=[__file__,'-v'])
