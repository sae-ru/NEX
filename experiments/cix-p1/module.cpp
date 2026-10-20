#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
// Experimental trusted CIX adapter. No NEX/runtime C++ objects cross its ABI.
#define CL_TARGET_OPENCL_VERSION 120
#include <CL/cl.h>
#include "onnxruntime_c_api.h"
#include "zhouyi_provider_factory.h"
#include "nex_ffi_module.h"
#include "third_party/json.hpp"
#include "model.inc"
#include <array>
#include <atomic>
#include <chrono>
#include <cmath>
#include <cstdlib>
#include <cstring>
#include <dlfcn.h>
#include <filesystem>
#include <fstream>
#include <mutex>
#include <stdexcept>
#include <string>
#include <vector>
#include <unistd.h>

using JSON=nlohmann::json;
struct Failure:std::runtime_error {
  std::string code;
  Failure(std::string code,std::string text):std::runtime_error(std::move(text)),code(std::move(code)){}
};
struct Library {
  void *value=nullptr;
  explicit Library(const char *path,int flags=RTLD_NOW|RTLD_LOCAL){value=dlopen(path,flags);if(!value)throw Failure("E_DEVICE_UNAVAILABLE",dlerror());}
  ~Library(){if(value)dlclose(value);}
  template<class T>T symbol(const char *name){dlerror();auto p=dlsym(value,name);auto e=dlerror();if(e||!p)throw Failure("E_DEVICE_ABI",e?e:name);return reinterpret_cast<T>(p);}
  Library(const Library&)=delete;
};
void trace(const JSON &entry){
  if(auto path=std::getenv("NEX_CIX_TRACE_FILE")){
    std::ofstream output(path,std::ios::app);if(!output)throw Failure("E_TRACE","cannot append private accelerator trace");
    output<<entry.dump()<<'\n';if(!output)throw Failure("E_TRACE","cannot write private accelerator trace");
  }
}
nex_ffi_status error(const nex_ffi_api_v1 *a,nex_ffi_call call,nex_ffi_ref *out,const std::string &code,const std::string &message){
  auto text=message.substr(0,2048);
  return a->make_failure(call,reinterpret_cast<const uint8_t*>(code.data()),code.size(),reinterpret_cast<const uint8_t*>(text.data()),text.size(),out);
}
#define FFI(expression) do {auto status=(expression);if(status)return status;}while(0)
std::mutex acceleratorMutex; // Explicit serialized adapter; no source concurrency claim.

