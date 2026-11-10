"""Exercise real typed f64 C FFI codecs/fatal transport without a CUDA driver."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import struct
import subprocess
import sys


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ['compiler','resources','emitter','frontend-archive','cxx','output']:
        parser.add_argument('--'+name,required=True,type=Path)
    args=parser.parse_args()
    if platform.system()!='Darwin':parser.error('these explicit unavailable-driver host controls currently require macOS')
    compiler,resources,emitter,frontend,cxx=[p.resolve(strict=True)for p in [args.compiler,args.resources,args.emitter,args.frontend_archive,args.cxx]]
    out=args.output.resolve();out.mkdir(exist_ok=False)
    source=Path(__file__).resolve().parent
    sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
    pins={str(p):sha(p)for p in [compiler,emitter,frontend,Path(__file__).resolve(),*[source/n for n in ['prepare.py','module.cpp','main.nex.in','context_probe.cpp']]]}
    env={k:v for k,v in os.environ.items()if not k.startswith(('NEX_','PYTHON','DYLD_','LD_'))};env.update(NEX_RESOURCE_DIR=str(resources),PYTHONDONTWRITEBYTECODE='1')
    report={'schema':'nex.experimental-owned-CUDA-f64-host-controls/1','ok':False,'commands':[],'cases':[],
        'compiler_sha256':sha(compiler),'source_input_pins':pins,'actual_GPU_execution':False,'actual_CUDA_contexts_allocations_launches':0}
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    def run(label,argv,cwd=out,expected=0,trace=None):
        assert all(sha(p)==h for p,h in pins.items())
        row={'label':label,'argv':list(map(str,argv))};report['commands'].append(row);save()
        value=subprocess.run(row['argv'],cwd=cwd,env={**env,**({'NEX_OWNED_CUDA_MAP_TRACE':str(trace)}if trace else{})},capture_output=True,timeout=600)
        (out/(label+'.stdout')).write_bytes(value.stdout);(out/(label+'.stderr')).write_bytes(value.stderr);row['exit_code']=value.returncode;save()
        assert value.returncode==expected,(label,value.stdout[-3000:],value.stderr[-3000:]);return value
    try:
        fixture=out/'fixture';fixture.mkdir();(fixture/'nex.json').write_text(json.dumps({'schema':'nex.project/1','language':'0.28','entry':'main.nex'})+'\n')
        (fixture/'main.nex').write_text('module float_source;pub fn transform(x:f64,y:f64)->f64{return x/y;}\n')
        project=out/'prepared'
        run('prepare',[sys.executable,'-B',source/'prepare.py','--compiler',compiler,'--resources',resources,'--emitter',emitter,'--frontend-archive',frontend,'--source-project',fixture,'--symbol','transform','--source-only','--output',project])
        prep=json.loads((project/'preparation/report.json').read_bytes());assert prep['all_f64_interface']and prep['f64_transport']['implemented']and len(prep['signature_sha256'])==11 and not prep['native_provider_built']and not prep['driver_initialized']
        inputs=project/'preparation/inputs';bundle=project/'bundle';bundle.mkdir();sdk=run('apple-sdk',['/usr/bin/xcrun','--sdk','macosx','--show-sdk-path']).stdout.decode().strip()
        flags=[cxx,'-isysroot',sdk,'-std=c++20','-O1','-g','-pthread','-Wall','-Wextra','-Werror','-I'+str(resources/'runtime'),'-I'+str(inputs)]
        run('module-build',[*flags,'-shared','-fPIC','-fvisibility=hidden',inputs/'module.cpp','-o',bundle/'module.so'])
        probe=out/'context-probe';run('probe-build',[*flags,inputs/'context_probe.cpp','-o',probe])
        lane=json.loads(run('lane-status-host',[probe,'--check-lane-status']).stdout);assert lane['ok']and lane['floating_point']and lane['actual_CUDA_contexts']==0 and not lane['actual_kernel_status_observed']
        unavailable=json.loads(run('probe-unavailable',[probe,'--expect-unavailable']).stdout);assert unavailable['scope']=='unavailable-driver-host-control'and not unavailable['physical_CUDA_context_probe_passed']
        (bundle/'NOTICE').write_bytes((resources/'LICENSE').read_bytes()+b'\n'+(resources/'runtime/third_party/JSON-LICENSE.MIT').read_bytes())
        manifest={'schema':'nex.foreign-bundle/1','platform':'macos-arm64'if platform.machine().lower()in ['arm64','aarch64']else'macos-x86_64','entry':'module.so',
            'files':[{'path':n,'sha256':sha(bundle/n)}for n in ['module.so','NOTICE']],'exports':prep['signature_sha256'],'notices':['NOTICE']}
        (bundle/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');pin=sha(bundle/'manifest.json')
        foreign=project/'foreign.json';foreign.write_text(json.dumps({'schema':'nex.foreign-host/1','module_limit':1,'resource_limit':64,'resource_bytes':16777216,
            'libraries':{'gpu':{'directory':'./bundle','manifest_sha256':pin,'exports':list(prep['signature_sha256'])}}},indent=2)+'\n')
        prefix=(project/'main.nex').read_text().split('server fn main()->unit',1)[0].replace('0'*64,pin)
        values=[0.0,-0.0,1.0,-1.25,5e-324,-5e-324,1.7976931348623157e308,-1.7976931348623157e308]
        literals=','.join(repr(v)for v in values);encoded=list(b''.join(struct.pack('<d',0.0 if v==0 else v)for v in values))
        body='''
 let values:list<f64>=[@VALUES@];let expected:bytes=unwrap(bytes(@BYTES@));
 let encoded:bytes=unwrap(encode_f64s(values));assert(encoded==expected);assert(unwrap(decode_f64s(encoded))==values);
 assert(unwrap(encode_f64_raw(values,1,2))==slice(encoded,8,16));assert(unwrap(decode_f64_raw(encoded,2,2))==[1.0,-1.25]);
 assert(unwrap(encode_f64_raw([],0,0))==unwrap(bytes([])));assert(unwrap(decode_f64_raw(unwrap(bytes([])),0,0))==[]);
 assert(unwrap(encode_f64s([]))==unwrap(bytes([])));assert(unwrap(decode_f64s(unwrap(bytes([]))))==[]);
 let nz:bytes=unwrap(bytes([0,0,0,0,0,0,0,128]));assert(unwrap(decode_f64s(nz))==[0.0]);assert(unwrap(encode_f64s(unwrap(decode_f64s(nz))))==unwrap(bytes([0,0,0,0,0,0,0,0])));
 var changed:list<f64>=[1.0,2.0];let snapshot:list<f64>=changed;changed=set(changed,0,3.0);assert(unwrap(decode_f64s(unwrap(encode_f64s(snapshot))))==[1.0,2.0]);assert(changed==[3.0,2.0]);
 assert(error_code(encode_f64_raw(values,-1,1))=="E_GPU_INPUT");assert(error_code(encode_f64_raw(values,0,-1))=="E_GPU_INPUT");assert(error_code(encode_f64_raw(values,0,1025))=="E_GPU_INPUT");assert(error_code(encode_f64_raw(values,9223372036854775807,1))=="E_GPU_INPUT");
 assert(error_code(decode_f64_raw(encoded,-1,1))=="E_GPU_INPUT");assert(error_code(decode_f64_raw(encoded,0,1025))=="E_GPU_INPUT");assert(error_code(decode_f64_raw(encoded,9223372036854775807,1))=="E_GPU_INPUT");assert(error_code(decode_f64s(unwrap(bytes([1]))))=="E_GPU_INPUT");
 @NONFINITE@
 var large:list<f64>=[1.25];var n:i64=0;while n<15{large=large+large;n=n+1;}
 let data:bytes=unwrap(encode_f64s(large));assert(len(data)==262144);assert(unwrap(decode_f64s(data))==large);
 var chunk:list<f64>=[1.25];n=0;while n<10{chunk=chunk+chunk;n=n+1;}
 assert(len(unwrap(encode_f64_raw(chunk,0,1024)))==8192);assert(len(unwrap(decode_f64_raw(slice(data,253952,8192),0,1024)))==1024);
 assert(error_code(encode_f64s(large+[1.0]))=="E_GPU_INPUT");assert(error_code(encode_f64_raw(chunk+[1.0],0,1))=="E_GPU_INPUT");
 assert(error_code(decode_f64s(data+unwrap(bytes([0,0,0,0,0,0,0,0]))))=="E_GPU_INPUT");
 assert(error_code(make_context())=="E_COMPUTE_UNAVAILABLE");print(42);
'''.replace('@VALUES@',literals).replace('@BYTES@',str(encoded))
        bad=[]
        for bits in [0x7ff0000000000000,0xfff0000000000000,0x7ff8000000000001,0x7ff0000000000001]:
            data=list(bits.to_bytes(8,'little'));bad.append('assert(error_code(decode_f64s(unwrap(bytes('+str(data)+'))))=="E_FLOAT");')
        body=body.replace('@NONFINITE@',''.join(bad))
        fatal='try{fatal_raw("E_FLOAT","controlled codec host trap");}catch(code,message){print(98);}finally{print(99);}'
        relay='let error:result<list<f64>>=decode_f64s(unwrap(bytes([1,0,0,0,0,0,248,127])));assert(!is_ok(error));try{fatal_raw(error_code(error),error_message(error));}catch(code,message){print(98);}finally{print(99);}'
        for name,program,error in [('codecs',body,None),('fatal',fatal,'E_FLOAT'),('relay',relay,'E_FLOAT')]:
            text=prefix+'\nserver fn main()->unit !{task,ffi,io,throw}{'+program+'}\n';(project/'main.nex').write_text(text)
            checked=json.loads(run(name+'-check',[compiler,'check','--json'],project).stdout);traces=[]
            reference_trace=out/(name+'-reference.trace.jsonl');value=json.loads(run(name+'-reference',[compiler,'eval','--foreign',foreign,'--task-workers','1','--task-steps','16000000','--task-timeout-ms','60000','--json'],project,1 if error else 0,reference_trace).stdout)
            assert value['stdout']==(''if error else'42\n')
            if error:assert value['code']==error
            else:assert value['foreign_resource_bytes_after_scope']==0
            traces.append(reference_trace)
            for mode in ['debug','release']:
                built=json.loads(run(name+'-build-'+mode,[compiler,'build','--profile',mode,'--task-workers','1','--task-steps','16000000','--task-timeout-ms','60000','--build-directory',out/('native-'+mode),'--json'],project).stdout)
                trace=out/(name+'-'+mode+'.trace.jsonl');native=run(name+'-native-'+mode,[built['executable'],'--nex-foreign',foreign,'--nex-task-workers','1'],project,70 if error else 0,trace)
                assert native.stdout==(b''if error else b'42\n')
                if error:assert error.encode()in native.stderr
                else:assert not native.stderr
                traces.append(trace)
            for trace in traces:
                rows=[json.loads(line)for line in trace.read_text().splitlines()];assert rows[-1]['event']=='module_unloaded'and rows[-1]['physical_completion_verified']and all(v==0 for v in rows[-1]['ledger'].values())
            report['cases'].append({'name':name,'checked_revision':checked['revision'],'backends':['reference','native-debug','native-release'],'expected_error':error,'zero_CUDA_resources_and_balanced_cleanup':True});save()
        report.update(ok=True,checked_signatures=11,typed_maximum_values=32768,per_call_chunk_values=1024,standard_C_call_limits_preserved=True,
            exact_little_endian_bytes_and_positive_zero=True,NaN_infinity_and_shape_rejected=True,immutable_input_snapshots_preserved=True,
            actual_E_FLOAT_fatal_bypasses_source_catch_and_finally=True,actual_native_GPU_lane_status_observed=False,
            module_sha256=sha(bundle/'module.so'),manifest_sha256=pin,actual_CXX_lane_mapping_host_control=lane,
            native_f64_provider_or_SDK_accepted=False)
    except BaseException as error:report['error']=repr(error);raise
    finally:save()
    print(json.dumps({k:report[k]for k in ['ok','checked_signatures','typed_maximum_values','per_call_chunk_values','actual_E_FLOAT_fatal_bypasses_source_catch_and_finally','actual_GPU_execution']}))


if __name__=='__main__':main()
