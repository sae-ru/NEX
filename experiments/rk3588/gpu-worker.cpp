#ifndef _GNU_SOURCE
#define _GNU_SOURCE 1
#endif
// Experimental trusted RK3588 OpenCL adapter. No NEX/runtime C++ objects cross its ABI.
#define CL_TARGET_OPENCL_VERSION 120
#include <CL/cl.h>
#include "nex_ffi_module.h"
#include "third_party/json.hpp"
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
  if(auto path=std::getenv("NEX_RK_GPU_TRACE_FILE")){
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
  Library library{"/usr/lib/aarch64-linux-gnu/libOpenCL.so.1"};
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

#include <fcntl.h>
#include <iostream>
#include <cerrno>
#include <sys/resource.h>
#include <limits>
static void rpcWrite(int fd,const void *data,size_t count){auto p=static_cast<const uint8_t*>(data);while(count){auto n=::write(fd,p,count);if(n<0&&errno==EINTR)continue;if(n<=0)throw std::runtime_error("worker result write");p+=n;count-=n;}}
static void rpcU32(int fd,uint32_t n){uint8_t b[4];for(int i=0;i<4;++i)b[i]=uint8_t(n>>(8*i));rpcWrite(fd,b,4);}
static uint32_t rpcReadU32(){uint8_t b[4];std::cin.read(reinterpret_cast<char*>(b),4);if(!std::cin)throw Failure("E_PROTOCOL","missing input length");return uint32_t(b[0])|(uint32_t(b[1])<<8)|(uint32_t(b[2])<<16)|(uint32_t(b[3])<<24);}
int main(){
 int protocol=fcntl(STDOUT_FILENO,F_DUPFD_CLOEXEC,3);if(protocol<0)return 3;
 // Only this dedicated child redirects descriptors; parent/other requests keep
 // their own stdout. Vendor constructors/destructors always use the log fd.
 if(dup2(STDERR_FILENO,STDOUT_FILENO)<0)return 3;
 rlimit files{2097152,2097152};if(setrlimit(RLIMIT_FSIZE,&files))return 3;
 rlimit core{0,0};setrlimit(RLIMIT_CORE,&core);
 try{
  uint32_t n=rpcReadU32();if(!n||n>65536)throw Failure("E_INPUT_SIZE","bounded worker input required");
  std::vector<uint8_t>x(n),y(n);std::cin.read(reinterpret_cast<char*>(x.data()),n);std::cin.read(reinterpret_cast<char*>(y.data()),n);
  if(!std::cin||std::cin.peek()!=std::char_traits<char>::eof())throw Failure("E_PROTOCOL","invalid worker input frame");
  for(size_t i=0;i<n;++i)if(x[i]>60||y[i]>30)throw Failure("E_INPUT_RANGE","invalid worker affine range");
  std::vector<uint8_t>result;{GPU gpu;result=gpu.run(x,y);}
  if(result.size()!=n)throw Failure("E_PROTOCOL","invalid worker result length");
  rpcU32(protocol,0);rpcU32(protocol,result.size());rpcWrite(protocol,result.data(),result.size());close(protocol);return 0;
 }catch(const std::exception &e){
  std::string message=e.what();for(auto &c:message)if(static_cast<unsigned char>(c)<32||static_cast<unsigned char>(c)>126)c='?';message=message.substr(0,2048);
  const auto *specific=dynamic_cast<const Failure*>(&e);std::string code=specific?specific->code:"E_ACCELERATOR";
  try{auto text=JSON{{"code",code},{"message",message}}.dump();rpcU32(protocol,1);rpcU32(protocol,text.size());rpcWrite(protocol,text.data(),text.size());close(protocol);return 0;}catch(...){return 3;}
 }
}