class GPU {
  Library library{"/opt/cixgpu-pro/lib/aarch64-linux-gnu/libOpenCL.so.1"};
#define LOAD(name) decltype(&::name) name=library.symbol<decltype(&::name)>(#name)
  LOAD(clGetPlatformIDs);LOAD(clGetDeviceIDs);LOAD(clGetDeviceInfo);LOAD(clCreateContext);
  LOAD(clCreateCommandQueue);LOAD(clCreateProgramWithSource);LOAD(clBuildProgram);LOAD(clGetProgramBuildInfo);
  LOAD(clCreateKernel);LOAD(clCreateBuffer);LOAD(clSetKernelArg);LOAD(clEnqueueNDRangeKernel);
  LOAD(clEnqueueReadBuffer);LOAD(clFinish);LOAD(clGetEventProfilingInfo);
  LOAD(clReleaseEvent);LOAD(clReleaseMemObject);LOAD(clReleaseKernel);LOAD(clReleaseProgram);
  LOAD(clReleaseCommandQueue);LOAD(clReleaseContext);
#undef LOAD
  cl_context context=nullptr;cl_command_queue queue=nullptr;cl_program program=nullptr;cl_kernel kernel=nullptr;
  std::vector<cl_mem> buffers;cl_event event=nullptr;int cleanupError=0;
  void check(cl_int code,const char *where){if(code)throw Failure("E_OPENCL",std::string(where)+": "+std::to_string(code));}
  void cleanup()noexcept{
    auto release=[&](int status){if(status&&!cleanupError)cleanupError=status;};
    if(event){release(clReleaseEvent(event));event=nullptr;}
    for(auto p:buffers)release(clReleaseMemObject(p));buffers.clear();
    if(kernel){release(clReleaseKernel(kernel));kernel=nullptr;}
    if(program){release(clReleaseProgram(program));program=nullptr;}
    if(queue){release(clReleaseCommandQueue(queue));queue=nullptr;}
    if(context){release(clReleaseContext(context));context=nullptr;}
  }
public:
  ~GPU(){cleanup();}
  std::vector<uint8_t> run(std::vector<uint8_t> &a,std::vector<uint8_t> &b){
    cl_uint n=0;check(clGetPlatformIDs(0,nullptr,&n),"platform count");if(!n||n>16)throw Failure("E_DEVICE_UNAVAILABLE","no bounded OpenCL platform list");
    std::vector<cl_platform_id> platforms(n);check(clGetPlatformIDs(n,platforms.data(),nullptr),"platform list");cl_device_id device=nullptr;
    for(auto platform:platforms){auto status=clGetDeviceIDs(platform,CL_DEVICE_TYPE_GPU,1,&device,nullptr);if(status==CL_DEVICE_NOT_FOUND)continue;check(status,"GPU selection");if(device)break;}
    if(!device)throw Failure("E_DEVICE_UNAVAILABLE","physical GPU required; CPU fallback forbidden");
    cl_device_type type=0;check(clGetDeviceInfo(device,CL_DEVICE_TYPE,sizeof(type),&type,nullptr),"device type");
    if(!(type&CL_DEVICE_TYPE_GPU))throw Failure("E_DEVICE_UNAVAILABLE","selected OpenCL device is not a GPU");
    size_t length=0;check(clGetDeviceInfo(device,CL_DEVICE_NAME,0,nullptr,&length),"device name size");
    if(!length||length>4096)throw Failure("E_DEVICE_ABI","invalid GPU name length");std::vector<char> name(length);
    check(clGetDeviceInfo(device,CL_DEVICE_NAME,name.size(),name.data(),nullptr),"device name");
    cl_int status=0;context=clCreateContext(nullptr,1,&device,nullptr,nullptr,&status);check(status,"create context");
    queue=clCreateCommandQueue(context,device,CL_QUEUE_PROFILING_ENABLE,&status);check(status,"create queue");
    const char *source="__kernel void affine(__global const uchar*a,__global const uchar*b,__global uchar*c){size_t i=get_global_id(0);c[i]=(uchar)(3*(int)a[i]+(int)b[i]);}";
    length=std::strlen(source);program=clCreateProgramWithSource(context,1,&source,&length,&status);check(status,"create program");
    status=clBuildProgram(program,1,&device,"-cl-std=CL1.2",nullptr,nullptr);
    if(status){size_t size=0;clGetProgramBuildInfo(program,device,CL_PROGRAM_BUILD_LOG,0,nullptr,&size);std::vector<char> log(std::min<size_t>(size,16384)+1);clGetProgramBuildInfo(program,device,CL_PROGRAM_BUILD_LOG,log.size()-1,log.data(),nullptr);throw Failure("E_OPENCL_BUILD",log.data());}
    kernel=clCreateKernel(program,"affine",&status);check(status,"create kernel");
    for(auto input:{&a,&b}){auto buffer=clCreateBuffer(context,CL_MEM_READ_ONLY|CL_MEM_COPY_HOST_PTR,input->size(),input->data(),&status);check(status,"input buffer");buffers.push_back(buffer);}
    auto output=clCreateBuffer(context,CL_MEM_WRITE_ONLY,a.size(),nullptr,&status);check(status,"output buffer");buffers.push_back(output);
    for(cl_uint i=0;i<3;++i)check(clSetKernelArg(kernel,i,sizeof(cl_mem),&buffers[i]),"kernel argument");
    size_t count=a.size();check(clEnqueueNDRangeKernel(queue,kernel,1,nullptr,&count,nullptr,0,nullptr,&event),"GPU enqueue");check(clFinish(queue),"GPU completion");
    std::vector<uint8_t> result(a.size());check(clEnqueueReadBuffer(queue,output,CL_TRUE,0,result.size(),result.data(),0,nullptr,nullptr),"GPU readback");
    cl_ulong start=0,end=0;check(clGetEventProfilingInfo(event,CL_PROFILING_COMMAND_START,sizeof(start),&start,nullptr),"GPU timestamp start");
    check(clGetEventProfilingInfo(event,CL_PROFILING_COMMAND_END,sizeof(end),&end,nullptr),"GPU timestamp end");
    if(end<start)throw Failure("E_DEVICE_ABI","invalid GPU timestamps");cleanup();if(cleanupError)throw Failure("E_OPENCL_CLEANUP",std::to_string(cleanupError));
    trace(JSON{{"backend","gpu"},{"device",std::string(name.data(),name.size()-1)},{"device_type",type},{"elements",a.size()},
               {"kernel_ns",end-start},{"cpu_fallback_allowed",false},{"cleanup_verified",true}});
    return result;
  }
};

