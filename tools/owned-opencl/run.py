#!/usr/bin/env python3
"""Run a checked scalar OpenCL kernel emitted by nex emit on an actual GPU."""
import argparse, ctypes, json, os, struct, subprocess, sys, tempfile
from ctypes import c_void_p,c_uint,c_ulonglong,c_size_t,c_char_p,c_int,c_double,POINTER,byref,create_string_buffer
from pathlib import Path

CL_SUCCESS=0; CL_DEVICE_TYPE_GPU=4; CL_MEM_READ_ONLY=1<<2; CL_MEM_WRITE_ONLY=1<<1; CL_MEM_COPY_HOST_PTR=1<<5; CL_TRUE=1

def load(path):
    lib=ctypes.CDLL(path)
    lib.clGetPlatformIDs.argtypes=[c_uint,POINTER(c_void_p),POINTER(c_uint)]
    lib.clGetDeviceIDs.argtypes=[c_void_p,c_ulonglong,c_uint,POINTER(c_void_p),POINTER(c_uint)]
    lib.clGetDeviceInfo.argtypes=[c_void_p,c_uint,c_size_t,c_void_p,POINTER(c_size_t)]
    lib.clCreateContext.argtypes=[c_void_p,c_uint,POINTER(c_void_p),c_void_p,c_void_p,POINTER(c_int)];lib.clCreateContext.restype=c_void_p
    lib.clCreateCommandQueue.argtypes=[c_void_p,c_void_p,c_ulonglong,POINTER(c_int)];lib.clCreateCommandQueue.restype=c_void_p
    lib.clCreateProgramWithSource.argtypes=[c_void_p,c_uint,POINTER(c_char_p),POINTER(c_size_t),POINTER(c_int)];lib.clCreateProgramWithSource.restype=c_void_p
    lib.clBuildProgram.argtypes=[c_void_p,c_uint,POINTER(c_void_p),c_char_p,c_void_p,c_void_p]
    lib.clGetProgramBuildInfo.argtypes=[c_void_p,c_void_p,c_uint,c_size_t,c_void_p,POINTER(c_size_t)]
    lib.clCreateKernel.argtypes=[c_void_p,c_char_p,POINTER(c_int)];lib.clCreateKernel.restype=c_void_p
    lib.clCreateBuffer.argtypes=[c_void_p,c_ulonglong,c_size_t,c_void_p,POINTER(c_int)];lib.clCreateBuffer.restype=c_void_p
    lib.clSetKernelArg.argtypes=[c_void_p,c_uint,c_size_t,c_void_p]
    lib.clEnqueueNDRangeKernel.argtypes=[c_void_p,c_void_p,c_uint,c_void_p,POINTER(c_size_t),c_void_p,c_uint,c_void_p,c_void_p]
    lib.clEnqueueReadBuffer.argtypes=[c_void_p,c_void_p,c_uint,c_size_t,c_size_t,c_void_p,c_uint,c_void_p,c_void_p]
    lib.clFinish.argtypes=[c_void_p]
    return lib

def info(lib,device,param,size):
    buf=create_string_buffer(size);got=c_size_t();code=lib.clGetDeviceInfo(device,param,size,buf,byref(got))
    if code!=CL_SUCCESS:raise RuntimeError('clGetDeviceInfo '+str(code))
    return buf.raw[:got.value].split(b'\0')[0].decode(errors='replace')

def emit(compiler,project,entry,layout):
    with tempfile.TemporaryDirectory() as temporary:
        kernel=Path(temporary)/'kernel.cl'
        result=subprocess.run([compiler,'emit','--kind','opencl','--entry',entry,'--input-layout',layout,'-o',str(kernel),'--json'],cwd=project,capture_output=True,text=True,timeout=180)
        if result.returncode:raise RuntimeError(result.stdout+result.stderr)
        return json.loads(result.stdout),kernel.read_bytes()

def value_word(kind,text):
    if kind=='i64':return int(text,0)
    if kind=='f64':return struct.unpack('<q',struct.pack('<d',float(text)))[0]
    if kind=='bool':return 1 if text.lower()=='true' else 0 if text.lower()=='false' else int(text)
    raise ValueError('unsupported scalar parameter type '+kind)

