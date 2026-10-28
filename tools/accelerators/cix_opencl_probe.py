"""Bounded, GPU-only OpenCL capability test; this is not a NEX backend."""
import ctypes as C
import datetime
import hashlib
import json
from pathlib import Path

library=Path('/opt/cixgpu-pro/lib/aarch64-linux-gnu/libOpenCL.so.1')
cl=C.CDLL(str(library))
P=C.c_void_p; I=C.c_int32; U=C.c_uint32; Q=C.c_uint64; Z=C.c_size_t
def api(name,result,args):
    f=getattr(cl,name); f.restype=result; f.argtypes=args; return f
platforms=api('clGetPlatformIDs',I,[U,C.POINTER(P),C.POINTER(U)])
devices=api('clGetDeviceIDs',I,[P,Q,U,C.POINTER(P),C.POINTER(U)])
info=api('clGetDeviceInfo',I,[P,U,Z,P,C.POINTER(Z)])
context=api('clCreateContext',P,[P,U,C.POINTER(P),P,P,C.POINTER(I)])
queue=api('clCreateCommandQueue',P,[P,P,Q,C.POINTER(I)])
program=api('clCreateProgramWithSource',P,[P,U,C.POINTER(C.c_char_p),C.POINTER(Z),C.POINTER(I)])
build=api('clBuildProgram',I,[P,U,C.POINTER(P),C.c_char_p,P,P])
buildinfo=api('clGetProgramBuildInfo',I,[P,P,U,Z,P,C.POINTER(Z)])
kernel=api('clCreateKernel',P,[P,C.c_char_p,C.POINTER(I)])
buffer=api('clCreateBuffer',P,[P,Q,Z,P,C.POINTER(I)])
argument=api('clSetKernelArg',I,[P,U,Z,P])
enqueue=api('clEnqueueNDRangeKernel',I,[P,P,U,C.POINTER(Z),C.POINTER(Z),C.POINTER(Z),U,C.POINTER(P),C.POINTER(P)])
read=api('clEnqueueReadBuffer',I,[P,P,U,Z,Z,P,U,C.POINTER(P),C.POINTER(P)])
finish=api('clFinish',I,[P])
profile=api('clGetEventProfilingInfo',I,[P,U,Z,P,C.POINTER(Z)])
release={n:api('clRelease'+n,I,[P]) for n in ['MemObject','Event','Kernel','Program','CommandQueue','Context']}
owned=[]
def check(code,label):
    if code: raise RuntimeError('%s: OpenCL %s'%(label,code))
def own(kind,value,code):
    check(code.value,kind)
    if not value: raise RuntimeError('null '+kind)
    owned.append((kind,value));return value
def string(device,key):
    n=Z();check(info(device,key,0,None,C.byref(n)),'device info size')
    s=C.create_string_buffer(n.value);check(info(device,key,n,s,None),'device info');return s.value.decode()
try:
    count=U();check(platforms(0,None,C.byref(count)),'platform count')
    ps=(P*count.value)();check(platforms(count,ps,None),'platform list')
    selected=None
    for p in ps:
        n=U();code=devices(p,4,0,None,C.byref(n)) # CL_DEVICE_TYPE_GPU only
        if code==-1:continue
        check(code,'GPU count')
        ds=(P*n.value)();check(devices(p,4,n,ds,None),'GPU list')
        if n.value:selected=ds[0];break
    if selected is None:raise RuntimeError('No physical OpenCL GPU; CPU fallback is forbidden')
    dtype=Q();check(info(selected,0x1000,C.sizeof(dtype),C.byref(dtype),None),'device type')
    if not dtype.value&4:raise RuntimeError('Selected device is not a GPU')
    device_array=(P*1)(selected);error=I()
    ctx=own('Context',context(None,1,device_array,None,None,C.byref(error)),error)
    cq=own('CommandQueue',queue(ctx,selected,2,C.byref(error)),error)
    source=b'__kernel void nex_probe(__global const int* a,__global const int* b,__global int* c){size_t i=get_global_id(0);c[i]=a[i]*3+b[i];}'
    sources=(C.c_char_p*1)(source);lengths=(Z*1)(len(source))
    prg=own('Program',program(ctx,1,sources,lengths,C.byref(error)),error)
    code=build(prg,1,device_array,b'-cl-std=CL1.2',None,None)
    if code:
        n=Z();buildinfo(prg,selected,0x1183,0,None,C.byref(n));log=C.create_string_buffer(n.value)
        buildinfo(prg,selected,0x1183,n,log,None);raise RuntimeError('kernel build: '+log.value.decode(errors='replace'))
    krn=own('Kernel',kernel(prg,b'nex_probe',C.byref(error)),error)
    rows=[];size=65536
    for seed in [0,17,997]:
        aa=[((i*13+seed)%20001)-10000 for i in range(size)]
        bb=[((i*7-seed)%20001)-10000 for i in range(size)]
        a=(I*size)(*aa);b=(I*size)(*bb);out=(I*size)()
        buffers=[]
        for flags,data in [(4|32,a),(4|32,b),(2,None)]:
            mem=own('MemObject',buffer(ctx,flags,C.sizeof(out),data,C.byref(error)),error);buffers.append(mem)
        for index,mem in enumerate(buffers):
            value=P(mem);check(argument(krn,index,C.sizeof(value),C.byref(value)),'kernel argument')
        event=P();global_size=(Z*1)(size)
        check(enqueue(cq,krn,1,None,global_size,None,0,None,C.byref(event)),'enqueue GPU kernel')
        owned.append(('Event',event));check(finish(cq),'finish GPU kernel')
        check(read(cq,buffers[2],1,0,C.sizeof(out),out,0,None,None),'read GPU result')
        mismatch=next((i for i,(x,y,z) in enumerate(zip(aa,bb,out)) if z!=x*3+y),None)
        if mismatch is not None:raise RuntimeError('GPU mismatch at %d'%mismatch)
        start=Q();end=Q()
        check(profile(event,0x1282,C.sizeof(start),C.byref(start),None),'GPU start timestamp')
        check(profile(event,0x1283,C.sizeof(end),C.byref(end),None),'GPU end timestamp')
        if end.value<start.value:raise RuntimeError('invalid GPU profiling timestamps')
        rows.append({'seed':seed,'elements_checked':size,'gpu_kernel_ns':end.value-start.value,'result_sha256':hashlib.sha256(bytes(out)).hexdigest()})
    print(json.dumps({'schema':'nex.hardware-probe/1','ok':True,'timestamp_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'backend':'OpenCL','device':string(selected,0x102b),'vendor':string(selected,0x102c),'driver':string(selected,0x102d),
        'device_version':string(selected,0x102f),'device_type':dtype.value,'cpu_fallback_allowed':False,'cases':rows,
        'kernel_sha256':hashlib.sha256(source).hexdigest(),'library':str(library.resolve()),'nex_backend_implemented':False},indent=2))
finally:
    for kind,value in reversed(owned):check(release[kind](value),'release '+kind)