const char *ortLibraryPath(){
  auto value=std::getenv("NEX_CIX_ORT_LIBRARY");
  if(!value||!*value||!std::filesystem::path(value).is_absolute())throw Failure("E_CONFIGURATION","explicit absolute NEX_CIX_ORT_LIBRARY is required");
  return value;
}
class NPU {
  // The vendor compiler exports an embedded LLVM ABI. Prefer its own local
  // dependency scope over the NEX process LLVM symbols on this glibc target.
  // Vendor driver initialization cannot be repeated after dlclose: retain its
  // code/static state until process exit; sessions/tensors still use RAII.
  Library library{ortLibraryPath(),RTLD_NOW|RTLD_LOCAL|RTLD_DEEPBIND|RTLD_NODELETE};
  const OrtApi *api=nullptr;OrtEnv *environment=nullptr;OrtSessionOptions *options=nullptr;
  OrtSession *session=nullptr;OrtMemoryInfo *memory=nullptr;OrtValue *input=nullptr,*output=nullptr;
  OrtTensorTypeAndShapeInfo *shape=nullptr;OrtAllocator *allocator=nullptr;std::vector<char*> strings;
  void check(OrtStatus *status){if(status){std::string message=api->GetErrorMessage(status);api->ReleaseStatus(status);throw Failure("E_NPU",message);}}
public:
  ~NPU(){
    if(!api)return;
    if(shape)api->ReleaseTensorTypeAndShapeInfo(shape);
    if(output)api->ReleaseValue(output);if(input)api->ReleaseValue(input);if(memory)api->ReleaseMemoryInfo(memory);
    if(session)api->ReleaseSession(session);if(options)api->ReleaseSessionOptions(options);if(environment)api->ReleaseEnv(environment);
    if(allocator)for(auto p:strings)allocator->Free(allocator,p);
  }
  std::vector<double> run(std::array<float,6> &values){
    auto base=library.symbol<decltype(&OrtGetApiBase)>("OrtGetApiBase")();api=base->GetApi(ORT_API_VERSION);
    if(!api)throw Failure("E_DEVICE_ABI","ONNX Runtime API20 is unavailable");
    check(api->CreateEnv(ORT_LOGGING_LEVEL_WARNING,"nex_cix",&environment));check(api->CreateSessionOptions(&options));
    check(api->SetIntraOpNumThreads(options,1));check(api->SetInterOpNumThreads(options,1));
    check(api->AddSessionConfigEntry(options,"session.disable_cpu_ep_fallback","1"));
    auto append=library.symbol<decltype(&OrtSessionOptionsAppendExecutionProvider_Zhouyi)>("OrtSessionOptionsAppendExecutionProvider_Zhouyi");check(append(options));
    std::string prefix;
    if(auto file=std::getenv("NEX_CIX_TRACE_FILE")){
      prefix=(std::filesystem::path(file).parent_path()/("npu-"+std::to_string(getpid())+"-"+std::to_string(std::chrono::steady_clock::now().time_since_epoch().count()))).string();
      check(api->EnableProfiling(options,prefix.c_str()));
    }
    check(api->CreateSessionFromArray(environment,modelData,sizeof(modelData),options,&session));
    size_t count=0;check(api->SessionGetInputCount(session,&count));if(count!=1)throw Failure("E_MODEL","expected one input");
    check(api->SessionGetOutputCount(session,&count));if(count!=1)throw Failure("E_MODEL","expected one output");
    check(api->GetAllocatorWithDefaultOptions(&allocator));char *inputName=nullptr,*outputName=nullptr;
    check(api->SessionGetInputName(session,0,allocator,&inputName));strings.push_back(inputName);
    check(api->SessionGetOutputName(session,0,allocator,&outputName));strings.push_back(outputName);
    check(api->CreateCpuMemoryInfo(OrtArenaAllocator,OrtMemTypeDefault,&memory));int64_t dimensions[]={3,2};
    check(api->CreateTensorWithDataAsOrtValue(memory,values.data(),sizeof(values),dimensions,2,ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT,&input));
    const OrtValue *inputs[]={input};const char *inputNames[]={inputName},*outputNames[]={outputName};
    check(api->Run(session,nullptr,inputNames,inputs,1,outputNames,1,&output));
    check(api->GetTensorTypeAndShape(output,&shape));ONNXTensorElementDataType type;
    check(api->GetTensorElementType(shape,&type));check(api->GetTensorShapeElementCount(shape,&count));
    if(type!=ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT||count!=6)throw Failure("E_MODEL_OUTPUT","unexpected NPU output type/size");
    size_t rank=0;check(api->GetDimensionsCount(shape,&rank));if(rank!=2)throw Failure("E_MODEL_OUTPUT","unexpected output rank");
    int64_t dims[2];check(api->GetDimensions(shape,dims,2));if(dims[0]!=3||dims[1]!=2)throw Failure("E_MODEL_OUTPUT","unexpected output shape");
    void *data=nullptr;check(api->GetTensorMutableData(output,&data));std::vector<double> result;
    for(size_t i=0;i<count;++i){double v=static_cast<float*>(data)[i];if(!std::isfinite(v))throw Failure("E_MODEL_OUTPUT","nonfinite output");result.push_back(v==0?0:v);}
    bool aipu=false;
    for(const auto &entry:std::filesystem::directory_iterator("/proc/self/fd")){
      std::error_code error;auto target=std::filesystem::read_symlink(entry.path(),error);if(!error&&target=="/dev/aipu")aipu=true;
    }
    std::string profile;
    if(!prefix.empty()){char *filename=nullptr;check(api->SessionEndProfiling(session,allocator,&filename));strings.push_back(filename);profile=filename;}
    trace(JSON{{"backend","npu"},{"symbol_scope","RTLD_DEEPBIND|RTLD_NODELETE"},{"provider","ZhouyiExecutionProvider"},{"runtime_version",base->GetVersionString()},{"runtime_library",ortLibraryPath()},
               {"elements",result.size()},{"cpu_ep_fallback_disabled",true},{"aipu_open",aipu},{"profile",profile},{"model_sha256",modelSHA256}});
    return result;
  }
};

