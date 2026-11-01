"""Require actual NEX->CUDA execution and physical cleanup on native Windows."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import runpy
import shutil
import subprocess
import time

ROOT=Path(__file__).resolve().parents[2]
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def write(path,value):path.write_bytes((json.dumps(value,ensure_ascii=False,indent=2)+'\n').encode('utf-8'))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',type=Path,required=True)
    parser.add_argument('--project',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--only',action='append')
    args=parser.parse_args()
    if os.name!='nt':parser.error('use native Windows Python')
    compiler=args.compiler.resolve(strict=True);project=args.project.resolve(strict=True);out=args.output.resolve()
    out.mkdir(parents=True,exist_ok=False)
    shared=runpy.run_path(str(Path(__file__).resolve().parents[1]/'owned-opencl/verify.py'))
    cases=dict(shared['CASES'])
    # The arithmetic and lifetime corpus is shared with the independently
    # accepted owned-device implementation. Its old receipts are not reused.
    for size in (1,31,32,255,256,257,1023,4096,262144):
        for mode,operation,a,b in [('add','c::Operation::Add()',127,128),('affine','c::Operation::Affine(3)',85,0)]:
            body=f'''let ctx:d::Context=unwrap(make_context());let job:c::Request=request(ctx,repeated({a},{size}),repeated({b},{size}),{operation},c::Fallback::Deny());let result:c::Response=unwrap(d::execute(ctx,job));assert(result.output.data==repeated(255,{size}));assert(result.device.kind==c::Kind::GPU()&&!result.fallback_used);'''
            cases[f'edge_{mode}_{size}']=(body,1,0)
    cases['i8_i32_storage_roundtrip']=('''let ctx:d::Context=unwrap(make_context());let a:c::Tensor=unwrap(c::from_i8([4],[-128,-1,0,127]));let b:c::Tensor=unwrap(c::from_i32([3],[-2147483648,0,2147483647]));let x:d::Tensor=unwrap(d::upload(ctx,a));let y:d::Tensor=unwrap(d::upload(ctx,b));assert(unwrap(d::download(x))==a);assert(unwrap(d::download(y))==b);d::close_tensor(x);d::close_tensor(y);''',0,0)
    cases['typed_error_preserves_live_device_buffer']=('''var finalized:i64=0;try{with_tasks(1,server fn(s:task_scope)->unit !{task,ffi,throw}{let ctx:d::Context=unwrap(make_context());let value:d::Tensor=output(ctx,unwrap(bytes([20])),unwrap(bytes([22])),c::Operation::Add());d::close_context(ctx);throw(GpuFault(value));});}catch(fault:GpuFault){assert(unwrap(d::download(fault.value)).data==unwrap(bytes([42])));assert(d::close_tensor(fault.value));}finally{finalized=finalized+1;}assert(finalized==1);''',1,0)
    helpers=shared['HELPERS']+'''
fn repeated(value:i64,count:i64)->bytes{var n:i64=count;var result:bytes=unwrap(bytes([]));var block:bytes=unwrap(bytes([value]));while n>0{if n%2==1{result=result+block;}n=n/2;if n>0{block=block+block;}}return result;}
struct GpuFault {value:d::Tensor;}
'''
    template=(project/'main.nex').read_bytes().decode('utf-8')
    prefix=template[:template.index('server fn main()->unit')]+helpers
    language=json.loads((project/'nex.json').read_bytes())['language']
    errors={
        'cancel_enqueued_GPU':(shared['ERROR_CASES']['cancel_enqueued_GPU'][0],'E_CANCELLED',10000),
        'deadline_enqueued_GPU':(shared['ERROR_CASES']['deadline_enqueued_GPU'][0],'E_TIMEOUT',2000),
    }
    available=set(cases)|set(errors)
    if args.only and not set(args.only)<=available:parser.error('unknown case: '+str(set(args.only)-available))
    report={'schema':'nex.owned-cuda-hardware/1','ok':False,'environment':'native Windows','requires_WSL':False,
            'compiler_sha256':sha(compiler),'manifest_sha256':sha(project/'bundle/manifest.json'),
            'module_sha256':sha(project/'bundle/module.dll'),'cases':[],'commands':[],
            'actual_GPU_execution':False,'CUDA_from_NEX_accepted':False,'full_windows_regression_accepted':False}
    started=time.monotonic()
    def save():report['seconds']=round(time.monotonic()-started,3);write(out/'report.json',report)
    def run(label,argv,cwd,trace=None,expected=0,extra=None):
        row={'label':label,'argv':list(map(str,argv)),'cwd':str(cwd)};report['commands'].append(row);save()
        env={**os.environ,'PYTHONUTF8':'1'}
        for key in ('NEX_OWNED_CUDA_TRACE','NEX_CUDA_ACCEPTANCE_DELAY_CYCLES','NEX_CUDA_ACCEPTANCE_KERNEL_REPEATS'):env.pop(key,None)
        if trace:env['NEX_OWNED_CUDA_TRACE']=str(trace)
        env.update(extra or {})
        began=time.monotonic();result=subprocess.run(row['argv'],cwd=cwd,env=env,capture_output=True,timeout=300)
        (out/(label+'.stdout')).write_bytes(result.stdout);(out/(label+'.stderr')).write_bytes(result.stderr)
        row.update(exit_code=result.returncode,seconds=round(time.monotonic()-began,3));save()
        if result.returncode!=expected:raise RuntimeError(label+': '+result.stdout.decode('utf-8','replace')[-2200:]+result.stderr.decode('utf-8','replace')[-2400:])
        return result
    def create(name,body):
        directory=out/name;directory.mkdir()
        shutil.copytree(project/'stdlib',directory/'stdlib');shutil.copy2(project/'nex.json',directory/'nex.json')
        (directory/'main.nex').write_bytes(shared['source_program'](prefix,body,language).encode('utf-8'))
        return directory
    def inspect(path,kernels,overflow,pending=False):
        records=[json.loads(line) for line in path.read_bytes().decode('utf-8').splitlines()]
        assert records and records[-1]['event']=='module_unloaded',records[-3:]
        assert all(row['event']!='unsettled' for row in records),records
        ledger=records[-1]['ledger'];assert ledger['live_bytes']==0 and ledger['cleanup_errors']==0,ledger
        for allocated,freed in [('allocations','frees'),('events','event_frees'),('contexts','context_frees'),('modules','module_frees'),('streams','stream_frees')]:assert ledger[allocated]==ledger[freed],ledger
        completed=[row for row in records if row['event']=='kernel_completed']
        if pending:
            assert any(row['event']=='kernel_queued' and row['completion_pending'] for row in records),records
            assert any(row['event']=='physical_drain' and row['physical_completion_verified'] and row['event_status']==0 for row in records),records
            assert any(row['event']=='host_trap' for row in records),records
        else:
            assert len(completed)==kernels,(len(completed),kernels)
            assert sum(bool(row['overflow']) for row in completed)==overflow,completed
            assert all(row['physical_completion_verified'] and row['cpu_fallback'] is False for row in completed),completed
        assert ledger['kernel_launches']==kernels,ledger
        sessions=[{key:row[key] for key in ('name','uuid','pci_bus_id','ordinal','driver_version')} for row in records if row['event']=='session_created']
        assert sessions and all('NVIDIA' in row['name'] for row in sessions),sessions
        return {'sessions':sessions,'ledger':ledger,'completed_kernels':completed,'physical_drain':pending,'trace_sha256':sha(path)}
    try:
        context_probe=project/'preparation/context-probe.exe';context_trace=out/'context-probe.trace.jsonl'
        context=json.loads(run('trusted-host-context-probe',[context_probe],out,context_trace).stdout)
        assert context=={'ok':True,'actual_CUDA_contexts':2,'source_reentry_rejected':True,'nested_cleanup_restores_context':True,'constructor_trap_rolls_back':True,'physical_cleanup_verified':True},context
        report['trusted_host_context_probe']={'executable_sha256':sha(context_probe),'result':context,'trace':inspect(context_trace,0,0)};save()
        for name,(body,kernels,overflow) in cases.items():
            if args.only and name not in args.only:continue
            directory=create(name,body);reference_trace=directory/'reference.trace.jsonl'
            ref=json.loads(run(name+'-reference',[compiler,'eval','--foreign',project/'foreign.json','--task-workers','1','--task-timeout-ms','30000','--task-steps','16000000','--json'],directory,reference_trace).stdout)
            assert ref['stdout']=='42\n' and ref['foreign_resource_bytes_after_scope']==0,ref
            built=json.loads(run(name+'-build',[compiler,'build','--profile','release','--task-timeout-ms','30000','--build-directory',out/'native','--json'],directory).stdout)
            native_trace=directory/'native.trace.jsonl'
            native=run(name+'-native',[built['executable'],'--nex-foreign',project/'foreign.json','--nex-task-workers','1'],directory,native_trace)
            assert native.stdout==b'42\n' and native.stderr==b'',(native.stdout,native.stderr)
            a,b=inspect(reference_trace,kernels,overflow),inspect(native_trace,kernels,overflow)
            assert a['sessions']==b['sessions'],(a['sessions'],b['sessions'])
            report['cases'].append({'name':name,'status':'passed','reference':a,'native':b,'executable':built['executable'],'executable_sha256':sha(Path(built['executable']))});save()
        for name,(body,code,timeout) in errors.items():
            if args.only and name not in args.only:continue
            directory=create(name,body);extra={'NEX_CUDA_ACCEPTANCE_DELAY_CYCLES':'200000000','NEX_CUDA_ACCEPTANCE_KERNEL_REPEATS':'32'}
            reference_trace=directory/'reference.trace.jsonl'
            ref=json.loads(run(name+'-reference',[compiler,'eval','--foreign',project/'foreign.json','--task-workers','1','--task-timeout-ms',str(timeout),'--task-steps','16000000','--json'],directory,reference_trace,1,extra).stdout)
            assert ref['code']==code,ref
            built=json.loads(run(name+'-build',[compiler,'build','--profile','release','--task-timeout-ms','30000','--build-directory',out/'native','--json'],directory).stdout)
            native_trace=directory/'native.trace.jsonl'
            native=run(name+'-native',[built['executable'],'--nex-foreign',project/'foreign.json','--nex-task-workers','1','--nex-task-timeout-ms',str(timeout)],directory,native_trace,70,extra)
            assert code.encode() in native.stderr and native.stdout==b'',(native.stdout,native.stderr)
            a,b=inspect(reference_trace,32,0,True),inspect(native_trace,32,0,True)
            report['cases'].append({'name':name,'status':'passed','expected_error':code,'reference':a,'native':b,'physical_settlement_before_error_exit':True,'executable':built['executable'],'executable_sha256':sha(Path(built['executable']))});save()
        assert sha(compiler)==report['compiler_sha256']
        report.update(ok=True,actual_GPU_execution=True,CUDA_from_NEX_accepted=True,full_hardware_corpus=not args.only)
    except BaseException as error:report['error']=repr(error);raise
    finally:save();print(json.dumps({'ok':report['ok'],'cases':len(report['cases']),'report':str(out/'report.json')}),flush=True)

if __name__=='__main__':main()