def decode(kind,word):
    if kind=='i64':return word
    if kind=='f64':return struct.unpack('<d',struct.pack('<q',word))[0]
    if kind=='bool':return bool(word)
    return None

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--compiler',required=True);parser.add_argument('--project',required=True,type=Path)
    parser.add_argument('--entry',required=True);parser.add_argument('--args',default='')
    parser.add_argument('--count',type=int,default=1);parser.add_argument('--steps',type=int,default=65536)
    parser.add_argument('--layout',choices=['rows','columns'],default='columns')
    parser.add_argument('--library',default=None,help='OpenCL loader path')
    args=parser.parse_args()
    if not 1<=args.count<=32768 or not 1<=args.steps<=65536 or args.count*args.steps>16777216:raise SystemExit('geometry out of bounds')
    emission,source=emit(args.compiler,args.project,args.entry,args.layout)
    params=emission.get('parameter_types',[]);result_type=emission.get('result_type')
    if any(p not in ('i64','f64','bool') for p in params) or result_type not in ('i64','f64','bool','unit'):
        raise SystemExit('owned OpenCL dispatch currently supports scalar i64/f64/bool/unit only')
    raw=args.args.split(',') if args.args else []
    if len(raw)!=len(params):raise SystemExit('argument count differs from checked signature')
    words=[value_word(kind,text) for kind,text in zip(params,raw)]
    library=args.library or os.environ.get('NEX_OPENCL_LIBRARY')
    if library is None:library='OpenCL.dll' if os.name=='nt' else ('/System/Library/Frameworks/OpenCL.framework/OpenCL' if sys.platform=='darwin' else 'libOpenCL.so.1')
    lib=load(library)
    platform=c_void_p();count=c_uint();code=lib.clGetPlatformIDs(1,byref(platform),byref(count))
    if code!=CL_SUCCESS or not count.value:raise RuntimeError('no OpenCL platform')
    device=c_void_p();code=lib.clGetDeviceIDs(platform,CL_DEVICE_TYPE_GPU,1,byref(device),byref(count))
    if code!=CL_SUCCESS or not count.value:raise RuntimeError('no OpenCL GPU device')
    name=info(lib,device,0x102B,256);version=info(lib,device,0x102F,256)
    context=lib.clCreateContext(None,1,byref(device),None,None,byref(c_int()))
    queue=lib.clCreateCommandQueue(context,device,0,byref(c_int()))
    program=lib.clCreateProgramWithSource(context,1,byref(c_char_p(source)),None,byref(c_int()))
    build=lib.clBuildProgram(program,1,byref(device),None,None,None)
    if build:
        log=create_string_buffer(65536);got=c_size_t();lib.clGetProgramBuildInfo(program,device,0x1183,65536,log,byref(got));raise RuntimeError('OpenCL build '+str(build)+'\n'+log.value.decode(errors='replace'))
    kernel=lib.clCreateKernel(program,b'nex_generated_map',byref(c_int()))
    def buffer(data,n):
        raw=ctypes.create_string_buffer(data,n)
        b=lib.clCreateBuffer(context,CL_MEM_READ_ONLY|CL_MEM_COPY_HOST_PTR,n,raw,byref(c_int()))
        return b,raw
    inputs=[]
    for word in words:
        payload=struct.pack('<q',word)*args.count
        inputs.append(buffer(payload,len(payload)))
    out_words=max(1,1 if result_type=='unit' else 1)
    out_bytes=args.count*8*(1 if result_type!='unit' else 1)
    output=lib.clCreateBuffer(context,CL_MEM_WRITE_ONLY,out_bytes,None,byref(c_int()))
    errors=lib.clCreateBuffer(context,CL_MEM_WRITE_ONLY,args.count*4,None,byref(c_int()))
    for i,(b,_) in enumerate(inputs):lib.clSetKernelArg(kernel,i,8,byref(c_void_p(b)))
    lib.clSetKernelArg(kernel,len(inputs),8,byref(c_void_p(output)))
    lib.clSetKernelArg(kernel,len(inputs)+1,8,byref(c_void_p(errors)))
    lanes=c_uint(args.count);steps=c_uint(args.steps)
    lib.clSetKernelArg(kernel,len(inputs)+2,4,byref(lanes));lib.clSetKernelArg(kernel,len(inputs)+3,4,byref(steps))
    global_size=c_size_t(args.count)
    if lib.clEnqueueNDRangeKernel(queue,kernel,1,None,byref(global_size),None,0,None,None)!=CL_SUCCESS:raise RuntimeError('enqueue failed')
    lib.clFinish(queue)
    out=create_string_buffer(out_bytes);err=create_string_buffer(args.count*4)
    lib.clEnqueueReadBuffer(queue,output,CL_TRUE,0,out_bytes,out,0,None,None)
    lib.clEnqueueReadBuffer(queue,errors,CL_TRUE,0,args.count*4,err,0,None,None)
    result=struct.unpack('<q',out.raw[:8])[0];error=struct.unpack('<I',err.raw[:4])[0]
    print(json.dumps({'schema':'nex.opencl-run/1','ok':error==0,'device':name,'version':version,
        'device_type':'GPU','entry':args.entry,'layout':args.layout,'count':args.count,'steps':args.steps,
        'result':decode(result_type,result),'result_type':result_type,'error':error,
        'source_sha256':emission.get('shader_sha256'),'cpu_fallback':False},ensure_ascii=False))
    return 0

if __name__=='__main__':sys.exit(main())
