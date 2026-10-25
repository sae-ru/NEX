#define CL_TARGET_OPENCL_VERSION 120
#include <CL/cl.h>
#include "protocol.h"
#include <algorithm>
#include <csignal>
#include <cstdio>
#include <cstdlib>
#include <thread>
#include <atomic>
#include <chrono>
#include <dlfcn.h>
#include <fcntl.h>
#include <limits>
#include <map>
#include <memory>
#include <sys/resource.h>
#ifndef NEX_OPENCL_LIBRARY
#error An explicit operator-selected OpenCL library must be embedded
#endif
using namespace owned_gpu;
struct Library {
 void *handle=nullptr;
 Library(){handle=dlopen(NEX_OPENCL_LIBRARY,RTLD_NOW|RTLD_LOCAL);if(!handle)throw Error("E_COMPUTE_UNAVAILABLE","configured OpenCL loader is unavailable");}
 ~Library(){if(handle)dlclose(handle);}
 template<class T>T get(const char *name){dlerror();auto p=dlsym(handle,name);if(auto e=dlerror();e||!p)throw Error("E_DEVICE_ABI",name);return reinterpret_cast<T>(p);}
};
class GPU {
 Library lib;
#define LOAD(n) decltype(&::n) n=lib.get<decltype(&::n)>(#n)
 LOAD(clGetPlatformIDs);LOAD(clGetDeviceIDs);LOAD(clGetDeviceInfo);LOAD(clCreateContext);LOAD(clCreateCommandQueue);
 LOAD(clCreateProgramWithSource);LOAD(clBuildProgram);LOAD(clGetProgramBuildInfo);LOAD(clCreateKernel);LOAD(clCreateBuffer);
 LOAD(clSetKernelArg);LOAD(clEnqueueNDRangeKernel);LOAD(clEnqueueReadBuffer);LOAD(clFinish);LOAD(clGetEventInfo);LOAD(clGetEventProfilingInfo);
 LOAD(clReleaseEvent);LOAD(clReleaseMemObject);LOAD(clReleaseKernel);LOAD(clReleaseProgram);LOAD(clReleaseCommandQueue);LOAD(clReleaseContext);
 LOAD(clCreateUserEvent);LOAD(clSetUserEventStatus);
#undef LOAD
 struct Buffer {cl_mem memory;uint32_t dtype;uint64_t bytes;};
 cl_context context=nullptr;cl_command_queue queue=nullptr;cl_program program=nullptr;cl_kernel kernel=nullptr;
 cl_mem flags=nullptr;cl_event event=nullptr;std::map<uint64_t,Buffer> buffers;uint64_t next=1;
 std::string name;cl_device_type type=0;bool uncertain=false,closed=false;
 void check(cl_int status,const char *where){if(status!=CL_SUCCESS)throw Error("E_OPENCL",std::string(where)+": "+std::to_string(status));}
 Buffer &buffer(uint64_t id){auto it=buffers.find(id);if(it==buffers.end())throw Error("E_DEVICE_BUFFER","unknown or already closed worker buffer");return it->second;}
 uint64_t publish(cl_mem memory,uint32_t dtype,uint64_t bytes){
  if(buffers.size()>=4096||next>uint64_t(INT64_MAX))throw Error("E_COMPUTE_LIMIT","worker buffer ownership limit exceeded");
  auto id=next++;buffers.emplace(id,Buffer{memory,dtype,bytes});return id;
 }
public:
 bool drain()noexcept{if(queue&&clFinish(queue)!=CL_SUCCESS)uncertain=true;return !uncertain;}
 bool settled()const noexcept{return !uncertain;}
 ~GPU(){closeNoThrow();}
 void closeNoThrow()noexcept{
  if(closed)return;
  if(!drain())return;
  auto released=buffers.size();
  auto release=[&](cl_int code){if(code!=CL_SUCCESS)uncertain=true;};
  if(event){release(clReleaseEvent(event));event=nullptr;}
  for(auto [id,b]:buffers)release(clReleaseMemObject(b.memory));buffers.clear();
  if(flags){release(clReleaseMemObject(flags));flags=nullptr;}
  if(kernel){release(clReleaseKernel(kernel));kernel=nullptr;}
  if(program){release(clReleaseProgram(program));program=nullptr;}
  if(queue){release(clReleaseCommandQueue(queue));queue=nullptr;}
  if(context){release(clReleaseContext(context));context=nullptr;}
  if(!uncertain){closed=true;std::fprintf(stderr,"NEXGPU_DRAIN %llu 1\n",static_cast<unsigned long long>(released));}
 }
 void open(uint32_t selected){
  cl_uint count=0;check(clGetPlatformIDs(0,nullptr,&count),"platform count");if(!count||count>16)throw Error("E_COMPUTE_UNAVAILABLE","no bounded OpenCL platform list");
  std::vector<cl_platform_id> platforms(count);check(clGetPlatformIDs(count,platforms.data(),nullptr),"platform list");std::vector<cl_device_id> devices;
  for(auto platform:platforms){cl_uint n=0;auto code=clGetDeviceIDs(platform,CL_DEVICE_TYPE_GPU,0,nullptr,&n);if(code==CL_DEVICE_NOT_FOUND)continue;check(code,"GPU count");if(n>16||devices.size()+n>64)throw Error("E_COMPUTE_LIMIT","GPU inventory exceeds configured bounds");std::vector<cl_device_id> part(n);if(n)check(clGetDeviceIDs(platform,CL_DEVICE_TYPE_GPU,n,part.data(),nullptr),"GPU list");devices.insert(devices.end(),part.begin(),part.end());}
  if(selected>=devices.size())throw Error("E_COMPUTE_UNAVAILABLE","selected physical GPU is unavailable");auto device=devices[selected];
  check(clGetDeviceInfo(device,CL_DEVICE_TYPE,sizeof(type),&type,nullptr),"physical device type");if(!(type&CL_DEVICE_TYPE_GPU)||(type&CL_DEVICE_TYPE_CPU))throw Error("E_COMPUTE_UNAVAILABLE","a physical GPU without CPU substitution is required");
  size_t length=0;check(clGetDeviceInfo(device,CL_DEVICE_NAME,0,nullptr,&length),"name size");if(!length||length>4096)throw Error("E_DEVICE_ABI","device name is not bounded");std::vector<char> text(length);check(clGetDeviceInfo(device,CL_DEVICE_NAME,text.size(),text.data(),nullptr),"name");if(text.back()!=0)throw Error("E_DEVICE_ABI","device name is not terminated");name.assign(text.data(),text.size()-1);
  cl_int status=0;context=clCreateContext(nullptr,1,&device,nullptr,nullptr,&status);check(status,"context");queue=clCreateCommandQueue(context,device,CL_QUEUE_PROFILING_ENABLE,&status);check(status,"queue");
  const char *source="__kernel void affine(__global const uchar*a,__global const uchar*b,__global uchar*out,__global uchar*flags,uint scale){size_t i=get_global_id(0);uint v=(uint)a[i]*scale+(uint)b[i];out[i]=(uchar)v;flags[i]=(uchar)(v>255);}";
  program=clCreateProgramWithSource(context,1,&source,nullptr,&status);check(status,"program");auto built=clBuildProgram(program,1,&device,"",nullptr,nullptr);
  if(built!=CL_SUCCESS){char log[2048]={};clGetProgramBuildInfo(program,device,CL_PROGRAM_BUILD_LOG,sizeof(log)-1,log,nullptr);throw Error("E_OPENCL_BUILD",log);}
  kernel=clCreateKernel(program,"affine",&status);check(status,"kernel");flags=clCreateBuffer(context,CL_MEM_READ_WRITE,maximumElements,nullptr,&status);check(status,"bounded session scratch");
  std::fprintf(stderr,"NEXGPU_OPEN %u %llu\n",selected,static_cast<unsigned long long>(type));
 }
 Data info()const{Data d;d.text(name);d.u64(type);d.u32(maximumElements);return d;}
 uint64_t upload(uint32_t dtype,Bytes &bytes){
  auto width=dtype==3?4u:1u;if(dtype<1||dtype>3||bytes.empty()||bytes.size()>uint64_t(maximumElements)*width||bytes.size()%width)throw Error("E_COMPUTE_SIZE","invalid typed buffer bytes");
  if(buffers.size()>=4096)throw Error("E_COMPUTE_LIMIT","worker buffer limit reached");cl_int status=0;auto memory=clCreateBuffer(context,CL_MEM_READ_WRITE|CL_MEM_COPY_HOST_PTR,bytes.size(),bytes.data(),&status);check(status,"upload buffer");
  try{return publish(memory,dtype,bytes.size());}catch(...){clReleaseMemObject(memory);throw;}
 }
 Data affine(uint64_t aid,uint64_t bid,uint32_t scale,const std::function<void(uint32_t,bool)> &admitted){
  auto a=buffer(aid),b=buffer(bid);if(a.dtype!=1||b.dtype!=1||a.bytes!=b.bytes||a.bytes>maximumElements||scale>255)throw Error("E_COMPUTE_SIZE","invalid exact u8 affine buffers");
  if(buffers.size()>=4096)throw Error("E_COMPUTE_LIMIT","worker buffer limit reached");cl_int status=0;auto memory=clCreateBuffer(context,CL_MEM_READ_WRITE,a.bytes,nullptr,&status);check(status,"output buffer");
  cl_event gate=nullptr;std::thread gateThread;std::atomic<cl_int> gateStatus{CL_QUEUED};
  auto releaseGate=[&]()noexcept{
   if(gateThread.joinable())gateThread.join();
   if(gate){if(gateStatus.load()==CL_QUEUED)gateStatus=clSetUserEventStatus(gate,CL_COMPLETE);if(gateStatus.load()!=CL_SUCCESS)uncertain=true;if(clReleaseEvent(gate)!=CL_SUCCESS)uncertain=true;gate=nullptr;}
  };
  try{
   cl_mem args[]={a.memory,b.memory,memory,flags};for(cl_uint i=0;i<4;++i)check(clSetKernelArg(kernel,i,sizeof(cl_mem),&args[i]),"buffer argument");check(clSetKernelArg(kernel,4,sizeof(scale),&scale),"scale argument");size_t n=size_t(a.bytes);
   unsigned delay=0;if(const char *text=std::getenv("NEX_OWNED_OPENCL_TEST_GATE_MS")){auto length=std::strlen(text);if(!length||length>4||std::strspn(text,"0123456789")!=length)throw Error("E_DEVICE_PROTOCOL","invalid controlled gate delay");auto parsed=std::strtoul(text,nullptr,10);if(parsed>5000)throw Error("E_DEVICE_PROTOCOL","controlled gate delay exceeds limit");delay=unsigned(parsed);}
   if(delay){gate=clCreateUserEvent(context,&status);check(status,"controlled physical user event");}
   check(clEnqueueNDRangeKernel(queue,kernel,1,nullptr,&n,nullptr,gate?1:0,gate?&gate:nullptr,&event),"physical kernel dispatch");
   if(gate)gateThread=std::thread([&,pending=gate,ms=delay]{std::this_thread::sleep_for(std::chrono::milliseconds(ms));gateStatus=clSetUserEventStatus(pending,CL_COMPLETE);});
   cl_int queued=CL_COMPLETE;check(clGetEventInfo(event,CL_EVENT_COMMAND_EXECUTION_STATUS,sizeof(queued),&queued,nullptr),"queued physical event");
   if(queued<CL_COMPLETE||queued>CL_QUEUED)throw Error("E_DEVICE_PROTOCOL","invalid queued physical event status");
   if(admitted)admitted(uint32_t(queued),gate!=nullptr);if(!drain())throw Error("E_DEVICE_UNSETTLED","GPU completion could not be established");releaseGate();
   cl_int execution=1;cl_command_type command=0;check(clGetEventInfo(event,CL_EVENT_COMMAND_EXECUTION_STATUS,sizeof(execution),&execution,nullptr),"event execution");check(clGetEventInfo(event,CL_EVENT_COMMAND_TYPE,sizeof(command),&command,nullptr),"event command");if(execution!=CL_COMPLETE||command!=CL_COMMAND_NDRANGE_KERNEL)throw Error("E_DEVICE_UNSETTLED","expected a completed physical kernel event");
   Bytes overflow(n);check(clEnqueueReadBuffer(queue,flags,CL_TRUE,0,n,overflow.data(),0,nullptr,nullptr),"checked overflow readback");cl_ulong start=0,end=0;check(clGetEventProfilingInfo(event,CL_PROFILING_COMMAND_START,sizeof(start),&start,nullptr),"device start");check(clGetEventProfilingInfo(event,CL_PROFILING_COMMAND_END,sizeof(end),&end,nullptr),"device end");if(end<start||end-start>uint64_t(INT64_MAX))throw Error("E_DEVICE_ABI","invalid physical profiling interval");
   bool rejected=std::any_of(overflow.begin(),overflow.end(),[](uint8_t x){return x!=0;});std::fprintf(stderr,"NEXGPU_KERNEL %llu %u %llu %u\n",static_cast<unsigned long long>(n),scale,static_cast<unsigned long long>(end-start),rejected?1u:0u);check(clReleaseEvent(event),"event release");event=nullptr;if(rejected)throw Error("E_COMPUTE_OVERFLOW","exact physical GPU output does not fit u8");
   auto id=publish(memory,1,n);memory=nullptr;Data d;d.u64(id);d.u64(n);d.u64(end-start);d.u32(uint32_t(execution));d.u32(uint32_t(command));return d;
  }catch(...){releaseGate();bool completed=drain();if(event&&completed){clReleaseEvent(event);event=nullptr;}if(memory&&completed)clReleaseMemObject(memory);throw;}
 }
 Bytes download(uint64_t id){auto b=buffer(id);Bytes result(size_t(b.bytes));check(clEnqueueReadBuffer(queue,b.memory,CL_TRUE,0,result.size(),result.data(),0,nullptr,nullptr),"buffer download");return result;}
 void free(uint64_t id){auto b=buffer(id);if(!drain())throw Error("E_DEVICE_UNSETTLED","buffer remains physically unsettled");check(clReleaseMemObject(b.memory),"buffer release");buffers.erase(id);}
 size_t live()const{return buffers.size();}
};
int main(){
 if(std::getenv("NEX_OWNED_OPENCL_TEST_NOISE"))std::fputs("controlled worker stdout diagnostic\n",stdout);
 std::signal(SIGPIPE,SIG_IGN);rlimit noCore{0,0};setrlimit(RLIMIT_CORE,&noCore);
 std::unique_ptr<GPU> gpu;uint64_t expected=1;Frame request{};bool faulted=false;
 try{
  if(const char *path=std::getenv("NEX_OWNED_OPENCL_TEST_CACHE_FILE")){
   if(path[0]!='/'||std::strlen(path)>4096)throw Error("E_DEVICE_TEST","controlled cache path must be absolute and bounded");
   int fd=::open(path,O_WRONLY|O_CREAT|O_EXCL|O_CLOEXEC,0600);if(fd<0)throw Error("E_DEVICE_TEST","controlled cache file creation failed");
   struct Close{int fd;~Close(){::close(fd);}} close{fd};char block[4096]={};std::fprintf(stderr,"NEXGPU_TEST_CACHE_BEGIN 9437184\n");
   for(size_t written=0;written<9437184;){auto n=::write(fd,block,std::min(sizeof(block),size_t(9437184-written)));if(n<0&&errno==EINTR)continue;if(n<=0)throw Error("E_DEVICE_TEST","controlled cache write failed");written+=size_t(n);}
   std::fprintf(stderr,"NEXGPU_TEST_CACHE_END 9437184\n");
  }
  if(const char *text=std::getenv("NEX_OWNED_OPENCL_TEST_NOISE_BYTES")){
   auto length=std::strlen(text);if(!length||length>8||std::strspn(text,"0123456789")!=length)throw Error("E_DEVICE_TEST","invalid controlled log size");
   auto count=std::strtoul(text,nullptr,10);if(count>16777216)throw Error("E_DEVICE_TEST","controlled log size exceeds16MiB");
   char block[4096];std::memset(block,'#',sizeof(block));block[sizeof(block)-1]='\n';std::fprintf(stderr,"NEXGPU_TEST_NOISE_BEGIN %lu\n",count);
   for(size_t n=0;n<count;){auto size=std::min(sizeof(block),size_t(count-n));if(std::fwrite(block,1,size,stdout)!=size)throw Error("E_DEVICE_TEST","controlled stdout write failed");n+=size;}
   if(std::fflush(stdout))throw Error("E_DEVICE_TEST","controlled stdout flush failed");std::fprintf(stderr,"NEXGPU_TEST_NOISE_END %lu\n",count);
  }
  const char *fault=std::getenv("NEX_OWNED_OPENCL_TEST_BAD_REPLY");
  if(fault&&std::strcmp(fault,"upload_truncated")&&std::strcmp(fault,"upload_wrong_size")&&std::strcmp(fault,"upload_reused_id")&&std::strcmp(fault,"affine_reused_id")&&std::strcmp(fault,"affine_truncated")&&std::strcmp(fault,"affine_trailing")&&std::strcmp(fault,"download_truncated")&&std::strcmp(fault,"download_wrong_size")&&std::strcmp(fault,"free_trailing")&&std::strcmp(fault,"close_truncated")&&std::strcmp(fault,"open_trailing"))throw Error("E_DEVICE_PROTOCOL","unknown controlled reply fault");
  auto wants=[&](const char *name){return !faulted&&fault&&std::strcmp(fault,name)==0;};
  while(receive(3,request)){
   if(request.sequence!=expected++||request.status!=0)throw Error("E_DEVICE_PROTOCOL","worker sequence or request status differs");
   try{
    Data input(std::move(request.payload)),output;bool closing=false;
    switch(request.operation){
     case Open:{if(gpu)throw Error("E_DEVICE_PROTOCOL","worker session already opened");auto ordinal=input.get32();input.done();gpu=std::make_unique<GPU>();gpu->open(ordinal);output=gpu->info();break;}
     case Upload:{if(!gpu)throw Error("E_DEVICE_PROTOCOL","no GPU session");auto dtype=input.get32();auto bytes=input.getBlob();input.done();output.u64(gpu->upload(dtype,bytes));output.u64(bytes.size());break;}
     case Affine:{if(!gpu)throw Error("E_DEVICE_PROTOCOL","no GPU session");auto a=input.get64(),b=input.get64();auto scale=input.get32();input.done();output=gpu->affine(a,b,scale,[&](uint32_t status,bool gated){Data progress;progress.u32(1);progress.u32(status);progress.u32(gated?1:0);send(3,Frame{request.sequence,request.operation,Progress,std::move(progress.bytes)});});break;}
     case Download:{if(!gpu)throw Error("E_DEVICE_PROTOCOL","no GPU session");auto id=input.get64();input.done();output.blob(gpu->download(id));break;}
     case Free:{if(!gpu)throw Error("E_DEVICE_PROTOCOL","no GPU session");auto id=input.get64();input.done();gpu->free(id);output.u32(uint32_t(gpu->live()));break;}
     case Close:{input.done();if(gpu&&gpu->live())throw Error("E_DEVICE_PROTOCOL","session closed before its actual buffers");if(gpu){gpu->closeNoThrow();if(!gpu->settled())throw Error("E_DEVICE_UNSETTLED","session release is not confirmed");gpu.reset();}output.u32(0);closing=true;break;}
     default:throw Error("E_DEVICE_PROTOCOL","unknown worker operation");
    }
    bool corrupt=false;
    if((request.operation==Upload&&wants("upload_truncated"))||(request.operation==Affine&&wants("affine_truncated"))){output.bytes.resize(7);corrupt=true;}
    if(request.operation==Upload&&wants("upload_wrong_size")){output.bytes.at(8)^=1;corrupt=true;}
    if((request.operation==Upload&&wants("upload_reused_id")&&gpu->live()>1)||(request.operation==Affine&&wants("affine_reused_id"))){for(size_t i=0;i<8;++i)output.bytes.at(i)=i==0?1:0;corrupt=true;}
    if((request.operation==Affine&&wants("affine_trailing"))||(request.operation==Free&&wants("free_trailing"))||(request.operation==Open&&wants("open_trailing"))){output.bytes.push_back(0);corrupt=true;}
    if((request.operation==Download&&wants("download_truncated"))||(request.operation==Close&&wants("close_truncated"))){output.bytes.resize(3);corrupt=true;}
    if(request.operation==Download&&wants("download_wrong_size")){Data original(std::move(output.bytes));auto bytes=original.getBlob();original.done();if(!bytes.empty())bytes.pop_back();Data wrong;wrong.blob(bytes);output=std::move(wrong);corrupt=true;}
    if(corrupt){faulted=true;std::fprintf(stderr,"NEXGPU_FAULT %s %u\n",fault,request.operation);}
    send(3,Frame{request.sequence,request.operation,Success,std::move(output.bytes)});if(closing)return 0;
   }catch(const Error &e){auto status=e.code=="E_DEVICE_UNSETTLED"||(gpu&&!gpu->drain())?Unsettled:Failure;send(3,Frame{request.sequence,request.operation,uint32_t(status),failure(e)});if(status==Unsettled)return 3;}
  }
  if(gpu){gpu->closeNoThrow();if(!gpu->settled())return 3;}return 0;
 }catch(const std::exception &){if(gpu){gpu->closeNoThrow();if(!gpu->settled())return 3;}return 20;}
}
