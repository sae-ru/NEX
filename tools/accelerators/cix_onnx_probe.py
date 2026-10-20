"""Run an installed ONNX fixture on the real Zhouyi EP, prohibiting CPU EP fallback."""
import datetime,hashlib,json,os,tempfile,time
from pathlib import Path

scratch=Path(tempfile.mkdtemp(prefix='nex-npu-probe-'))
os.chdir(scratch)
os.environ['OPERATOR_PATH']='/usr/share/cix/lib/onnxruntime/operator/'
os.environ['OMP_NUM_THREADS']='1'
import numpy as np
import onnxruntime as ort

report={'schema':'nex.hardware-probe/1','ok':False,'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'scratch':str(scratch),'backend':'onnxruntime','ort_version':ort.__version__,'available_providers':ort.get_available_providers(),
        'requested_provider':'ZhouyiExecutionProvider','cpu_ep_fallback_disabled':True,'nex_backend_implemented':False}
def opened_npu():
    result=[]
    for p in Path('/proc/self/fd').iterdir():
        try:
            target=os.readlink(p)
            if 'aipu' in target:result.append(target)
        except OSError:pass
    return sorted(result)
try:
    model=Path(ort.__file__).parent/'datasets/mul_1.onnx'
    report.update(model=str(model),model_sha256=hashlib.sha256(model.read_bytes()).hexdigest())
    cpu_options=ort.SessionOptions();cpu_options.intra_op_num_threads=1;cpu_options.inter_op_num_threads=1
    cpu=ort.InferenceSession(str(model),sess_options=cpu_options,providers=['CPUExecutionProvider'])
    inputs=cpu.get_inputs()
    report['inputs']=[{'name':v.name,'shape':v.shape,'type':v.type} for v in inputs]
    options=ort.SessionOptions();options.intra_op_num_threads=1;options.inter_op_num_threads=1
    options.add_session_config_entry('session.disable_cpu_ep_fallback','1')
    options.enable_profiling=True;options.profile_file_prefix=str(scratch/'zhouyi-profile')
    report['phase']='create_npu_session'
    npu=ort.InferenceSession(str(model),sess_options=options,providers=['ZhouyiExecutionProvider'])
    npu.disable_fallback()
    report['registered_providers']=npu.get_providers()
    if 'ZhouyiExecutionProvider' not in npu.get_providers():raise RuntimeError('NPU provider was not registered; refusing CPU substitute')
    report['opened_npu_devices']=opened_npu();rows=[]
    for seed in [0,17,997]:
        feed={}
        for i,v in enumerate(inputs):
            if v.type!='tensor(float)' or not all(isinstance(n,int) and n>0 for n in v.shape):raise RuntimeError('fixture needs fixed float32 inputs')
            shape=tuple(v.shape);count=int(np.prod(shape));feed[v.name]=((np.arange(count,dtype=np.float32)+seed+i)%31/16).reshape(shape)
        expected=cpu.run(None,feed);start=time.perf_counter_ns();actual=npu.run(None,feed);elapsed=time.perf_counter_ns()-start
        if len(actual)!=len(expected):raise RuntimeError('output count differs')
        for a,e in zip(actual,expected):
            if a.shape!=e.shape or a.dtype!=e.dtype or not np.all(np.isfinite(a)):raise RuntimeError('invalid NPU output type/shape/finiteness')
            np.testing.assert_allclose(a,e,rtol=1e-4,atol=1e-5)
        rows.append({'seed':seed,'elements_checked':sum(a.size for a in actual),'host_call_ns':elapsed,
                     'maximum_absolute_error':max(float(np.max(np.abs(a-e))) for a,e in zip(actual,expected)),
                     'output_sha256':[hashlib.sha256(a.tobytes()).hexdigest() for a in actual]})
    profile=Path(npu.end_profiling());events=json.loads(profile.read_text())
    placed=[{'name':e.get('name'),'provider':e.get('args',{}).get('provider'),'op_name':e.get('args',{}).get('op_name'),'duration_us':e.get('dur')} for e in events if e.get('args',{}).get('provider')]
    if not placed or any(e['provider']!='ZhouyiExecutionProvider' for e in placed):raise RuntimeError('profiling does not prove exclusive Zhouyi EP placement: '+repr(placed))
    report.update(ok=True,phase='complete',cases=rows,execution_events=placed,profile_file=str(profile),profile_sha256=hashlib.sha256(profile.read_bytes()).hexdigest())
except Exception as e:
    report['error']=repr(e)
finally:
    (scratch/'receipt.json').write_text(json.dumps(report,indent=2)+'\n')
    print('NEX_HARDWARE_RESULT='+json.dumps(report))
if not report['ok']:raise SystemExit(1)