extern "C" nex_ffi_status gpu_affine(const nex_ffi_api_v1 *a,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void*){
  try{
    if(count!=2)return NEX_FFI_ARGUMENT;FFI(a->poll(call));uint64_t n=0,m=0;FFI(a->byte_size(call,args[0],&n));FFI(a->byte_size(call,args[1],&m));
    if(n!=m||!n||n>65536)return error(a,call,out,"E_INPUT_SIZE","GPU inputs require equal nonzero byte lengths <=65536");
    std::vector<uint8_t> x(n),y(n);uint64_t copied=0;FFI(a->copy_bytes(call,args[0],0,x.data(),n,&copied));if(copied!=n)return NEX_FFI_INTERNAL;
    FFI(a->copy_bytes(call,args[1],0,y.data(),n,&copied));if(copied!=n)return NEX_FFI_INTERNAL;
    for(size_t i=0;i<n;++i)if(x[i]>60||y[i]>30)return error(a,call,out,"E_INPUT_RANGE","bounded affine input exceeds a<=60,b<=30");
    std::vector<uint8_t> result;{std::lock_guard lock(acceleratorMutex);GPU gpu;result=gpu.run(x,y);}FFI(a->poll(call));
    nex_ffi_ref value=0;FFI(a->make_bytes(call,result.data(),result.size(),&value));return a->make_success(call,value,out);
  }catch(const Failure &e){return error(a,call,out,e.code,e.what());}catch(const std::exception &e){return error(a,call,out,"E_ACCELERATOR",e.what());}catch(...){return NEX_FFI_INTERNAL;}
}
extern "C" nex_ffi_status npu_mul(const nex_ffi_api_v1 *a,nex_ffi_call call,const nex_ffi_ref *args,uint64_t count,nex_ffi_ref *out,void*){
  try{
    if(count!=1)return NEX_FFI_ARGUMENT;FFI(a->poll(call));uint64_t n=0;FFI(a->child_count(call,args[0],&n));
    if(n!=6)return error(a,call,out,"E_INPUT_SIZE","fixed model requires six float32 values");std::array<float,6> input;
    for(size_t i=0;i<6;++i){nex_ffi_ref child=0;double value;FFI(a->child(call,args[0],i,&child));FFI(a->get_f64(call,child,&value));
      float converted=static_cast<float>(value);if(!std::isfinite(converted)||static_cast<double>(converted)!=value)return error(a,call,out,"E_MODEL_PRECISION","input is not exactly representable as finite float32");input[i]=converted;}
    std::vector<double> result;{std::lock_guard lock(acceleratorMutex);NPU npu;result=npu.run(input);}FFI(a->poll(call));
    std::vector<nex_ffi_ref> values(result.size());for(size_t i=0;i<result.size();++i)FFI(a->make_f64(call,result[i],&values[i]));
    nex_ffi_ref value=0;FFI(a->make_list(call,values.data(),values.size(),&value));return a->make_success(call,value,out);
  }catch(const Failure &e){return error(a,call,out,e.code,e.what());}catch(const std::exception &e){return error(a,call,out,"E_ACCELERATOR",e.what());}catch(...){return NEX_FFI_INTERNAL;}
}
NEX_FFI_MODULE_EXPORT const nex_ffi_module_v1 *nex_ffi_module_entry(uint32_t abi,uint32_t size){
  static const nex_ffi_export_v1 exports[]={
    {sizeof(nex_ffi_export_v1),0,"gpu_affine",NEX_GPU_SIGNATURE,gpu_affine,nullptr},
    {sizeof(nex_ffi_export_v1),0,"npu_mul",NEX_NPU_SIGNATURE,npu_mul,nullptr}};
  static const nex_ffi_module_v1 module={NEX_FFI_MODULE_ABI_V1,sizeof(nex_ffi_module_v1),2,sizeof(nex_ffi_export_v1),exports};
  return abi==NEX_FFI_ABI_V1&&size>=sizeof(nex_ffi_api_v1)?&module:nullptr;
}
