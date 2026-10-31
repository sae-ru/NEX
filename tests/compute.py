"""Checked tensors, real CPU semantics, provider dispatch/fallback and realm boundaries."""
import json
import os
import subprocess
from pathlib import Path
import unittest
import support as harness

IMPORT='module compute_test;import "std/compute.nex" as c;\n'
SETUP='''
fn job(kind:c::Kind,fallback:c::Fallback)->c::Request{
 let a:c::Tensor=unwrap(c::tensor(c::DType::U8(),[2],unwrap(bytes([1,2]))));
 let b:c::Tensor=unwrap(c::tensor(c::DType::U8(),[2],unwrap(bytes([3,4]))));
 return c::request("job",c::Operation::Add(),[a,b],c::Selection(kind,""),fallback);
}
fn device(id:str)->c::Device{return c::Device(c::Kind::GPU(),id,"controlled.test","1","test callback, no accelerator hardware",[c::Capability(c::OperationKind::Add(),c::DType::U8(),c::DType::U8())]);}
server fn never(request:c::Request,selected:c::Device)->result<c::Response>!{ffi}{assert(false);return err("NOT_REACHED","invalid dispatch");}
'''

class Compute(harness.ToolchainCase):
    def test_discovery_matches_pack_and_installed_guide(self):
        descriptor=self.cli('describe')['compute']
        pack=json.loads((harness.REPO/'llm/language-pack.json').read_text())
        self.assertEqual(descriptor,pack['compute'])
        self.assertEqual(self.cli('describe','--field','compute')['value'],descriptor)
        self.assertTrue(descriptor['context_wire'] is False)
        self.assertEqual(self.cli('guide','--kind','compute')['text'],(harness.REPO/'docs/compute.md').read_text())

    def test_cpu_library_agrees_native_typescript_reference_and_archived_source(self):
        self.source((harness.REPO/'examples/compute/main.nex').read_text())
        expected=self.cli('eval')['stdout'];self.assertIn('[16,-11,4,6]',expected)
        for profile in ['debug','release']:
            self.cli('test','--profile',profile,timeout=240)
            self.assertEqual(self.cli('run','--profile',profile,timeout=240)['stdout'],expected)
        self.cli('test','--target','web',timeout=180)
        build=self.cli('build','--profile','release',timeout=180)
        self.file.unlink()
        self.assertEqual(self.cli('run','--revision',build['revision'],'--profile','release',timeout=180)['stdout'],expected)

    def test_cpu_overflow_work_limits_and_unreachable_server_code(self):
        self.source(IMPORT+'''
fn repeated(size:i64)->bytes{var data:bytes=unwrap(bytes([128]));while len(data)<size{data=data+data;}return data;}
fn run(a:c::Tensor,b:c::Tensor)->result<c::Response>{return c::execute_cpu(c::request("limit",c::Operation::Matmul(),[a,b],c::Selection(c::Kind::CPU(),""),c::Fallback::Deny()));}
fn main()->unit!{io}{
 let data:bytes=repeated(131072);let a:c::Tensor=unwrap(c::tensor(c::DType::I8(),[1,131072],data));let b:c::Tensor=unwrap(c::tensor(c::DType::I8(),[131072,1],data));
 assert(error_code(run(a,b))=="E_COMPUTE_OVERFLOW");
 let large:bytes=data+data;let x:c::Tensor=unwrap(c::tensor(c::DType::I8(),[8,32768],large));let y:c::Tensor=unwrap(c::tensor(c::DType::I8(),[32768,8],large));
 assert(error_code(run(x,y))=="E_COMPUTE_LIMIT");
 let u:c::Tensor=unwrap(c::tensor(c::DType::U8(),[1],unwrap(bytes([255]))));let v:c::Tensor=unwrap(c::tensor(c::DType::U8(),[1],unwrap(bytes([1]))));
 let job:c::Request=c::request("overflow",c::Operation::Add(),[u,v],c::Selection(c::Kind::CPU(),""),c::Fallback::Deny());assert(error_code(c::execute_cpu(job))=="E_COMPUTE_OVERFLOW");
 assert(error_code(c::validate_request(c::request("range",c::Operation::Affine(9223372036854775807),[u,v],job.device,job.fallback)))=="E_COMPUTE_RANGE");
 print("CPU checked overflow and work limit OK");
}
''')
        expected=self.cli('eval','--steps','16000000',timeout=180)['stdout']
        self.assertEqual(self.cli('run','--profile','release',timeout=180)['stdout'],expected)
        folder=self.root/'typescript';self.cli('emit','--kind','typescript','--directory',folder)
        emitted=(folder/'program.ts').read_text()
        self.assertNotIn('provider changed correlation',emitted)
        self.assertNotIn('requested device is unavailable',emitted)
        (folder/'package.json').write_text('{"type":"module"}', newline="\n")
        (folder/'driver.ts').write_text("import {entry} from './program.ts';entry();", newline="\n")
        actual=subprocess.run([os.environ.get('NEX_NODE','node'),'--experimental-strip-types','--no-warnings',str(folder/'driver.ts')],capture_output=True,text=True,timeout=60)
        self.assertEqual(actual.returncode,0,actual.stderr);self.assertEqual(actual.stdout,expected)

    def test_explicit_fallback_and_errors_never_invoke_unavailable_provider(self):
        self.source(IMPORT+SETUP+'''
server fn main()->unit{}
server test fn unavailable()->unit!{ffi}{
 let ctx:c::Context=unwrap(c::context([],never));
 assert(error_code(c::execute(ctx,job(c::Kind::GPU(),c::Fallback::Deny())))=="E_COMPUTE_UNAVAILABLE");
 let result:c::Response=unwrap(c::execute(ctx,job(c::Kind::GPU(),c::Fallback::CPU())));
 assert(result.device.kind==c::Kind::CPU());assert(result.fallback_used);assert(result.fallback_reason!="");assert(result.output.data==unwrap(bytes([4,6])));
 let malformed:c::Request=job(c::Kind::GPU(),c::Fallback::CPU());
 assert(error_code(c::execute(ctx,c::Request(999,malformed.id,malformed.operation,malformed.inputs,malformed.device,malformed.fallback)))=="E_COMPUTE_VERSION");
 let invalid:c::Tensor=c::Tensor(c::DType::U8(),[2],unwrap(bytes([1])));
 assert(error_code(c::execute(ctx,c::request("bad",c::Operation::Add(),[invalid,invalid],malformed.device,malformed.fallback)))=="E_COMPUTE_SIZE");
}
server test fn malformed_context()->unit!{ffi}{
 let d:c::Device=device("test-gpu");assert(error_code(c::context([d,d],never))=="E_COMPUTE_DEVICE");
 assert(error_code(c::context([c::cpu_device()],never))=="E_COMPUTE_DEVICE");
 let wrong:c::Device=c::Device(d.kind,d.id,d.provider,d.version,d.provenance,[c::Capability(c::OperationKind::Matmul(),c::DType::U8(),c::DType::I32())]);
 assert(error_code(c::execute(c::Context([wrong],never),job(c::Kind::CPU(),c::Fallback::Deny())))=="E_COMPUTE_DEVICE");
}
''')
        self.cli('test',timeout=240)

    def test_provider_output_validation_and_selective_fallback(self):
        self.source(IMPORT+SETUP+'''
server fn reject(request:c::Request,selected:c::Device)->result<c::Response>!{ffi}{return err("E_TEST_FAULT","ordinary device failure");}
server fn unsupported(request:c::Request,selected:c::Device)->result<c::Response>!{ffi}{return err("E_COMPUTE_UNSUPPORTED","constraint");}
server fn lie(request:c::Request,selected:c::Device)->result<c::Response>!{ffi}{return c::execute_cpu(c::on(request,c::Selection(c::Kind::CPU(),""),c::Fallback::Deny()));}
server fn wrong_shape(request:c::Request,selected:c::Device)->result<c::Response>!{ffi}{return ok(c::Response(1,request.id,c::Tensor(c::DType::U8(),[3],unwrap(bytes([1,2,3]))),selected,false,""));}
server fn checked_callback(request:c::Request,selected:c::Device)->result<c::Response>!{ffi}{
 let reference:c::Response=c::execute_cpu(c::on(request,c::Selection(c::Kind::CPU(),""),c::Fallback::Deny()))?;
 return ok(c::Response(1,request.id,reference.output,selected,false,""));
}
server fn main()->unit{}
server fn response_checks()->unit!{ffi}{
 let devices:list<c::Device>=[device("test-gpu")];let request:c::Request=job(c::Kind::GPU(),c::Fallback::CPU());
 assert(error_code(c::execute(unwrap(c::context(devices,reject)),request))=="E_TEST_FAULT");
 assert(error_code(c::execute(unwrap(c::context(devices,lie)),request))=="E_COMPUTE_RESPONSE");
 assert(error_code(c::execute(unwrap(c::context(devices,wrong_shape)),request))=="E_COMPUTE_RESPONSE");
 let fallback:c::Response=unwrap(c::execute(unwrap(c::context(devices,unsupported)),request));assert(fallback.fallback_used);assert(fallback.device.kind==c::Kind::CPU());
 let matched:c::Response=unwrap(c::execute(unwrap(c::context(devices,checked_callback)),request));
 assert(!matched.fallback_used);assert(matched.device==devices[0]);assert(matched.output.data==unwrap(bytes([4,6])));
}
server test fn responses()->unit!{ffi}{response_checks();}
server test fn automatic_selection_skips_incapable_device()->unit!{ffi}{
 let first:c::Device=c::Device(c::Kind::GPU(),"wrong-cap","controlled.test","1","no hardware",[c::Capability(c::OperationKind::Matmul(),c::DType::I8(),c::DType::I32())]);
 let second:c::Device=device("right-cap");let ctx:c::Context=unwrap(c::context([first,second],checked_callback));
 let request:c::Request=job(c::Kind::GPU(),c::Fallback::Deny());assert(unwrap(c::execute(ctx,request)).device.id=="right-cap");
 assert(error_code(c::execute(ctx,c::on(request,c::Selection(c::Kind::GPU(),"wrong-cap"),c::Fallback::Deny())))=="E_COMPUTE_UNSUPPORTED");
}
''')
        self.cli('test',timeout=240)
        measured=self.cli('profile','--entry','response_checks','--scenario','compute context owned exits',timeout=240)
        profile=json.loads(Path(measured['output']).read_text())
        self.assertTrue(profile['ok'])
        for row in profile['memory']:self.assertEqual(row['live'],0);self.assertEqual(row['allocations'],row['frees'])

    def test_context_passive_capture_and_opaque_foreign_signature_follow_language_rules(self):
        self.source(IMPORT+SETUP+'''
server extern fn bounce(value:c::Context)->c::Context !{ffi}=foreign("audit","bounce","@PIN@");
server fn main()->unit{
 let ctx:c::Context=unwrap(c::context([],never));
 let values:list<i64>=parallel_map([1,2],server fn(value:i64)->i64{return value+len(ctx.devices);},2);
 assert(values==[1,2]);
}
'''.replace('@PIN@','0'*64))
        signature=self.cli('ffi','--symbol','bounce')
        self.assertTrue(any(t['kind']=='function' for t in signature['types']),signature)
        self.cli('eval');self.cli('run',timeout=180)
        self.source(IMPORT+SETUP+'''
server fn main()->unit{
 let ctx:c::Context=unwrap(c::context([],never));
 let values:list<i64>=parallel_map([1],server fn(value:i64)->i64{
  let result:result<c::Response>=ctx.invoke(job(c::Kind::CPU(),c::Fallback::Deny()),c::cpu_device());return value;},1);
}
''')
        self.assertEqual(self.cli('check',ok=False)['code'],'E_EFFECT')

    def test_typed_context_cannot_cross_wire_or_client_realm(self):
        cases=[('fn bad(v:c::Context)->str{return encode_json(v);}','E_GENERIC_BOUND'),
               ('client fn bad()->unit{let ignored:result<c::Context>=c::context([],never);}','E_REALM'),
               ('server fn bad(v:c::Context)->unit{let ignored:result<c::Response>=c::execute(v,job(c::Kind::CPU(),c::Fallback::Deny()));}','E_EFFECT'),
               ('fn bad()->result<c::Tensor>{return c::tensor(c::DType::I8(),[2],[1,2]);}','E_TYPE')]
        for body,code in cases:
            with self.subTest(code=code):
                self.source(IMPORT+SETUP+'fn main()->unit{}'+body)
                result=self.cli('check',ok=False)
                self.assertEqual(result['code'],code,result)

if __name__=='__main__':unittest.main()
